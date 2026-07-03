#!/bin/bash
# vibe-feedback-agent 일일 러너 — 3패스 (생성 → 심사 → 게시), crontab에서 호출
set -u
BASE=/home/ubuntu/vibe-feedback-agent
LOG="$BASE/logs/run-$(date +%Y%m%d-%H%M%S).log"
CLAUDE=/home/ubuntu/.local/bin/claude
export PATH="/home/ubuntu/.local/bin:$PATH"
cd "$BASE"

# 동시 실행 방지
exec 9>"$BASE/.lock"
flock -n 9 || { echo "already running" >> "$LOG"; exit 0; }

mkdir -p "$BASE/work"
rm -f "$BASE/work/drafts.json" "$BASE/work/verdicts.json"

echo "=== Pass 1: 생성 $(date -Iseconds) ===" >> "$LOG"
"$CLAUDE" -p "$(cat "$BASE/PROMPT.md")" \
  --allowedTools "Bash" "WebFetch" "WebSearch" "Read" "Write" "Edit" "Glob" "Grep" \
  >> "$LOG" 2>&1

DRAFTS=$(python3 -c "import json;print(len(json.load(open('$BASE/work/drafts.json')).get('drafts',[])))" 2>/dev/null || echo 0)
echo "--- drafts: $DRAFTS ---" >> "$LOG"

if [ "$DRAFTS" -gt 0 ]; then
  echo "=== Pass 2: 심사 $(date -Iseconds) ===" >> "$LOG"
  "$CLAUDE" -p "$(cat "$BASE/VERIFIER.md")" \
    --allowedTools "Bash" "WebFetch" "Read" "Write" "Glob" "Grep" \
    >> "$LOG" 2>&1

  echo "=== Pass 3: 게시 $(date -Iseconds) ===" >> "$LOG"
  python3 "$BASE/post_drafts.py" >> "$LOG" 2>&1
else
  echo "초안 없음 — 심사/게시 생략" >> "$LOG"
fi

echo "=== done $(date -Iseconds) ===" >> "$LOG"

# 로그 30일 보관
find "$BASE/logs" -name 'run-*.log' -mtime +30 -delete 2>/dev/null
exit 0
