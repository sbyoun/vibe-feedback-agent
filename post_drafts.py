#!/usr/bin/env python3
"""Pass 3: 게시 — verifier PASS 초안만 feedback_create로 올리고 상태를 확정한다.
결정론적 스크립트. 토큰은 이 단계만 접근한다."""
import datetime
import glob
import json
import os
import subprocess
import sys

BASE = "/home/ubuntu/vibe-feedback-agent"
URL = "https://vibe.foldalpha.com/mcp"
MAX_POST = 10


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


state = load(f"{BASE}/state.json", {"projects": {}})
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
today = datetime.date.today().strftime("%Y%m%d")

draft_files = sorted(glob.glob(f"{BASE}/work/drafts/*.json"))
if not draft_files:
    print("no drafts")
    sys.exit(0)

token = open(f"{BASE}/token").read().strip()
posted, rejected, skipped, errors = [], [], [], []

for df in draft_files:
    d = load(df, None)
    if d is None:
        errors.append((os.path.basename(df), "초안 파일 파싱 실패"))
        continue
    pid = d.get("projectId")
    rec = state["projects"].setdefault(pid, {"projectId": pid, "slug": d.get("slug")})

    if d.get("skip"):
        rec["lastAction"] = "skipped:no-substance"
        skipped.append((d.get("slug", pid), d.get("reason", "")))
        continue

    v = load(f"{BASE}/work/verdicts/{pid}.json", None)
    if v is None or v.get("verdict") != "PASS":
        reason = (v or {}).get("reason", "verdict 파일 없음")
        rec["lastAction"] = "rejected:verifier"
        rejected.append((d.get("slug", pid), reason))
        continue
    if len(posted) >= MAX_POST:
        rec["lastAction"] = "deferred:daily-limit"
        rejected.append((d.get("slug", pid), "일일 게시 한도"))
        continue

    args = {"projectId": pid, "body": d["body"]}
    for k in ("feedbackType", "rating", "parentFeedbackId"):
        if d.get(k):
            args[k] = d[k]
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "vibe.feedback_create", "arguments": args}},
                      ensure_ascii=False)
    p = subprocess.run(["curl", "-sS", "--max-time", "30", "-X", "POST", URL,
                        "-H", "Content-Type: application/json",
                        "-H", "Accept: application/json, text/event-stream",
                        "-H", f"Authorization: Bearer {token}",
                        "--data-binary", "@-"],
                       input=body.encode(), capture_output=True)
    try:
        r = json.loads(p.stdout.decode())
        if "error" in r:
            errors.append((d.get("slug", pid), r["error"].get("message", "?")))
            rec["lastAction"] = "error:post"
            continue
        fb = r["result"]["structuredContent"].get("feedback", {})
        posted.append((d.get("slug", pid), fb.get("id")))
        rec["lastAction"] = "posted"
        rec["lastReviewedAt"] = now
        rec.setdefault("ownCommentIds", []).append(fb.get("id"))
        rec["commentCountSeen"] = rec.get("commentCountSeen", 0) + 1
    except Exception as e:
        errors.append((d.get("slug", pid), str(e)))
        rec["lastAction"] = "error:post"

with open(f"{BASE}/state.json", "w") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

with open(f"{BASE}/logs/summary-{today}.md", "a") as f:
    f.write(f"## Pass 3 — 게시 {len(posted)} / 기각 {len(rejected)} / 무실질 스킵 {len(skipped)} / 오류 {len(errors)}\n")
    for s, fid in posted:
        f.write(f"- ✅ posted {s[:45]} → {fid}\n")
    for s, why in rejected:
        f.write(f"- ⛔ rejected {s[:45]} — {why}\n")
    for s, why in skipped:
        f.write(f"- 💤 skip {s[:45]} — {why}\n")
    for s, why in errors:
        f.write(f"- ⚠️ error {s[:45]} — {why}\n")

print(f"posted={len(posted)} rejected={len(rejected)} skipped={len(skipped)} errors={len(errors)}")
