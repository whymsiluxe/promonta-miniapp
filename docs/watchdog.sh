#!/bin/bash
UNIT="claude-autonomous-run"
REPO="/home/promonta/agent/miniapp-repo"
LOG="$REPO/docs/autonomous_run.log"

STATE=$(systemctl is-active "$UNIT.service" 2>&1)

if [ "$STATE" = "active" ]; then
  exit 0
fi

echo "$(date -Iseconds) watchdog: unit state=$STATE, restarting" >> "$REPO/docs/watchdog.log"

systemctl reset-failed "$UNIT.service" 2>>"$REPO/docs/watchdog.log"

systemd-run --uid=promonta --gid=promonta \
  --property=EnvironmentFile=/etc/claude-agent.env \
  --property=WorkingDirectory="$REPO" \
  --property=StandardOutput=append:"$LOG" \
  --property=StandardError=append:"$LOG" \
  --unit="$UNIT" \
  /usr/bin/claude --dangerously-skip-permissions -p "Read docs/HANDOFF.md first (has full current status of the production control program), then docs/OPEN_QUESTIONS.md, then docs/PRODUCTION_CONTROL_PLAN.md and docs/AUTONOMOUS_EXECUTION_RULES.md. Continue exactly where HANDOFF.md says work left off — do not redo completed rounds. Keep going through Round 7, autonomously, no stopping for GO messages. Run pytest before/after each change. Commit incrementally. Update HANDOFF.md continuously as you go, so a future restart knows exactly where to resume." \
  >> "$REPO/docs/watchdog.log" 2>&1

echo "$(date -Iseconds) watchdog: restart issued" >> "$REPO/docs/watchdog.log"
