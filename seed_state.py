#!/usr/bin/env python3
"""오늘 게시분 기준으로 state.json 초기화 — 내일 루프가 '변경 없음'을 올바르게 감지하도록."""
import hashlib
import json
import subprocess
import datetime

BASE = "/home/ubuntu/vibe-feedback-agent"
URL = "https://vibe.foldalpha.com/mcp"

PROJECTS = [  # slug, repo(owner/name or None)
    ("chart-atlas-국가별-음악-차트-세계지도", None),
    ("점심메이트-lunch-party-사내-점심-자동매칭-앱", None),
    ("loop-engine-검증-가능한-완료-조건-기반-자율-골-루프-프레임워크", "sbyoun/loop-engine-public"),
    ("finllm-한국-주식-특화-ai-금융-분석-터미널", "sbyoun/finllm-agent"),
    ("yousinsa-fashion-youtube-archive-영상-근거-기반-패션-추천-아카이브", "sbyoun/yousinsa"),
    ("kpoly-ai-집단지성-예측-리서치-플랫폼", None),
    ("vibe-code-workspace-ai-코딩-프로젝트-피드백-보드", None),
    ("alpha-engine-데이터-기반-퀀트-전략-수집-백테스트-리밸런싱-플랫폼", None),
    ("portfolio-dashboard-alpha-engine-라이브-전략-성과-모니터링-대시보드", None),
    ("kid-cat-avatar-아이가-만든-캐릭터와-실시간-대화하는-앱", None),
]
NO_SURFACE = {"alpha-engine-데이터-기반-퀀트-전략-수집-백테스트-리밸런싱-플랫폼",
              "portfolio-dashboard-alpha-engine-라이브-전략-성과-모니터링-대시보드",
              "kid-cat-avatar-아이가-만든-캐릭터와-실시간-대화하는-앱"}

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
state = {"projects": {}, "seededAt": now}

def mcp(name, args):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}, ensure_ascii=False)
    p = subprocess.run(["curl", "-sS", "-X", "POST", URL,
                        "-H", "Content-Type: application/json",
                        "-H", "Accept: application/json, text/event-stream",
                        "--data-binary", "@-"], input=body.encode(), capture_output=True)
    return json.loads(p.stdout.decode())["result"]["structuredContent"]

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

for slug, repo in PROJECTS:
    sc = mcp("vibe.public_projects_get", {"handle": "sbyoun", "slug": slug})
    p = sc.get("project", sc)
    comments = sc.get("feedback") or sc.get("comments") or p.get("feedback") or []
    own = [c.get("id") for c in comments
           if (c.get("author") or {}).get("handle") == "ai-reviewer"] if comments else []
    rec = {
        "projectId": p.get("id"), "slug": slug,
        "lastCheckedAt": now,
        "lastReviewedAt": now if own else None,
        "updatedAtSeen": p.get("updatedAt"),
        "commentCountSeen": len(comments),
        "ownCommentIds": own,
        "repoShaSeen": None, "demoHashSeen": None,
        "lastAction": "posted" if own else (
            "skipped:no-surface" if slug in NO_SURFACE else "skipped:seed"),
    }
    if repo:
        sha = sh(f"curl -sS 'https://api.github.com/repos/{repo}/commits?per_page=1' | python3 -c 'import sys,json; print(json.load(sys.stdin)[0][\"sha\"])' 2>/dev/null")
        rec["repoShaSeen"] = sha or None
        rec["repo"] = repo
    demo = p.get("demoUrl")
    if demo:
        html = subprocess.run(["curl", "-sL", "--max-time", "15", demo],
                              capture_output=True).stdout
        rec["demoHashSeen"] = hashlib.sha256(html).hexdigest() if html else None
        rec["demoUrl"] = demo
    state["projects"][p.get("id")] = rec
    print(f"{slug[:40]:42} action={rec['lastAction']:20} comments={len(comments)} own={len(own)}")

with open(f"{BASE}/state.json", "w") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
print("\nstate.json 초기화 완료")
