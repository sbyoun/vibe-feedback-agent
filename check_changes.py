#!/usr/bin/env python3
"""Pass 0: 열거 + 표면/변경 게이트 (결정론적) — 변경 있는 프로젝트만 큐에 담는다.
LLM 없이 동작. state.json 관찰 마커도 여기서 갱신한다."""
import datetime
import hashlib
import json
import re
import subprocess
import sys

BASE = "/home/ubuntu/vibe-feedback-agent"
URL = "https://vibe.foldalpha.com/mcp"
BOT_HANDLE = "ai-reviewer"
MAX_QUEUE = 10

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
today = datetime.date.today().strftime("%Y%m%d")


def mcp(name, args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}, ensure_ascii=False)
    p = subprocess.run(["curl", "-sS", "--max-time", "30", "-X", "POST", URL,
                        "-H", "Content-Type: application/json",
                        "-H", "Accept: application/json, text/event-stream",
                        "--data-binary", "@-"], input=body.encode(), capture_output=True)
    return json.loads(p.stdout.decode())["result"]["structuredContent"]


def repo_sha(repo_url):
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", repo_url or "")
    if not m:
        return None
    out = subprocess.run(
        ["curl", "-sS", "--max-time", "15",
         f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/commits?per_page=1"],
        capture_output=True).stdout
    try:
        return json.loads(out)[0]["sha"]
    except Exception:
        return None


def demo_hash(url):
    out = subprocess.run(["curl", "-sL", "--max-time", "15", url],
                         capture_output=True).stdout
    return hashlib.sha256(out).hexdigest() if out else None


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


state = load_json(f"{BASE}/state.json", {"projects": {}})

# 1) 열거 (페이지네이션)
entries, offset = [], 0
while True:
    sc = mcp("vibe.public_projects_list", {"limit": 100, "offset": offset, "sort": "updated"})
    page = sc.get("projects", [])
    entries.extend(page)
    if len(page) < 100:
        break
    offset += 100

candidates, skips = [], []
for e in entries:
    p, owner = e["project"], e["owner"]
    if owner.get("handle") == BOT_HANDLE:
        continue
    pid = p["id"]
    rec = state["projects"].setdefault(pid, {"projectId": pid})
    rec.update({"slug": p.get("slug"), "handle": owner.get("handle"), "lastCheckedAt": now})

    # 게이트 1: 표면
    if not p.get("demoUrl") and not p.get("repoUrl"):
        rec["lastAction"] = "skipped:no-surface"
        skips.append((p.get("title", "?"), "no-surface"))
        continue

    # 게이트 2: 변경 신호
    signals = []
    is_new = "updatedAtSeen" not in rec
    if is_new:
        signals.append("new-project")
    else:
        if p.get("updatedAt") and p["updatedAt"] > (rec.get("updatedAtSeen") or ""):
            signals.append("post-updated")

    detail = mcp("vibe.public_projects_get", {"handle": owner.get("handle"), "slug": p.get("slug")})
    dp = detail.get("project", detail)
    comments = detail.get("feedback") or detail.get("comments") or dp.get("feedback") or []
    if not is_new and len(comments) != rec.get("commentCountSeen", 0):
        signals.append("comments-changed")

    sha = repo_sha(p.get("repoUrl")) if p.get("repoUrl") else None
    if sha and not is_new and sha != rec.get("repoShaSeen"):
        signals.append("repo-commit")
    dhash = demo_hash(p.get("demoUrl")) if p.get("demoUrl") else None
    if dhash and not is_new and dhash != rec.get("demoHashSeen"):
        signals.append("demo-changed(weak)")

    # 관찰 마커는 확인 시점 기준으로 갱신 (같은 변경으로 무한 재시도 방지)
    rec.update({"updatedAtSeen": p.get("updatedAt"), "commentCountSeen": len(comments),
                "repoShaSeen": sha or rec.get("repoShaSeen"),
                "demoHashSeen": dhash or rec.get("demoHashSeen")})

    if not signals:
        rec["lastAction"] = "skipped:no-change"
        skips.append((p.get("title", "?"), "no-change"))
        continue

    own = [c for c in comments if (c.get("author") or {}).get("handle") == BOT_HANDLE]
    others = [c for c in comments if (c.get("author") or {}).get("handle") != BOT_HANDLE]
    rec["lastAction"] = "queued"
    candidates.append({
        "projectId": pid, "slug": p.get("slug"), "handle": owner.get("handle"),
        "title": p.get("title"), "isNew": is_new, "changeSignals": signals,
        "project": dp, "ownerAndOtherComments": others, "botPreviousComments": own,
    })

# 신규 우선 → 신호 수 내림차순, 상한
candidates.sort(key=lambda c: (not c["isNew"], -len(c["changeSignals"])))
overflow = candidates[MAX_QUEUE:]
candidates = candidates[:MAX_QUEUE]
for c in overflow:
    state["projects"][c["projectId"]]["lastAction"] = "deferred:queue-full"

for i, c in enumerate(candidates):
    with open(f"{BASE}/work/queue/{i:02d}-{c['projectId']}.json", "w") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)

with open(f"{BASE}/state.json", "w") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)

with open(f"{BASE}/logs/summary-{today}.md", "a") as f:
    f.write(f"\n# 실행 {now}\n## Pass 0 — 검토 {len(entries)} / 큐 {len(candidates)} / 이월 {len(overflow)}\n")
    for c in candidates:
        f.write(f"- ▶ queued {c['slug'][:45]} — {', '.join(c['changeSignals'])}\n")
    from collections import Counter
    for reason, n in Counter(r for _, r in skips).items():
        f.write(f"- 스킵 {reason}: {n}건\n")

print(f"checked={len(entries)} queued={len(candidates)} deferred={len(overflow)}")
