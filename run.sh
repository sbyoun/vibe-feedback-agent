#!/bin/bash
# vibe-feedback-agent 일일 러너 — 프로젝트별 독립 컨텍스트 4패스
# Pass 0: 변경감지(코드) → Pass 1: 프로젝트별 생성(LLM) → Pass 2: 초안별 심사(LLM) → Pass 3: 게시(코드)
set -u
BASE=/home/ubuntu/vibe-feedback-agent
LOG="$BASE/logs/run-$(date +%Y%m%d-%H%M%S).log"
CLAUDE=/home/ubuntu/.local/bin/claude
export PATH="/home/ubuntu/.local/bin:$PATH"
cd "$BASE"

exec 9>"$BASE/.lock"
flock -n 9 || { echo "already running" >> "$LOG"; exit 0; }

rm -rf "$BASE/work/queue" "$BASE/work/drafts" "$BASE/work/verdicts"
mkdir -p "$BASE/work/queue" "$BASE/work/drafts" "$BASE/work/verdicts" "$BASE/logs"

echo "=== Pass 0: 변경 감지 $(date -Iseconds) ===" >> "$LOG"
python3 "$BASE/check_changes.py" >> "$LOG" 2>&1 || { echo "check_changes 실패" >> "$LOG"; exit 1; }

QUEUED=$(ls "$BASE/work/queue" 2>/dev/null | wc -l)
if [ "$QUEUED" -eq 0 ]; then
  echo "변경 없음 — LLM 호출 없이 종료 $(date -Iseconds)" >> "$LOG"
  exit 0
fi

echo "=== Pass 1: 생성 (${QUEUED}개, 프로젝트별 독립 세션) ===" >> "$LOG"
for f in "$BASE"/work/queue/*.json; do
  echo "--- gen: $(basename "$f") $(date -Iseconds)" >> "$LOG"
  timeout 1200 "$CLAUDE" -p "$(cat "$BASE/PROMPT.md")

입력 파일: $f" \
    --allowedTools "Bash" "WebFetch" "WebSearch" "Read" "Write" "Glob" "Grep" \
    >> "$LOG" 2>&1 || echo "gen 실패/타임아웃: $(basename "$f")" >> "$LOG"
done

echo "=== Pass 2: 심사 (초안별 독립 세션) ===" >> "$LOG"
for f in "$BASE"/work/drafts/*.json; do
  [ -e "$f" ] || continue
  python3 -c "import json,sys; sys.exit(0 if not json.load(open('$f')).get('skip') else 1)" || continue
  echo "--- verify: $(basename "$f") $(date -Iseconds)" >> "$LOG"
  timeout 900 "$CLAUDE" -p "$(cat "$BASE/VERIFIER.md")

초안 파일: $f" \
    --allowedTools "Bash" "WebFetch" "Read" "Write" "Glob" "Grep" \
    >> "$LOG" 2>&1 || echo "verify 실패/타임아웃: $(basename "$f")" >> "$LOG"
done

echo "=== Pass 3: 게시 $(date -Iseconds) ===" >> "$LOG"
python3 "$BASE/post_drafts.py" >> "$LOG" 2>&1

echo "=== done $(date -Iseconds) ===" >> "$LOG"
find "$BASE/logs" -name 'run-*.log' -mtime +30 -delete 2>/dev/null
exit 0
