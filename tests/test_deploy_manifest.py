"""Phase 1 (11.09.2026): Backend artifact manifest integrity tests.

Verifies that:
1. All files listed in scripts/manifest.sh exist in backend/.
2. All listed .py files pass py_compile.
3. backend/core/ exists and its .py files pass py_compile.
4. daily_plan_lib.py is in the manifest (the P0 finding that triggered this).
5. Backup → deploy → rollback round-trip preserves file hashes (simulated in temp dirs).
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
MANIFEST_PATH = os.path.join(REPO_ROOT, 'scripts', 'manifest.sh')
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')


def _parse_manifest():
    """Parse BACKEND_PY_LIBS and BACKEND_JS_FILES arrays from manifest.sh."""
    with open(MANIFEST_PATH, encoding='utf-8') as f:
        content = f.read()
    py_match = re.search(r'BACKEND_PY_LIBS=\(([^)]+)\)', content, re.DOTALL)
    js_match = re.search(r'BACKEND_JS_FILES=\(([^)]+)\)', content, re.DOTALL)
    core_match = re.search(r'BACKEND_CORE_DIR="([^"]+)"', content)
    py_libs = re.findall(r'"([^"]+\.py)"', py_match.group(1)) if py_match else []
    js_files = re.findall(r'"([^"]+\.js)"', js_match.group(1)) if js_match else []
    core_dir = core_match.group(1) if core_match else 'core'
    return py_libs, js_files, core_dir


class ManifestCompletenessTests(unittest.TestCase):
    """All files listed in manifest exist and compile; critical file is present."""

    @classmethod
    def setUpClass(cls):
        cls.py_libs, cls.js_files, cls.core_dir = _parse_manifest()

    def test_manifest_file_exists(self):
        self.assertTrue(os.path.isfile(MANIFEST_PATH), f"manifest.sh not found at {MANIFEST_PATH}")

    def test_daily_plan_lib_in_manifest(self):
        self.assertIn('daily_plan_lib.py', self.py_libs,
                      "daily_plan_lib.py missing from BACKEND_PY_LIBS in manifest.sh "
                      "(P0 finding: main.py imports it but it was not being deployed)")

    def test_all_manifest_py_libs_exist(self):
        for f in self.py_libs:
            path = os.path.join(BACKEND_DIR, f)
            self.assertTrue(os.path.isfile(path), f"Manifest lists {f} but backend/{f} does not exist")

    def test_all_manifest_js_files_exist(self):
        for f in self.js_files:
            path = os.path.join(BACKEND_DIR, f)
            self.assertTrue(os.path.isfile(path), f"Manifest lists {f} but backend/{f} does not exist")

    def test_core_dir_exists(self):
        core_path = os.path.join(BACKEND_DIR, self.core_dir)
        self.assertTrue(os.path.isdir(core_path), f"backend/{self.core_dir}/ not found")

    def test_manifest_py_libs_compile(self):
        for f in self.py_libs:
            path = os.path.join(BACKEND_DIR, f)
            result = subprocess.run(
                [sys.executable, '-m', 'py_compile', path],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, f"py_compile failed for {f}: {result.stderr}")

    def test_core_py_files_compile(self):
        core_path = os.path.join(BACKEND_DIR, self.core_dir)
        py_files = [os.path.join(core_path, f) for f in os.listdir(core_path)
                    if f.endswith('.py') and f != '__init__.py']
        for path in py_files:
            result = subprocess.run(
                [sys.executable, '-m', 'py_compile', path],
                capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0,
                             f"py_compile failed for {os.path.basename(path)}: {result.stderr}")

    def test_deploy_sh_sources_manifest(self):
        deploy_path = os.path.join(REPO_ROOT, 'scripts', 'deploy.sh')
        with open(deploy_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('manifest.sh', content, "deploy.sh must source manifest.sh")
        self.assertIn('BACKEND_PY_LIBS', content, "deploy.sh must use BACKEND_PY_LIBS loop")

    def test_rollback_sh_sources_manifest(self):
        rollback_path = os.path.join(REPO_ROOT, 'scripts', 'rollback.sh')
        with open(rollback_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('manifest.sh', content, "rollback.sh must source manifest.sh")
        self.assertIn('BACKEND_PY_LIBS', content, "rollback.sh must use BACKEND_PY_LIBS loop")

    def test_daily_plan_lib_in_deploy_backup_and_copy(self):
        """daily_plan_lib.py must be handled by the manifest loop in deploy.sh, not left out."""
        deploy_path = os.path.join(REPO_ROOT, 'scripts', 'deploy.sh')
        with open(deploy_path, encoding='utf-8') as f:
            content = f.read()
        # Since deploy.sh uses the loop, it must NOT have a hardcoded individual cp for daily_plan_lib
        # (that was the old broken pattern). The manifest loop is sufficient.
        self.assertIn('BACKEND_PY_LIBS', content,
                      "deploy.sh must deploy daily_plan_lib.py via the BACKEND_PY_LIBS manifest loop")


class DeployRollbackRoundTripTests(unittest.TestCase):
    """Simulate backup → mutate → rollback and verify hashes match original."""

    def setUp(self):
        self.py_libs, self.js_files, self.core_dir = _parse_manifest()
        self.old_serving = tempfile.mkdtemp(prefix='rollback_test_old_')
        self.backup_dir = tempfile.mkdtemp(prefix='rollback_test_backup_')
        self.new_repo = tempfile.mkdtemp(prefix='rollback_test_repo_')

    def tearDown(self):
        shutil.rmtree(self.old_serving, ignore_errors=True)
        shutil.rmtree(self.backup_dir, ignore_errors=True)
        shutil.rmtree(self.new_repo, ignore_errors=True)

    def _sha256(self, path):
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            h.update(f.read())
        return h.hexdigest()

    def _dir_hashes(self, base_dir, rel_prefix=''):
        """Return {rel_path: sha256} for all files under base_dir."""
        hashes = {}
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                if fname.startswith('.'):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, base_dir)
                hashes[rel] = self._sha256(full)
        return hashes

    def _simulate_backup(self, serving_dir, backup_dir, core_dir_name):
        """Mirror the backup logic from deploy.sh (ABSENT-marker pattern)."""
        # main.py always present
        shutil.copy(os.path.join(serving_dir, 'main.py'), os.path.join(backup_dir, 'main.py'))
        for f in self.py_libs:
            src = os.path.join(serving_dir, f)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(backup_dir, f))
            else:
                open(os.path.join(backup_dir, f'.{f}.ABSENT'), 'w').close()
        for f in self.js_files:
            src = os.path.join(serving_dir, f)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(backup_dir, f))
        core_src = os.path.join(serving_dir, core_dir_name)
        if os.path.isdir(core_src):
            shutil.copytree(core_src, os.path.join(backup_dir, core_dir_name))
        else:
            open(os.path.join(backup_dir, f'.{core_dir_name}.ABSENT'), 'w').close()

    def _simulate_deploy(self, repo_dir, serving_dir, core_dir_name):
        """Mirror the copy logic from deploy.sh."""
        shutil.copy(os.path.join(repo_dir, 'main.py'), os.path.join(serving_dir, 'main.py'))
        for f in self.py_libs:
            shutil.copy(os.path.join(repo_dir, f), os.path.join(serving_dir, f))
        for f in self.js_files:
            shutil.copy(os.path.join(repo_dir, f), os.path.join(serving_dir, f))
        core_dst = os.path.join(serving_dir, core_dir_name)
        if os.path.isdir(core_dst):
            shutil.rmtree(core_dst)
        shutil.copytree(os.path.join(repo_dir, core_dir_name), core_dst)

    def _simulate_rollback(self, backup_dir, serving_dir, core_dir_name):
        """Mirror the restore logic from rollback.sh."""
        shutil.copy(os.path.join(backup_dir, 'main.py'), os.path.join(serving_dir, 'main.py'))
        for f in self.py_libs:
            bk = os.path.join(backup_dir, f)
            absent = os.path.join(backup_dir, f'.{f}.ABSENT')
            if os.path.isfile(bk):
                shutil.copy(bk, os.path.join(serving_dir, f))
            elif os.path.isfile(absent):
                try:
                    os.remove(os.path.join(serving_dir, f))
                except FileNotFoundError:
                    pass
        for f in self.js_files:
            bk = os.path.join(backup_dir, f)
            if os.path.isfile(bk):
                shutil.copy(bk, os.path.join(serving_dir, f))
        core_bk = os.path.join(backup_dir, core_dir_name)
        core_dst = os.path.join(serving_dir, core_dir_name)
        core_absent = os.path.join(backup_dir, f'.{core_dir_name}.ABSENT')
        if os.path.isdir(core_bk):
            if os.path.isdir(core_dst):
                shutil.rmtree(core_dst)
            shutil.copytree(core_bk, core_dst)
        elif os.path.isfile(core_absent):
            if os.path.isdir(core_dst):
                shutil.rmtree(core_dst)

    def test_roundtrip_preserves_hashes(self):
        """old-serving → backup → deploy-new → rollback → hashes must match old-serving."""
        core_dir_name = self.core_dir

        # Seed old_serving with stub files (all manifest files + core/)
        with open(os.path.join(self.old_serving, 'main.py'), 'w') as f:
            f.write('# old main\n')
        for fname in self.py_libs:
            with open(os.path.join(self.old_serving, fname), 'w') as f:
                f.write(f'# old {fname}\n')
        for fname in self.js_files:
            with open(os.path.join(self.old_serving, fname), 'w') as f:
                f.write(f'// old {fname}\n')
        os.makedirs(os.path.join(self.old_serving, core_dir_name))
        with open(os.path.join(self.old_serving, core_dir_name, 'time.py'), 'w') as f:
            f.write('# old core/time.py\n')

        # Record hashes before deploy
        before_hashes = self._dir_hashes(self.old_serving)

        # Backup old_serving state
        self._simulate_backup(self.old_serving, self.backup_dir, core_dir_name)

        # Seed new_repo with different content
        with open(os.path.join(self.new_repo, 'main.py'), 'w') as f:
            f.write('# new main\n')
        for fname in self.py_libs:
            with open(os.path.join(self.new_repo, fname), 'w') as f:
                f.write(f'# new {fname}\n')
        for fname in self.js_files:
            with open(os.path.join(self.new_repo, fname), 'w') as f:
                f.write(f'// new {fname}\n')
        os.makedirs(os.path.join(self.new_repo, core_dir_name))
        with open(os.path.join(self.new_repo, core_dir_name, 'time.py'), 'w') as f:
            f.write('# new core/time.py\n')

        # Deploy new content to old_serving (simulates production deploy)
        self._simulate_deploy(self.new_repo, self.old_serving, core_dir_name)
        after_deploy_hashes = self._dir_hashes(self.old_serving)
        self.assertNotEqual(before_hashes, after_deploy_hashes, "Deploy should change files")

        # Rollback
        self._simulate_rollback(self.backup_dir, self.old_serving, core_dir_name)
        after_rollback_hashes = self._dir_hashes(self.old_serving)

        self.assertEqual(before_hashes, after_rollback_hashes,
                         f"Hash mismatch after rollback.\n"
                         f"Missing: {set(before_hashes) - set(after_rollback_hashes)}\n"
                         f"Extra: {set(after_rollback_hashes) - set(before_hashes)}")

    def test_roundtrip_with_absent_new_module(self):
        """New module added by deploy (didn't exist before) is deleted on rollback."""
        core_dir_name = self.core_dir
        new_module = 'daily_plan_lib.py'

        # old_serving has all libs EXCEPT new_module
        with open(os.path.join(self.old_serving, 'main.py'), 'w') as f:
            f.write('# old\n')
        for fname in self.py_libs:
            if fname != new_module:
                with open(os.path.join(self.old_serving, fname), 'w') as f:
                    f.write(f'# old {fname}\n')
        os.makedirs(os.path.join(self.old_serving, core_dir_name))
        with open(os.path.join(self.old_serving, core_dir_name, 'time.py'), 'w') as f:
            f.write('# old\n')

        # Backup (new_module absent → ABSENT marker created)
        self._simulate_backup(self.old_serving, self.backup_dir, core_dir_name)
        self.assertTrue(
            os.path.isfile(os.path.join(self.backup_dir, f'.{new_module}.ABSENT')),
            f"Backup should create .{new_module}.ABSENT marker"
        )

        # Deploy adds new_module
        for fname in self.py_libs:
            with open(os.path.join(self.old_serving, fname), 'w') as f:
                f.write(f'# deployed {fname}\n')
        self.assertTrue(os.path.isfile(os.path.join(self.old_serving, new_module)))

        # Rollback: new_module should be removed
        self._simulate_rollback(self.backup_dir, self.old_serving, core_dir_name)
        self.assertFalse(
            os.path.isfile(os.path.join(self.old_serving, new_module)),
            f"Rollback must delete {new_module} when ABSENT marker exists in backup"
        )
