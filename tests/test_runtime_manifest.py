import hashlib
import pathlib
import shlex
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_bash(script: str, cwd: pathlib.Path = ROOT) -> str:
    result = subprocess.run(
        ["bash", "-lc", script],
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def _manifest_entries() -> list[str]:
    out = _run_bash("source scripts/runtime_manifest.sh; backend_runtime_manifest_print")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _write_old_entry(serving: pathlib.Path, entry: str) -> None:
    norm = entry.rstrip("/")
    path = serving / norm
    if entry.endswith("/"):
        (path / "old_nested").mkdir(parents=True, exist_ok=True)
        (path / "old_nested" / "sentinel.py").write_text("OLD = True\n", encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if entry.endswith(".js"):
            path.write_text("console.log('old artifact');\n", encoding="utf-8")
        elif entry.endswith(".py"):
            path.write_text("OLD = True\n", encoding="utf-8")
        else:
            path.write_text("old artifact\n", encoding="utf-8")


def _tree_hash(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class RuntimeManifestTests(unittest.TestCase):
    def test_manifest_contains_daily_plan_and_core(self):
        entries = set(_manifest_entries())
        self.assertIn("daily_plan_lib.py", entries)
        self.assertIn("core/", entries)
        self.assertIn("main.py", entries)
        self.assertIn("angebot_free.js", entries)
        self.assertIn("rechnung.js", entries)

    def test_deploy_then_restore_roundtrips_backend_artifact_tree(self):
        entries = _manifest_entries()
        with tempfile.TemporaryDirectory(prefix="promonta-runtime-manifest-") as tmp:
            tmp_path = pathlib.Path(tmp)
            serving = tmp_path / "serving"
            backup = tmp_path / "backup"
            serving.mkdir()
            for entry in entries:
                _write_old_entry(serving, entry)
            before = _tree_hash(serving)
            serving_q = shlex.quote(str(serving))
            backup_q = shlex.quote(str(backup))
            daily_plan_q = shlex.quote(str(serving / "daily_plan_lib.py"))
            core_storage_q = shlex.quote(str(serving / "core" / "storage.py"))

            script = f"""
            set -euo pipefail
            source scripts/runtime_manifest.sh
            backend_runtime_backup {serving_q} {backup_q}
            backend_runtime_deploy "$PWD/backend" {serving_q}
            test -f {daily_plan_q}
            test -f {core_storage_q}
            backend_runtime_restore {backup_q} {serving_q}
            """
            _run_bash(script)

            after = _tree_hash(serving)
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
