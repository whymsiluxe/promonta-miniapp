#!/bin/bash
# BACKEND RUNTIME ARTIFACT MANIFEST — single source of truth.
# Sourced by deploy.sh and rollback.sh (bash arrays).
# Parsed by tests/test_deploy_manifest.py (Python regex).
#
# Rule: every file that main.py imports from backend/ must appear here.
# If you add a new backend lib imported by main.py, add it here and re-run
# the full test suite — it will catch a missing-from-manifest regression.
#
# Deliberately excluded:
#   cleanup_old_attachments.py — standalone maintenance script, not imported by main.py
#   create_object*.py          — external, at /home/promonta/agent/ (outside this repo)
#                                see docs/OPEN_QUESTIONS_11sep2026.md for resolution plan
BACKEND_PY_LIBS=(
    "tools_lib.py"
    "mangel_lib.py"
    "objekte_lib.py"
    "roadmap_lib.py"
    "work_types.py"
    "profile_skills.py"
    "assignment_matching.py"
    "daily_plan_lib.py"
    "system_status.py"
)
BACKEND_JS_FILES=(
    "angebot_free.js"
    "rechnung.js"
)
# Shipped as a unit: rm -rf $DEST/core && cp -r $SRC/core $DEST/core
BACKEND_CORE_DIR="core"
