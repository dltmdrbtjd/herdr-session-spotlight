#!/usr/bin/env python3
"""Synthetic benchmark: N Claude/Codex sessions in a temporary folder.

    python3 scripts/bench.py --sessions 1000 --messages 40

Measures the first index, a no-change re-index, an append re-index, and search
latency (the engine's own timing and the whole `python3 spotlight.py search`
process the mod runs). The real ~/.claude and ~/.codex are never touched.
"""

import argparse
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "session-spotlight" / "mods" / "session-spotlight" / "engine"
sys.path.insert(0, str(ENGINE))
sys.dont_write_bytecode = True

WORDS_KO = "프로필 수정 로그인 버그 결제 화면 리팩터링 배포 테스트 마이페이지 검색 인덱스 성능 알림 설정 권한 이미지 업로드 캐시 세션".split()
WORDS_EN = "profile login payment refactor deploy test search index cache upload image session api review module button modal".split()


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def sentence(rng, n):
    return " ".join(rng.choice(WORDS_KO + WORDS_EN) for _ in range(n))


def make(root: Path, sessions: int, messages: int, seed: int = 7):
    rng = random.Random(seed)
    claude = root / "claude" / "projects"
    codex = root / "codex" / "sessions" / "2026" / "11" / "19"
    claude.mkdir(parents=True)
    codex.mkdir(parents=True)
    now = time.time()
    for i in range(sessions):
        cwd = f"/work/project-{i % 40}"
        at = now - rng.uniform(0, 90 * 86400)
        if i % 4 == 3:
            sid = f"01a1f20b-{i:04x}-7000-8000-{i:012x}"
            lines = [{"timestamp": iso(at), "type": "session_meta", "payload": {"id": sid, "cwd": cwd, "timestamp": iso(at), "source": "cli"}}]
            for m in range(messages):
                role = "user" if m % 2 == 0 else "assistant"
                lines.append({"timestamp": iso(at + m), "type": "response_item", "payload": {"type": "message", "role": role, "content": [{"type": "input_text" if role == "user" else "output_text", "text": sentence(rng, rng.randint(8, 80))}]}})
            (codex / f"rollout-2026-11-19T00-00-00-{sid}.jsonl").write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines))
        else:
            sid = f"{i:08x}-0000-4000-8000-000000000000"
            folder = claude / cwd.replace("/", "-")
            folder.mkdir(exist_ok=True)
            lines = [{"type": "custom-title", "customTitle": sentence(rng, 4), "sessionId": sid}]
            for m in range(messages):
                role = "user" if m % 2 == 0 else "assistant"
                text = sentence(rng, rng.randint(8, 80))
                lines.append({"type": role, "sessionId": sid, "cwd": cwd, "timestamp": iso(at + m),
                              "message": {"role": role, "content": text if role == "user" else [{"type": "text", "text": text}]}})
                # Tool output the index must skip, as real transcripts are full of it.
                lines.append({"type": "user", "sessionId": sid, "cwd": cwd, "timestamp": iso(at + m),
                              "message": {"role": "user", "content": [{"type": "tool_result", "content": "x" * 2000}]}})
            (folder / f"{sid}.jsonl").write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines))
    return claude.parent, codex.parents[3]


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=1000)
    ap.add_argument("--messages", type=int, default=40)
    ap.add_argument("--runs", type=int, default=15)
    args = ap.parse_args()

    root = Path(tempfile.mkdtemp(prefix="spotlight-bench-"))
    try:
        claude_home, codex_home = make(root, args.sessions, args.messages)
        raw = sum(f.stat().st_size for f in root.rglob("*.jsonl"))
        env = dict(os.environ, SPOTLIGHT_DATA_DIR=str(root / "data"), SPOTLIGHT_CONFIG=str(root / "config.json"))
        (root / "config.json").write_text(json.dumps({"claude_home": str(claude_home), "codex_home": str(codex_home)}))
        os.environ.update(env)

        from spotlight_engine import search, store
        from spotlight_engine.config import load_config
        from spotlight_engine.indexer import run_index

        t = time.perf_counter()
        first = run_index(load_config())
        t_first = time.perf_counter() - t
        t = time.perf_counter()
        again = run_index(load_config())
        t_again = time.perf_counter() - t
        # Append one message to 1% of the files.
        files = sorted(root.rglob("*.jsonl"))[:: 100]
        for f in files:
            with f.open("a") as h:
                h.write(json.dumps({"type": "user", "sessionId": "x", "cwd": "/work/x", "timestamp": iso(time.time()), "message": {"role": "user", "content": "appended 추가 메시지"}}, ensure_ascii=False) + "\n")
        t = time.perf_counter()
        appended = run_index(load_config())
        t_append = time.perf_counter() - t

        queries = ["", "프로필", "프로필 수정", "로그인 버그", "UI", "payment", "review module", "agent:codex 배포", "project:project-3 after:30d", "없는검색어"]
        conn = store.connect(readonly=True)
        in_proc = {}
        for q in queries:
            times = []
            for _ in range(args.runs):
                t = time.perf_counter()
                search.run_search(conn, q, limit=80)
                times.append((time.perf_counter() - t) * 1000)
            in_proc[q] = (statistics.median(times), pct(times, 95))
        conn.close()
        cli = []
        script = str(ENGINE / "spotlight.py")
        for _ in range(args.runs):
            t = time.perf_counter()
            subprocess.run([sys.executable, "-B", script, "search", "--query", "프로필 수정", "--limit", "80"], env=env, capture_output=True, check=True)
            cli.append((time.perf_counter() - t) * 1000)

        db = store.index_path()
        size = sum(os.path.getsize(str(db) + s) for s in ("", "-wal") if os.path.exists(str(db) + s))
        print(f"sessions={first['sessions']} messages={first['messages']} raw_jsonl={raw / 1e6:.1f}MB index={size / 1e6:.1f}MB")
        print(f"index first={t_first * 1000:.0f}ms  no-change={t_again * 1000:.0f}ms (unchanged={again['unchanged']})  append {len(files)} files={t_append * 1000:.0f}ms (appended={appended['appended']})")
        print("search (in-process, ms)  median / p95")
        for q, (med, p95) in in_proc.items():
            print(f"  {q or '(empty)':32s} {med:7.1f} / {p95:7.1f}")
        print(f"search via `python3 spotlight.py search` (what the mod runs): median {statistics.median(cli):.0f}ms, p95 {pct(cli, 95):.0f}ms")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
