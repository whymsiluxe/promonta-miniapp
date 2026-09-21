"""Runs this repo's dependency-free node-*.js runtime regression scripts (see
docs/TESTING.md for why this repo has no JS test framework) as pytest tests,
via subprocess -- so they execute under CI's existing `python -m pytest .`
step without needing a separate CI workflow step (avoids touching
.github/workflows/ci.yml, which needs a workflow-scoped token to push).

Distinct from tests/smoke-*.js (Playwright browser smoke scripts, NOT run in
CI per their own docstrings -- they need a Chromium runtime this repo's CI
doesn't provision). node-*.js scripts are plain Node with mocked globals
(vm.createContext), no browser/DOM, safe to run anywhere `node` exists.
"""
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"


class NodeRuntimeRegressionTests(unittest.TestCase):
    def _run_node_script(self, filename):
        result = subprocess.run(
            ["node", str(TESTS_DIR / filename)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_worker_shift_state_dead_letter_offline_precedence(self):
        self._run_node_script("node-worker-shift-state-dead-letter-offline.js")


if __name__ == '__main__':
    unittest.main()
