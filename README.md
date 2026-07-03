# vibe-feedback-agent

[Vibe Code Workspace](https://vibe.foldalpha.com)의 public 프로젝트에 **사람 수준의 리뷰를 자동으로 다는 AI 에이전트**.
브라우저 자동화 없이 순수 MCP(JSON-RPC over HTTP)로만 동작하며, 매일 1회 크론으로 실행된다.

계정: [`ai-reviewer`](https://vibe.foldalpha.com/p/ai-reviewer) — 모든 리뷰에 AI 자동 리뷰임을 명시한다.

## 설계: 4중 게이트

스팸 봇이 되지 않기 위해, 게시 전에 네 개의 게이트를 통과해야 한다:

| 게이트 | 규칙 |
|---|---|
| 1. 표면 | demo도 repo도 없는 프로젝트는 리뷰하지 않는다 — 관찰 없는 리뷰는 훈수다 |
| 2. 변경 | 글 수정 / 새 댓글 / repo 새 커밋 / 데모 재배포 중 하나라도 없으면 침묵 |
| 3. 중복 | 자신의 이전 리뷰를 읽고 같은 지적을 반복하지 않는다 |
| 4. 가치 | 변경이 있어도 새로 말할 실질이 없으면 SKIP — 억지 피드백 < 침묵 |

리뷰 작성 규칙: 오너의 셀프노트에 직접 반응하고, 데모/repo를 **실제 방문한 관찰**을 근거로 인용하고,
확인 못 한 것은 가설로 표기한다. 오너가 지적을 반영하면 확인 코멘트를 남긴다.

## 구조 — 프로젝트별 독립 컨텍스트 4패스

두 가지 분리 원칙:
1. **생성 ↛ 심사** — "완료는 주장이지 증명이 아니다." 초안을 쓴 에이전트가 게시를 결정하지 않는다 (자기 심사 편향 차단).
2. **프로젝트 ↛ 프로젝트** — LLM 세션은 프로젝트 1개만 담당한다. 피드백 히스토리가 길어져도
   컨텍스트가 비대해지지 않고, 프로젝트 간 관점 오염이 없다.

기계적인 일(열거·변경감지·게시·상태)은 전부 결정론적 코드가 하고, LLM은 판단(관찰·작성·심사)에만 쓴다.
**state.json과 token은 LLM이 아예 만지지 않는다.** 변경이 없는 날은 LLM 호출 0회.

```
run.sh
 ├─ Pass 0  check_changes.py      열거 + 표면/변경 게이트(코드) → 변경분만 work/queue/<id>.json
 ├─ Pass 1  claude -p PROMPT.md   × 프로젝트마다 새 세션 — 관찰·초안 → work/drafts/<id>.json
 ├─ Pass 2  claude -p VERIFIER.md × 초안마다 새 세션 — 독립 심사 → work/verdicts/<id>.json (기본값 FAIL)
 └─ Pass 3  post_drafts.py        PASS만 feedback_create — 토큰은 이 스크립트만 접근
```

```
check_changes.py # Pass 0: 열거·표면 게이트·변경 감지·큐 구성 (결정론적)
PROMPT.md        # Pass 1 규약: 프로젝트 1개 관찰 + 오너 댓글 반응 + 초안 (핵심 파일)
VERIFIER.md      # Pass 2 규약: 초안 1개 심사, 7개 기준, 의심스러우면 FAIL
post_drafts.py   # Pass 3: 결정론적 게시 + 상태 확정 + 일일 요약
run.sh           # 크론 러너: 4패스 오케스트레이션, flock, 세션별 timeout
seed_state.py    # 최초 1회 상태 기준선 시딩
state.json       # (gitignore) 프로젝트별 마지막 관찰 기록 — 변경 감지의 기준
token            # (gitignore) 봇 계정 MCP Bearer 토큰
work/            # (gitignore) 당일 큐/초안/판정 파일
logs/            # (gitignore) 실행 로그 + 일일 요약
```

## 실행

```bash
# 봇 계정 토큰 발급 (vibe.auth_register / auth_token) 후 token 파일에 저장
chmod 600 token

# 상태 기준선 시딩 (최초 1회)
python3 seed_state.py

# 크론 등록 (매일 09:17 KST)
( crontab -l; echo "17 9 * * * $PWD/run.sh" ) | crontab -
```

수동 실행은 `./run.sh`. 로그는 `logs/run-*.log`, 사람이 읽는 요약은 `logs/summary-YYYYMMDD.md`.

## 안전장치

- 하루 최대 게시 5건, 프로젝트당 1건
- 쓰기 도구는 `feedback_create`만 사용 (프로젝트 수정/삭제 도구 사용 금지)
- 같은 지적 반복 금지, 인사치레 답글 금지
- 오류는 로그에 남기고 다음 프로젝트로 진행 (전체 중단 없음)

## 왜 MCP인가

Vibe Code Workspace는 코딩 에이전트가 UI 자동화 없이 계정 생성·프로젝트 등록·피드백을
할 수 있도록 MCP 엔드포인트(`/mcp`)를 제공한다. 이 에이전트는 그 설계의 첫 번째 실전 소비자다 —
등록도, 리뷰 게시도, 오너 반영 확인도 전부 MCP 호출로 이뤄진다.
