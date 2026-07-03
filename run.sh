#!/bin/bash
# vibe-feedback-agent 일일 러너 — crontab에서 호출
set -u
BASE=/home/ubuntu/vibe-feedback-agent
LOG="$BASE/logs/run-$(date +%Y%m%d-%H%M%S).log"
cd "$BASE"

# 동시 실행 방지
exec 9>"$BASE/.lock"
flock -n 9 || { echo "already running" >> "$LOG"; exit 0; }

echo "=== vibe-feedback-agent run $(date -Iseconds) ===" >> "$LOG"
export PATH="/home/ubuntu/.local/bin:$PATH"
/home/ubuntu/.local/bin/claude -p "$(cat "$BASE/PROMPT.md")" \
  --allowedTools "Bash" "WebFetch" "WebSearch" "Read" "Write" "Edit" "Glob" "Grep" \
  >> "$LOG" 2>&1
RC=$?
echo "=== exit $RC $(date -Iseconds) ===" >> "$LOG"

# 로그 30일 보관
find "$BASE/logs" -name 'run-*.log' -mtime +30 -delete 2>/dev/null
exit $RC
