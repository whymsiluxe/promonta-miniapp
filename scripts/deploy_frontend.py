#!/usr/bin/env python3
"""Deploy frontend files to /var/www/miniapp/.
Запускается watchdog.sh (root) когда есть /home/promonta/agent/miniapp/frontend_deploy/.

Полная синхронизация: копирует все js/* и заменяет app.html целиком,
предварительно делая бэкап текущего app.html с таймстампом.

Перед копированием: синтакс-чек JS (node --check) + HTML-валидация через
html.parser.HTMLParser (НЕ regex — regex false-positives на тегах внутри
CSS-комментариев, что вызвало ложный abort в деплое 2026-07-23).
Деплой прерывается, если проверка не проходит — staging-папка остаётся нетронутой.
После копирования: SHA-256 проверка (src vs dst), health smoke test (/api/health),
version-marker обновление.
Ротация бэкапов: хранятся только последние 3 на файл."""
import hashlib
import os
import shutil
import subprocess
import datetime
import re
import glob
import sys
import time
from html.parser import HTMLParser

SRC = '/home/promonta/agent/miniapp/frontend_deploy'
DST = '/var/www/miniapp'
APP_HTML_SRC = os.path.join(SRC, 'app.html')
APP_HTML_DST = os.path.join(DST, 'app.html')
BACKUP_KEEP = 3
HEALTH_URL = 'http://127.0.0.1:8001/api/health'


def check_js_syntax(src_dir):
    js_files = glob.glob(os.path.join(src_dir, 'js', '**', '*.js'), recursive=True)
    for f in js_files:
        result = subprocess.run(['node', '--check', f], capture_output=True, text=True)
        if result.returncode != 0:
            print(f'SYNTAX ERROR in {f}:\n{result.stderr}')
            return False
    print(f'JS syntax OK ({len(js_files)} files checked)')
    return True


class _HTMLBalanceChecker(HTMLParser):
    """Counts open/close tags using Python's real HTML parser.

    Uses the parser's own tokenizer — avoids false positives from tags mentioned
    inside CSS rule strings, JavaScript template literals, or HTML comments
    (the previous regex approach matched those too).
    """
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.error = None

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass  # <tag /> — self-closing, no stack change

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.error = f'unexpected </{tag}>, stack is empty'
            return
        if self.stack[-1] != tag:
            # HTML parsers tolerate some mismatches (optional close tags like <p>, <li>).
            # Only flag if the mismatch is clearly a structural error.
            if tag not in {'p', 'li', 'dt', 'dd', 'option', 'tr', 'td', 'th'}:
                self.error = f'unexpected </{tag}>, expected </{self.stack[-1]}>'
                return
        else:
            self.stack.pop()


def check_html_balance(html_path):
    try:
        text = open(html_path, encoding='utf-8').read()
        checker = _HTMLBalanceChecker()
        checker.feed(text)
        if checker.error:
            print(f'HTML BALANCE ERROR: {checker.error}')
            return False
        unclosed = [t for t in checker.stack if t not in {'html', 'head', 'body'}]
        if unclosed:
            print(f'HTML BALANCE WARNING (non-critical optional close tags): {unclosed}')
        print('HTML parse OK')
        return True
    except Exception as e:
        print(f'HTML parse FAILED: {e}')
        return False


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_copy_sha(src, dst):
    src_sha = sha256_file(src)
    dst_sha = sha256_file(dst)
    if src_sha != dst_sha:
        print(f'SHA MISMATCH: src={src_sha[:12]}… dst={dst_sha[:12]}…')
        return False
    print(f'SHA verified OK: {src_sha[:16]}…')
    return True


def health_check(url=HEALTH_URL, retries=3, delay=2):
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                ['curl', '-sf', '--max-time', '5', url],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print(f'Health check OK ({url}): {result.stdout.strip()[:80]}')
                return True
            print(f'Health check attempt {attempt} failed (returncode={result.returncode}): {result.stderr.strip()[:80]}')
        except Exception as e:
            print(f'Health check attempt {attempt} error: {e}')
        if attempt < retries:
            time.sleep(delay)
    return False


def get_git_sha(repo_dir=None):
    """Return short git SHA (7 chars) of HEAD, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True,
            cwd=repo_dir or os.path.dirname(os.path.abspath(__file__)),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def inject_build_sha(html_path, sha):
    """Append ?v=<sha> to all local JS <script src> and CSS <link href> references,
    and expose window.__APP_BUILD_SHA__ as a global. Idempotent: strips existing ?v=..."""
    text = open(html_path, encoding='utf-8').read()

    # Strip any existing ?v= querystrings from local asset references first
    text = re.sub(r'(<script src="js/[^"?]+)(\?v=[^"]+)(")', r'\1\3', text)
    text = re.sub(r'(<link[^>]+href="[^"?]+\.css)(\?v=[^"]+)(")', r'\1\3', text)

    # Inject ?v=<sha> on all local JS script tags (not external CDN URLs)
    text = re.sub(r'(<script src="js/[^"]+)(")', rf'\1?v={sha}\2', text)

    # Inject window.__APP_BUILD_SHA__ right after <script> that opens the main inline block
    sha_declaration = f'window.__APP_BUILD_SHA__ = {repr(sha)};\n'
    if 'window.__APP_BUILD_SHA__' not in text:
        text = text.replace('<script>\n// Mängel', sha_declaration + '<script>\n// Mängel', 1)
        if 'window.__APP_BUILD_SHA__' not in text:
            # Fallback: inject before initApp()
            text = text.replace('initApp();\n</script>', sha_declaration + 'initApp();\n</script>', 1)

    open(html_path, 'w', encoding='utf-8').write(text)


def bump_version_marker(html_path):
    text = open(html_path, encoding='utf-8').read()
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    marker = f'<!-- build: {ts} -->'
    if re.search(r'<!-- build: [\d-]+ -->', text):
        text = re.sub(r'<!-- build: [\d-]+ -->', marker, text, count=1)
    else:
        text = marker + '\n' + text
    open(html_path, 'w', encoding='utf-8').write(text)
    return ts


def rotate_backups(dst_path, keep=BACKUP_KEEP):
    pattern = f'{dst_path}.bak-*'
    backups = sorted(glob.glob(pattern), reverse=True)
    for old in backups[keep:]:
        os.remove(old)
        print(f'Removed old backup: {old}')


# ── MAIN ─────────────────────────────────────────────────────────────────────

if not os.path.isdir(SRC):
    print('No staging dir, nothing to deploy')
    sys.exit(0)

# Determine build SHA from the miniapp-repo (scripts/ is inside the repo)
BUILD_SHA = get_git_sha(repo_dir=os.path.dirname(os.path.abspath(__file__)))
print(f'Build SHA: {BUILD_SHA}')

print('=' * 60)
print('PRE-DEPLOY VALIDATION')
print('=' * 60)

# 1. Pre-deploy checks — abort on failure, staging dir stays for inspection
if not check_js_syntax(SRC):
    print('DEPLOY ABORTED: JS syntax check failed')
    sys.exit(1)

if os.path.isfile(APP_HTML_SRC) and not check_html_balance(APP_HTML_SRC):
    print('DEPLOY ABORTED: HTML parse check failed')
    sys.exit(1)

print('=' * 60)
print('DEPLOY')
print('=' * 60)

# 2. Backup current app.html (if present)
if os.path.isfile(APP_HTML_DST):
    ts_bak = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = f'{APP_HTML_DST}.bak-{ts_bak}'
    shutil.copy2(APP_HTML_DST, backup_path)
    print(f'Backed up current app.html → {backup_path}')
    rotate_backups(APP_HTML_DST)

# 3. Copy all JS files (overwrite)
js_src_dir = os.path.join(SRC, 'js')
copied_files = []
if os.path.isdir(js_src_dir):
    for root, dirs, files in os.walk(js_src_dir):
        for f in files:
            src_path = os.path.join(root, f)
            rel = os.path.relpath(src_path, SRC)
            dst_path = os.path.join(DST, rel)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)
            if not verify_copy_sha(src_path, dst_path):
                print(f'DEPLOY ABORTED: SHA mismatch on {rel}')
                sys.exit(1)
            copied_files.append(rel)
            print(f'Copied: {rel}')

# 4. Replace app.html wholesale, verify SHA, bump version marker
build_ts = None
if os.path.isfile(APP_HTML_SRC):
    shutil.copy2(APP_HTML_SRC, APP_HTML_DST)
    if not verify_copy_sha(APP_HTML_SRC, APP_HTML_DST):
        print('DEPLOY ABORTED: SHA mismatch on app.html')
        sys.exit(1)
    inject_build_sha(APP_HTML_DST, BUILD_SHA)
    build_ts = bump_version_marker(APP_HTML_DST)
    print(f'app.html replaced (build: {build_ts}, sha: {BUILD_SHA})')
else:
    print('WARNING: no app.html in staging dir, skipped')

print('=' * 60)
print('POST-DEPLOY VERIFICATION')
print('=' * 60)

# 5. Version marker smoke test
if build_ts:
    live_text = open(APP_HTML_DST, encoding='utf-8').read()
    if f'build: {build_ts}' in live_text:
        print(f'Version marker OK: build {build_ts}')
    else:
        print('DEPLOY FAILED: version marker not found in deployed file')
        sys.exit(1)

# 6. Health check (non-blocking for this script — service restart is a human step)
if health_check():
    print('Service health: OK')
else:
    print('Service health: UNREACHABLE (service may need restart — check manually)')
    # Not an abort — health check failure may mean service needs manual restart

print('=' * 60)
files_summary = f'{len(copied_files)} JS file(s)' + (', app.html' if build_ts else '')
print(f'DEPLOY COMPLETE: {files_summary}')
print('=' * 60)

# 7. Remove staging dir
shutil.rmtree(SRC)
print('Staging dir removed')
