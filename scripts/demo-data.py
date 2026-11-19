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
    ("claude", "acme-web", "Edit profile page", -0.4 * H, [
        ("user", "Add an API for editing the nickname and avatar on the profile page, with input validation."),
        ("assistant", "Added the profile update API with validation: nicknames are 2–20 characters and avatars at most 5 MB."),
        ("user", "Only enable the Save button when something changed"),
        ("assistant", "The form now compares its state and enables Save only when there are changes."),
    ]),
    ("claude", "acme-web", "Refactor the checkout page", -5 * H, [
        ("user", "The checkout component is too big. Split it into steps."),
        ("assistant", "Split it into order summary, shipping and payment steps, with shared state in a useCheckout hook."),
    ]),
    ("codex", "acme-api", "Review payment webhook retries", -1.2 * D, [
        ("user", "Review the payment webhook handler for retry safety."),
        ("assistant", "Two issues: the handler isn't idempotent on duplicate events, and failures return 200 so the provider never retries."),
    ]),
    ("claude", "acme-api", "Fix session expiry after login", -2 * D, [
        ("user", "Users get logged out about 30 minutes after signing in. Find out why."),
        ("assistant", "Two refresh-token requests raced and the second one failed. Refreshes are now coalesced into one."),
    ]),
    ("codex", "acme-mobile", "Add push notification settings", -3 * D, [
        ("user", "Add a settings screen for push notifications with per-topic toggles."),
        ("assistant", "Added NotificationSettings with toggles for orders, promotions and chat; preferences sync to the profile API."),
    ]),
    ("claude", "acme-mobile", "Speed up app launch", -6 * D, [
        ("user", "The first screen takes 3 seconds to appear. How can we cut that?"),
        ("assistant", "Font loading and the remote config request were blocking the first screen. Both run asynchronously now: 1.1 s."),
    ]),
    # Korean sessions: substring search works across particles ("프로필" finds "프로필을").
    ("claude", "acme-docs", "온보딩 문서 정리", -12 * D, [
        ("user", "신규 입사자용 개발 환경 세팅 문서를 정리해줘. 프로필 설정 방법도 넣어줘"),
        ("assistant", "설치, 저장소 클론, 환경 변수, 로컬 실행 순서로 다시 썼고 프로필을 설정하는 방법과 FAQ를 추가했습니다."),
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
