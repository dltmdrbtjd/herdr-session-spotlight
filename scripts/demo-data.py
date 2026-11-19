#!/usr/bin/env python3
"""Writes a small, made-up Claude Code + Codex history for screenshots and demos.

    python3 scripts/demo-data.py <folder>

Creates <folder>/claude/projects/... and <folder>/codex/sessions/... with
sessions in projects named acme-*. Point the engine at it with a config file:
{"claude_home": "<folder>/claude", "codex_home": "<folder>/codex"}.
"""

import json
import sys
import time
from pathlib import Path

NOW = time.time()
H, D = 3600, 86400

SESSIONS = [
    ("claude", "acme-web", "마이페이지 프로필 수정", -0.4 * H, [
        ("user", "마이페이지에서 닉네임과 프로필 이미지를 수정하는 API를 붙여줘. 입력값 검증도 필요해."),
        ("assistant", "프로필 수정 API와 입력 유효성 검증을 구현했습니다. 닉네임은 2–20자, 이미지는 5MB 이하만 허용합니다."),
        ("user", "저장 버튼은 변경 사항이 있을 때만 활성화해줘"),
        ("assistant", "폼 상태를 비교해 변경이 있을 때만 저장 버튼이 활성화되도록 했습니다."),
    ]),
    ("claude", "acme-web", "결제 화면 리팩터링", -5 * H, [
        ("user", "결제 화면 컴포넌트가 너무 커. 단계별로 나눠줘."),
        ("assistant", "주문 요약, 배송지, 결제 수단 세 단계로 분리하고 공통 상태는 useCheckout 훅으로 옮겼습니다."),
    ]),
    ("codex", "acme-api", "Review payment webhook retries", -1.2 * D, [
        ("user", "Review the payment webhook handler for retry safety."),
        ("assistant", "Two issues: the handler isn't idempotent on duplicate events, and failures return 200 so the provider never retries."),
    ]),
    ("claude", "acme-api", "로그인 세션 만료 버그", -2 * D, [
        ("user", "로그인하고 30분 지나면 갑자기 로그아웃돼. 원인 찾아줘."),
        ("assistant", "리프레시 토큰 갱신 요청이 동시에 두 번 나가며 두 번째가 실패하는 경쟁 상태였습니다. 갱신을 하나로 합쳐 고쳤습니다."),
    ]),
    ("codex", "acme-mobile", "Add push notification settings", -3 * D, [
        ("user", "Add a settings screen for push notifications with per-topic toggles."),
        ("assistant", "Added NotificationSettings with toggles for orders, promotions and chat; preferences sync to the profile API."),
    ]),
    ("claude", "acme-mobile", "앱 시작 속도 개선", -6 * D, [
        ("user", "앱 첫 화면 뜨는 데 3초나 걸려. 줄일 방법?"),
        ("assistant", "폰트 로딩과 원격 설정 요청이 첫 화면을 막고 있었습니다. 둘 다 비동기로 돌려 1.1초로 줄였습니다."),
    ]),
    ("claude", "acme-docs", "온보딩 문서 정리", -12 * D, [
        ("user", "신규 입사자용 개발 환경 세팅 문서를 정리해줘"),
        ("assistant", "설치, 저장소 클론, 환경 변수, 로컬 실행 순서로 다시 썼고 자주 막히는 부분을 FAQ로 모았습니다."),
    ]),
    ("codex", "acme-web", "Fix flaky checkout e2e test", -20 * D, [
        ("user", "The checkout e2e test fails one run in five. Find out why."),
        ("assistant", "It clicked Pay before the payment iframe finished loading. Waiting for the iframe's ready message fixes it."),
    ]),
]


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve()
    work = root / "work"
    for i, (agent, project, title, offset, turns) in enumerate(SESSIONS):
        cwd = work / project
        cwd.mkdir(parents=True, exist_ok=True)
        start = NOW + offset - 600
        if agent == "claude":
            sid = f"d3m0{i:04d}-0000-4000-8000-{i:012d}"
            folder = root / "claude" / "projects" / str(cwd).replace("/", "-")
            folder.mkdir(parents=True, exist_ok=True)
            lines = []
            for n, (role, text) in enumerate(turns):
                content = text if role == "user" else [{"type": "text", "text": text}]
                lines.append({"type": role, "sessionId": sid, "cwd": str(cwd), "gitBranch": "main", "timestamp": iso(start + n * 150),
                              "message": {"role": role, "content": content}})
            lines.append({"type": "custom-title", "customTitle": title, "sessionId": sid})
            (folder / f"{sid}.jsonl").write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines))
        else:
            sid = f"01a1d3m0-{i:04d}-7000-8000-{i:012d}"
            folder = root / "codex" / "sessions" / "2026" / "11" / "19"
            folder.mkdir(parents=True, exist_ok=True)
            lines = [{"timestamp": iso(start), "type": "session_meta", "payload": {"id": sid, "cwd": str(cwd), "timestamp": iso(start), "source": "cli"}}]
            for n, (role, text) in enumerate(turns):
                kind = "input_text" if role == "user" else "output_text"
                lines.append({"timestamp": iso(start + n * 150), "type": "response_item",
                              "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}})
            (folder / f"rollout-2026-11-19T00-00-00-{sid}.jsonl").write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines))
            with (root / "codex" / "session_index.jsonl").open("a") as f:
                f.write(json.dumps({"id": sid, "thread_name": title}, ensure_ascii=False) + "\n")
    print(json.dumps({"claude_home": str(root / "claude"), "codex_home": str(root / "codex")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
