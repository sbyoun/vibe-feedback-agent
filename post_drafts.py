#!/usr/bin/env python3
"""Pass 3: 게시 — verifier PASS 초안만 feedback_create로 올리고 상태를 확정한다.
결정론적 스크립트. 토큰은 이 단계만 접근한다."""
import datetime
import json
import subprocess
import sys

BASE = "/home/ubuntu/vibe-feedback-agent"
URL = "https://vibe.foldalpha.com/mcp"
MAX_POST = 5

def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

drafts_doc = load(f"{BASE}/work/drafts.json", {"drafts": []})
verdicts_doc = load(f"{BASE}/work/verdicts.json", {"verdicts": []})
drafts = drafts_doc.get("drafts", [])
verdicts = {v["index"]: v for v in verdicts_doc.get("verdicts", [])}

if not drafts:
    print("no drafts — nothing to post")
    sys.exit(0)

token = open(f"{BASE}/token").read().strip()
state = load(f"{BASE}/state.json", {"projects": {}})
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
today = datetime.date.today().strftime("%Y%m%d")

posted, rejected, errors = [], [], []
for i, d in enumerate(drafts):
    v = verdicts.get(i)
    pid = d.get("projectId")
    rec = state["projects"].setdefault(pid, {"projectId": pid, "slug": d.get("slug")})
    if v is None or v.get("verdict") != "PASS":
        reason = (v or {}).get("reason", "verdict 누락")
        rejected.append((d, reason))
        rec["lastAction"] = "rejected:verifier"
        continue
    if len(posted) >= MAX_POST:
        rejected.append((d, "일일 게시 한도 초과"))
        rec["lastAction"] = "rejected:daily-limit"
        continue
    args = {"projectId": pid, "body": d["body"]}
    for k in ("feedbackType", "rating", "parentFeedbackId"):
        if d.get(k):
            args[k] = d[k]
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": "vibe.feedback_create", "arguments": args}},
                      ensure_ascii=False)
    p = subprocess.run(["curl", "-sS", "-X", "POST", URL,
                        "-H", "Content-Type: application/json",
                        "-H", "Accept: application/json, text/event-stream",
                        "-H", f"Authorization: Bearer {token}",
                        "--data-binary", "@-"],
                       input=body.encode(), capture_output=True)
    try:
        r = json.loads(p.stdout.decode())
        if "error" in r:
            errors.append((d, r["error"].get("message", "?")))
            rec["lastAction"] = "error:post"
            continue
        fb = r["result"]["structuredContent"].get("feedback", {})
        posted.append((d, fb.get("id")))
        rec["lastAction"] = "posted"
        rec["lastReviewedAt"] = now
        rec.setdefault("ownCommentIds", []).append(fb.get("id"))
        rec["commentCountSeen"] = rec.get("commentCountSeen", 0) + 1
    except Exception as e:
        errors.append((d, str(e)))
        rec["lastAction"] = "error:post"

with open(f"{BASE}/state.json", "w") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

with open(f"{BASE}/logs/summary-{today}.md", "a") as f:
    f.write(f"\n## 게시 결과 (Pass 3, {now})\n")
    f.write(f"- 초안 {len(drafts)} / 게시 {len(posted)} / 기각 {len(rejected)} / 오류 {len(errors)}\n")
    for d, fid in posted:
        f.write(f"- ✅ posted {d.get('slug','?')[:40]} → {fid}\n")
    for d, why in rejected:
        f.write(f"- ⛔ rejected {d.get('slug','?')[:40]} — {why}\n")
    for d, why in errors:
        f.write(f"- ⚠️ error {d.get('slug','?')[:40]} — {why}\n")

print(f"posted={len(posted)} rejected={len(rejected)} errors={len(errors)}")
