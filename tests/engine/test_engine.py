"""Engine tests: adapters, redaction, incremental indexing, search, live mapping.

Run: python3 -m unittest discover -s tests/engine -v
Every test works in its own temporary folders; the real ~/.claude and ~/.codex are never read.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ENGINE = Path(__file__).resolve().parents[2] / "session-spotlight" / "mods" / "session-spotlight" / "engine"
sys.path.insert(0, str(ENGINE))
sys.dont_write_bytecode = True

from spotlight_engine import live, search, store  # noqa: E402
from spotlight_engine.config import load_config  # noqa: E402
from spotlight_engine.indexer import Busy, IndexLock, run_index  # noqa: E402
from spotlight_engine import store as store_mod  # noqa: E402,F401
from spotlight_engine.redact import redact  # noqa: E402
from spotlight_engine.textutil import excerpt, highlight, snippet  # noqa: E402


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="spotlight-test-"))
        self.claude = self.tmp / "claude"
        self.codex = self.tmp / "codex"
        self.work = self.tmp / "work"
        for p in (self.claude / "projects", self.codex / "sessions" / "2026" / "11" / "19", self.work):
            p.mkdir(parents=True)
        self.env = {
            "SPOTLIGHT_DATA_DIR": str(self.tmp / "data"),
            "SPOTLIGHT_CONFIG": str(self.tmp / "config.json"),
        }
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.write_config()
        self.now = time.time()

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_config(self, **extra):
        body = {"claude_home": str(self.claude), "codex_home": str(self.codex)}
        body.update(extra)
        (self.tmp / "config.json").write_text(json.dumps(body))

    def project(self, name):
        d = self.work / name
        d.mkdir(exist_ok=True)
        return str(d)

    # -- fixtures --------------------------------------------------------

    def claude_session(self, sid, cwd, turns, title=None, ai_title=None, at=None, extra=None):
        folder = self.claude / "projects" / cwd.replace("/", "-")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{sid}.jsonl"
        at = at or self.now - 3600
        lines = []
        for i, (role, text) in enumerate(turns):
            content = text if role == "user" else [{"type": "text", "text": text}]
            lines.append({
                "type": role, "sessionId": sid, "cwd": cwd, "gitBranch": "main", "version": "2.1.0",
                "timestamp": iso(at + i * 10), "message": {"role": role, "content": content},
            })
        if ai_title:
            lines.append({"type": "ai-title", "aiTitle": ai_title, "sessionId": sid})
        if title:
            lines.append({"type": "custom-title", "customTitle": title, "sessionId": sid})
        lines += extra or []
        path.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines))
        return path

    def codex_session(self, sid, cwd, turns, at=None, name=None):
        at = at or self.now - 7200
        path = self.codex / "sessions" / "2026" / "11" / "19" / f"rollout-2026-11-19T10-00-00-{sid}.jsonl"
        lines = [{"timestamp": iso(at), "type": "session_meta", "payload": {"id": sid, "cwd": cwd, "timestamp": iso(at), "source": "cli", "cli_version": "0.169.1"}}]
        lines.append({"timestamp": iso(at), "type": "response_item", "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "You are Codex, developer instructions"}]}})
        lines.append({"timestamp": iso(at), "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /x\n\nsecret rules"}]}})
        for i, (role, text) in enumerate(turns):
            kind = "input_text" if role == "user" else "output_text"
            lines.append({"timestamp": iso(at + 5 + i), "type": "response_item", "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}})
        path.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines))
        if name:
            with (self.codex / "session_index.jsonl").open("a") as f:
                f.write(json.dumps({"id": sid, "thread_name": name, "updated_at": iso(at)}, ensure_ascii=False) + "\n")
        return path

    def index(self, **kw):
        return run_index(load_config(), **kw)

    def search(self, text="", **kw):
        conn = store.connect(readonly=True)
        try:
            return search.run_search(conn, text, now=kw.pop("now", None), **kw)
        finally:
            conn.close()

    def titles(self, text="", **kw):
        return [r["title"] for r in self.search(text, **kw)["results"]]


class AdapterTests(Env):
    def test_claude_titles_noise_and_first_cwd(self):
        cwd = self.project("acme-web")
        self.claude_session(
            "11111111-1111-1111-1111-111111111111", cwd,
            [("user", "마이페이지 프로필 수정 API 만들어줘"), ("assistant", "프로필 수정 API와 입력 유효성 검증을 구현했습니다.")],
            ai_title="AI가 지은 제목", title="마이페이지 프로필 수정",
            extra=[
                {"type": "user", "sessionId": "11111111-1111-1111-1111-111111111111", "cwd": cwd + "/sub", "timestamp": iso(self.now - 100),
                 "message": {"role": "user", "content": [{"type": "tool_result", "content": "SECRET FILE CONTENTS"}]}},
                {"type": "user", "isMeta": True, "sessionId": "11111111-1111-1111-1111-111111111111", "cwd": cwd, "timestamp": iso(self.now - 90),
                 "message": {"role": "user", "content": "<system-reminder>hidden</system-reminder>"}},
                {"type": "assistant", "sessionId": "11111111-1111-1111-1111-111111111111", "cwd": cwd, "timestamp": iso(self.now - 80),
                 "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "private thoughts"}, {"type": "tool_use", "name": "Bash", "input": {"command": "env"}}]}},
                {"type": "user", "sessionId": "11111111-1111-1111-1111-111111111111", "cwd": cwd, "timestamp": iso(self.now - 70),
                 "message": {"role": "user", "content": "<command-name>/clear</command-name>"}},
                {"type": "user", "isSidechain": True, "sessionId": "11111111-1111-1111-1111-111111111111", "cwd": cwd, "timestamp": iso(self.now - 60),
                 "message": {"role": "user", "content": "sidechain prompt"}},
            ],
        )
        self.index()
        res = self.search()["results"]
        self.assertEqual(len(res), 1)
        r = res[0]
        self.assertEqual(r["title"], "마이페이지 프로필 수정")  # custom title beats the AI one
        self.assertEqual(r["cwd"], cwd)  # the launch folder, not a later `cd`
        self.assertEqual(r["project"], "acme-web")
        self.assertEqual(r["messages"], 2)
        for hidden in ("SECRET FILE", "hidden", "private thoughts", "env", "/clear", "sidechain"):
            self.assertEqual(self.search(hidden)["total"], 0, hidden)

    def test_claude_title_falls_back_to_ai_then_prompt(self):
        cwd = self.project("app")
        self.claude_session("22222222-2222-2222-2222-222222222222", cwd, [("user", "  ## 첫 줄 제목\n둘째 줄")], ai_title="AI 제목")
        self.claude_session("33333333-3333-3333-3333-333333333333", cwd, [("user", "  ## 첫 줄 제목\n둘째 줄")])
        self.index()
        self.assertEqual(sorted(self.titles()), ["AI 제목", "첫 줄 제목"])

    def test_codex_meta_names_and_noise(self):
        cwd = self.project("api")
        self.codex_session("01a1f20b-4ca5-7793-bba3-b10e946bfb82", cwd, [("user", "리뷰해줘 로그인 버그"), ("assistant", "로그인 버그를 찾았습니다")], name="Review login bug")
        self.index()
        r = self.search()["results"][0]
        self.assertEqual(r["agent"], "codex")
        self.assertEqual(r["title"], "Review login bug")
        self.assertEqual(r["session_id"], "01a1f20b-4ca5-7793-bba3-b10e946bfb82")
        self.assertEqual(r["resume_args"], ["resume", "01a1f20b-4ca5-7793-bba3-b10e946bfb82", "-C", cwd])
        self.assertEqual(self.search("developer instructions")["total"], 0)
        self.assertEqual(self.search("secret rules")["total"], 0)

    def test_codex_rename_updates_title_without_rollout_change(self):
        cwd = self.project("api")
        self.codex_session("01a1f20b-0000-7793-bba3-b10e946bfb82", cwd, [("user", "hello")], name="Old name")
        self.index()
        with (self.codex / "session_index.jsonl").open("a") as f:
            f.write(json.dumps({"id": "01a1f20b-0000-7793-bba3-b10e946bfb82", "thread_name": "New name"}) + "\n")
        self.index()
        self.assertEqual(self.titles(), ["New name"])


class CopyTests(Env):
    SID = "01a1f20b-1111-7793-bba3-b10e946bfb82"

    def test_rollout_moved_into_the_archive_stays_searchable(self):
        cwd = self.project("api")
        path = self.codex_session(self.SID, cwd, [("user", "아카이브 이동 테스트")])
        self.index()
        archive = self.codex / "archived_sessions"
        archive.mkdir()
        shutil.move(str(path), str(archive / path.name))
        self.index()
        self.assertEqual(self.search("아카이브")["total"], 1)
        self.index()  # and still there once nothing changes
        r = self.search("아카이브")["results"][0]
        self.assertTrue(r["archived"])

    def test_an_older_copy_stands_in_when_the_newer_file_goes(self):
        cwd = self.project("api")
        old = self.codex_session(self.SID, cwd, [("user", "복사본 테스트")], at=self.now - 9000)
        archive = self.codex / "archived_sessions"
        archive.mkdir()
        copy = archive / old.name
        shutil.copy(str(old), str(copy))
        # The live file gets newer.
        with old.open("a") as f:
            f.write(json.dumps({"timestamp": iso(self.now), "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "새 답변"}]}}, ensure_ascii=False) + "\n")
        self.index()
        self.assertEqual(self.search("복사본")["total"], 1)
        self.assertFalse(self.search("복사본")["results"][0]["archived"])
        old.unlink()
        self.index()
        res = self.search("복사본")["results"]
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0]["archived"])


class OwnershipTests(Env):
    SID = "01a1f20b-2222-7793-bba3-b10e946bfb82"

    def turn(self, path, text, ts):
        with path.open("a") as f:
            f.write(json.dumps({"timestamp": iso(ts), "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}}, ensure_ascii=False) + "\n")

    def test_a_former_owner_that_grows_is_read_whole(self):
        cwd = self.project("api")
        a = self.codex_session(self.SID, cwd, [("user", "처음 질문 알파"), ("assistant", "초기 답변 베타")], at=self.now - 9000)
        self.index()  # a owns it
        archive = self.codex / "archived_sessions"
        archive.mkdir()
        b = archive / a.name
        shutil.copy(str(a), str(b))
        self.turn(b, "사본에서 늘어난 답", self.now - 5000)
        self.index()  # b is newer: b owns it now
        self.turn(a, "원본에서 늘어난 답", self.now - 100)
        self.index()  # a is newer again: it must be read from the start, not appended
        self.assertEqual(self.search("초기 답변 베타")["total"], 1)  # only in a message, not in any title/prompt field
        self.assertEqual(self.search("원본에서 늘어난")["total"], 1)
        self.assertEqual(self.search("원본에서 늘어난")["results"][0]["messages"], 3)

    def test_a_copy_stands_in_when_the_owner_gives_the_session_up(self):
        cwd = self.project("api")
        a = self.codex_session(self.SID, cwd, [("user", "양도 테스트")], at=self.now - 9000)
        archive = self.codex / "archived_sessions"
        archive.mkdir()
        shutil.copy(str(a), str(archive / a.name))
        self.turn(a, "원본이 더 새것", self.now - 100)
        self.index()
        self.assertFalse(self.search("양도")["results"][0]["archived"])
        # The owner is rewritten as another session: the archived copy takes the old one over.
        self.codex_session("01a1f20b-3333-7793-bba3-b10e946bfb82", cwd, [("user", "다른 세션")], at=self.now)
        other = sorted((self.codex / "sessions").rglob("*3333*"))[0]
        shutil.move(str(other), str(a))
        self.index()
        res = self.search("양도")["results"]
        self.assertEqual(len(res), 1)
        self.assertTrue(res[0]["archived"])


class RedactionTests(Env):
    def test_redact_patterns(self):
        cases = [
            "key sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123",
            "AKIAABCDEFGHIJKLMNOP",
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz.123",
            "DB_PASSWORD=hunter2hunter2",
            "postgres://user:topsecretpw@db.local/x",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        ]
        for c in cases:
            out = redact(c)
            self.assertIn("[REDACTED]", out, c)
        self.assertNotIn("hunter2", redact("DB_PASSWORD=hunter2hunter2"))
        self.assertNotIn("topsecretpw", redact("postgres://user:topsecretpw@db.local/x"))
        self.assertEqual(redact("프로필 수정 API를 만들었습니다"), "프로필 수정 API를 만들었습니다")
        # Quoted keys (JSON) and quoted values with spaces or escaped quotes.
        self.assertEqual(redact('{"password": "hunter 2 x"}'), '{"password": "[REDACTED]"}')
        self.assertEqual(redact('"client_secret":"a\\"b"'), '"client_secret":"[REDACTED]"')
        self.assertEqual(redact("api_key = 'abc'"), "api_key = '[REDACTED]'")
        self.assertEqual(redact("password is required"), "password is required")
        long_secret = "p" * 900
        self.assertNotIn(long_secret, redact('{"password": "' + long_secret + '"}'))
        self.assertNotIn("cut off", redact('"api_key": "cut off before its quote\nnext line stays'))
        self.assertIn("next line stays", redact('"api_key": "cut off before its quote\nnext line stays'))

    def test_secrets_never_reach_the_index(self):
        cwd = self.project("x")
        self.claude_session("44444444-4444-4444-4444-444444444444", cwd, [("user", "이 키를 써: sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456 그리고 배포해")])
        self.index()
        conn = sqlite3.connect(str(store.index_path()))
        blob = "\n".join(r[0] for r in conn.execute("SELECT text FROM messages_fts"))
        blob += "\n".join(r[0] + r[1] + r[2] for r in conn.execute("SELECT title, first_prompt, last_prompt FROM sessions"))
        conn.close()
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ123456", blob)
        self.assertEqual(self.search("ABCDEFGHIJKLMNOP")["total"], 0)
        self.assertEqual(self.search("배포해")["total"], 1)

    def test_parser_state_keeps_no_secret(self):
        cwd = self.project("x")
        self.claude_session("46444444-4444-4444-4444-444444444444", cwd, [("user", 'deploy with {"password": "hunter 2 x"} and sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456')])
        self.write_config(exclude_paths=[self.project("hidden")])
        self.claude_session("47444444-4444-4444-4444-444444444444", self.project("hidden"), [("user", "excluded prompt with private words")])
        self.index()
        conn = sqlite3.connect(str(store.index_path()))
        states = "\n".join(r[0] for r in conn.execute("SELECT state FROM sources"))
        excluded = conn.execute("SELECT state FROM sources WHERE path LIKE '%47444444%'").fetchone()[0]
        conn.close()
        self.assertNotIn("hunter 2", states)
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ123456", states)
        self.assertEqual(excluded, "{}")
        self.assertNotIn("private words", states)

    def test_prompt_preview_is_masked_before_it_is_cut(self):
        cwd = self.project("x")
        # The closing quote lands on character 401: cut first, the old way, it would be gone.
        prompt = "x" * 375 + '{"password": "hunter2abcd"} tail'
        self.assertEqual(prompt[400], '"')
        self.claude_session("48444444-4444-4444-4444-444444444444", cwd, [("user", prompt)])
        self.index()
        conn = sqlite3.connect(str(store.index_path()))
        blob = "\n".join(r[0] for r in conn.execute("SELECT state FROM sources"))
        blob += "\n".join(r[0] + r[1] for r in conn.execute("SELECT first_prompt, last_prompt FROM sessions"))
        conn.close()
        self.assertNotIn("hunter2", blob)

    def test_index_file_permissions(self):
        self.claude_session("45444444-4444-4444-4444-444444444444", self.project("x"), [("user", "hi there")])
        self.index()
        self.assertEqual(os.stat(store.index_path()).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(store.index_path().parent).st_mode & 0o777, 0o700)


class IncrementalTests(Env):
    def setUp(self):
        super().setUp()
        self.cwd = self.project("inc")
        self.sid = "55555555-5555-5555-5555-555555555555"
        self.path = self.claude_session(self.sid, self.cwd, [("user", "첫 번째 질문"), ("assistant", "첫 번째 답변")])

    def count(self):
        conn = sqlite3.connect(str(store.index_path()))
        try:
            return conn.execute("SELECT count(*) FROM messages").fetchone()[0]
        finally:
            conn.close()

    def append(self, role, text):
        rec = {"type": role, "sessionId": self.sid, "cwd": self.cwd, "timestamp": iso(time.time()),
               "message": {"role": role, "content": text if role == "user" else [{"type": "text", "text": text}]}}
        with self.path.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def test_unchanged_files_are_skipped(self):
        first = self.index()
        self.assertEqual(first["reread"], 1)
        again = self.index()
        self.assertEqual(again["unchanged"], 1)
        self.assertEqual(again["reread"] + again["appended"], 0)

    def test_append_reads_only_the_new_part(self):
        self.index()
        self.assertEqual(self.count(), 2)
        self.append("user", "두 번째 질문 고양이")
        r = self.index()
        self.assertEqual(r["appended"], 1)
        self.assertEqual(self.count(), 3)  # nothing indexed twice
        self.assertEqual(self.search("고양이")["total"], 1)
        self.assertEqual(self.search()["results"][0]["messages"], 3)

    def test_partial_last_line_waits(self):
        self.index()
        with self.path.open("a") as f:
            f.write('{"type": "user", "sessionId": "x", "message": {"role": "user", "content": "반쯤')
        self.index()
        self.assertEqual(self.count(), 2)
        with self.path.open("a") as f:
            f.write(' 쓴 줄"}}\n')
        self.index()
        self.assertEqual(self.search("반쯤 쓴 줄")["total"], 1)

    def test_equal_sized_rewrite_is_reread(self):
        self.index()
        data = self.path.read_bytes()
        changed = data.replace("첫 번째 답변".encode(), "다른 내용임!".encode())
        self.assertEqual(len(changed), len(data))
        time.sleep(0.01)
        self.path.write_bytes(changed)
        os.utime(self.path, None)
        r = self.index()
        self.assertEqual(r["reread"], 1)
        self.assertEqual(self.search("첫 번째 답변")["total"], 0)
        self.assertEqual(self.search("다른 내용임")["total"], 1)

    def test_bigger_replacement_is_not_treated_as_append(self):
        self.index()
        other = "66666666-6666-6666-6666-666666666666"
        lines = [{"type": "user", "sessionId": other, "cwd": self.cwd, "timestamp": iso(time.time()),
                  "message": {"role": "user", "content": "완전히 다른 대화 " + "x" * 400}}]
        self.path.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines))
        r = self.index()
        self.assertEqual(r["reread"], 1)
        self.assertEqual(self.search("첫 번째")["total"], 0)
        res = self.search()["results"]
        self.assertEqual([x["session_id"] for x in res], [other])

    def test_rewritten_file_is_reread(self):
        self.index()
        self.claude_session(self.sid, self.cwd, [("user", "완전히 새로운 내용")])
        r = self.index()
        self.assertEqual(r["reread"], 1)
        self.assertEqual(self.search("첫 번째")["total"], 0)
        self.assertEqual(self.search("새로운")["total"], 1)
        self.assertEqual(self.count(), 1)

    def test_deleted_history_leaves_the_index(self):
        self.index()
        self.path.unlink()
        r = self.index()
        self.assertEqual(r["removed"], 1)
        self.assertEqual(self.search()["total"], 0)
        self.assertEqual(self.count(), 0)

    def test_excluded_paths_and_coming_back(self):
        self.write_config(exclude_paths=[self.cwd])
        r = self.index()
        self.assertEqual(r["excluded"], 1)
        self.assertEqual(self.search()["total"], 0)
        self.write_config(exclude_paths=[])
        self.index()
        self.assertEqual(self.search()["total"], 1)

    def test_full_rebuild(self):
        self.index()
        r = self.index(full=True)
        self.assertEqual(r["reread"], 1)
        self.assertEqual(self.count(), 2)

    def test_reset_waits_for_a_running_indexer(self):
        self.index()
        with IndexLock(store.index_path().with_name("index.lock")):
            with self.assertRaises(Busy):
                store.reset()
        self.assertTrue(store.index_path().exists())
        store.reset()
        self.assertFalse(store.index_path().exists())
        self.assertTrue(store.index_path().with_name("index.lock").exists())

    def test_old_schema_is_not_read_and_index_rebuilds_it(self):
        self.index()
        conn = sqlite3.connect(str(store.index_path()))
        conn.execute("UPDATE meta SET value='0' WHERE key='schema'")
        conn.commit()
        conn.close()
        with self.assertRaises(FileNotFoundError):
            store.connect(readonly=True)  # search answers "index not ready" instead of crashing
        r = self.index()
        self.assertEqual(r["reread"], 1)
        self.assertEqual(self.search("첫 번째")["total"], 1)

    def test_only_one_indexer_at_a_time(self):
        lock = store.index_path().with_name("index.lock")
        with IndexLock(lock):
            with self.assertRaises(Busy):
                self.index()


class SearchTests(Env):
    def setUp(self):
        super().setUp()
        web, app = self.project("acme-web"), self.project("acme-app")
        now = self.now
        self.claude_session("aaaaaaaa-0000-0000-0000-000000000001", web, [("user", "마이페이지 프로필을 고쳐줘"), ("assistant", "프로필을 수정했습니다")], title="마이페이지 프로필 수정", at=now - 3600)
        self.claude_session("aaaaaaaa-0000-0000-0000-000000000002", app, [("user", "로그인 버그 찾아줘"), ("assistant", "UI 버그와 프로필 이미지 문제를 찾았어요")], title="로그인 오류 조사", at=now - 86400 * 3)
        self.claude_session("aaaaaaaa-0000-0000-0000-000000000003", web, [("user", "결제 화면 리팩터링"), ("assistant", "완료했습니다")], title="결제 리팩터링", at=now - 86400 * 40)
        self.codex_session("01a1f20b-0000-0000-0000-000000000004", app, [("user", "review the payment module"), ("assistant", "Found two bugs in payment")], at=now - 86400 * 10, name="Review payment module")
        self.index()

    def test_empty_query_lists_recent_first(self):
        self.assertEqual(self.titles(), ["마이페이지 프로필 수정", "로그인 오류 조사", "Review payment module", "결제 리팩터링"])

    def test_korean_substring_with_particles(self):
        self.assertEqual(set(self.titles("프로필")), {"마이페이지 프로필 수정", "로그인 오류 조사"})

    def test_title_match_outranks_body_match(self):
        self.assertEqual(self.titles("프로필")[0], "마이페이지 프로필 수정")

    def test_all_words_must_match(self):
        self.assertEqual(self.titles("프로필 이미지"), ["로그인 오류 조사"])
        self.assertEqual(self.titles("프로필 결제"), [])

    def test_short_terms_use_substring_scan(self):
        self.assertEqual(self.titles("UI"), ["로그인 오류 조사"])
        self.assertEqual(self.titles("버그"), ["로그인 오류 조사"])
        self.assertEqual(self.titles("ui"), ["로그인 오류 조사"])  # case-insensitive

    def test_english_case_insensitive_and_phrase(self):
        self.assertEqual(self.titles("PAYMENT"), ["Review payment module"])
        self.assertEqual(self.titles('"two bugs"'), ["Review payment module"])
        self.assertEqual(self.titles('"bugs two"'), [])

    def test_project_and_folder_and_agent_fields(self):
        self.assertEqual(set(self.titles("acme-web")), {"마이페이지 프로필 수정", "결제 리팩터링"})
        self.assertEqual(self.titles("codex"), ["Review payment module"])

    def test_snippet_and_highlights(self):
        r = self.search("이미지")["results"][0]
        self.assertEqual(r["match"], "body")
        joined = "".join(t for t, _ in r["snippet"]["segments"])
        self.assertIn("이미지", joined)
        self.assertTrue(any(h and t == "이미지" for t, h in r["snippet"]["segments"]))
        t = self.search("프로필")["results"][0]
        self.assertTrue(any(h and s == "프로필" for s, h in t["title_segments"]))

    def test_operators(self):
        self.assertEqual(self.titles("agent:codex"), ["Review payment module"])
        self.assertEqual(set(self.titles("agent:claude project:acme-web")), {"마이페이지 프로필 수정", "결제 리팩터링"})
        self.assertEqual(self.titles("after:7d"), ["마이페이지 프로필 수정", "로그인 오류 조사"])
        old = time.strftime("%Y-%m-%d", time.localtime(self.now - 86400 * 20))
        self.assertEqual(self.titles(f"before:{old}"), ["결제 리팩터링"])
        q = search.parse_query("hello project:acme-web agent:기타 status:종료됨 sort:oldest bogus:x")
        self.assertEqual((q.project, q.agent, q.status, q.sort), ("acme-web", "other", "ended", "oldest"))
        self.assertIn("bogus:x", q.terms)

    def test_filter_arguments(self):
        self.assertEqual(self.titles(agent="codex"), ["Review payment module"])
        self.assertEqual(self.titles(since="today"), ["마이페이지 프로필 수정"])
        self.assertEqual(self.titles(since="30d", project="acme-app"), ["로그인 오류 조사", "Review payment module"])

    def test_sorts(self):
        self.assertEqual(self.titles(sort="oldest")[0], "결제 리팩터링")
        self.assertEqual(self.titles(sort="created")[0], "마이페이지 프로필 수정")
        self.assertEqual(self.search("프로필", sort="recent")["sort"], "recent")

    def test_no_results(self):
        r = self.search("존재하지않는검색어zzz")
        self.assertEqual((r["total"], r["results"]), (0, []))

    def test_live_terminals_mark_running_and_stay_apart(self):
        live_info = {"terminals": [
            {"address": "t1", "agent": "claude", "session_id": "aaaaaaaa-0000-0000-0000-000000000001", "space_id": "sp1", "space_name": "same", "tab_id": "tb1", "tab_name": "Claude", "status": "idle", "title": "x"},
            {"address": "t2", "agent": "claude", "session_id": "aaaaaaaa-0000-0000-0000-000000000002", "space_id": "sp2", "space_name": "same", "tab_id": "tb2", "tab_name": "Claude", "status": "working", "title": "x"},
            {"address": "t3", "agent": "pi", "session_id": None, "space_id": "sp3", "space_name": "other", "tab_id": "tb3", "tab_name": "Pi", "status": "idle", "title": "pi agent", "program": "Pi"},
        ]}
        res = self.search(live=live_info)["results"]
        by_title = {r["title"]: r for r in res}
        self.assertEqual(by_title["마이페이지 프로필 수정"]["running"]["address"], "t1")
        self.assertEqual(by_title["로그인 오류 조사"]["running"]["address"], "t2")
        self.assertEqual(by_title["pi agent"]["kind"], "live")
        self.assertIsNone(by_title["결제 리팩터링"]["running"])
        self.assertEqual(self.titles(status="running", live=live_info), ["마이페이지 프로필 수정", "로그인 오류 조사", "pi agent"])
        self.assertNotIn("pi agent", self.titles(status="ended", live=live_info))
        self.assertEqual(self.titles(agent="other", live=live_info), ["pi agent"])
        self.assertEqual(set(self.titles("project:same", live=live_info)), {"마이페이지 프로필 수정", "로그인 오류 조사"})

    def test_preview_centres_on_the_match(self):
        key = store.session_key("claude", "aaaaaaaa-0000-0000-0000-000000000002")
        conn = store.connect(readonly=True)
        try:
            p = search.preview(conn, key, "이미지")
            self.assertTrue(p["ok"])
            self.assertEqual([m["match"] for m in p["messages"]], [False, True])
            missing = search.preview(conn, "local|claude|nope", "")
            self.assertFalse(missing["ok"])
        finally:
            conn.close()

    def test_check_detects_deleted_history_and_folder(self):
        key = store.session_key("claude", "aaaaaaaa-0000-0000-0000-000000000003")
        conn = store.connect(readonly=True)
        try:
            self.assertTrue(search.check(conn, key)["resumable"])
            shutil.rmtree(self.work / "acme-web")
            c = search.check(conn, key)
            self.assertFalse(c["resumable"])
            self.assertEqual(c["why_not_code"], "missing_cwd")
            self.assertIn("working folder is gone", c["why_not"])
            self.assertTrue(c["why_not_detail"].endswith("acme-web"))
            self.assertFalse(search.check(conn, "local|claude|gone")["ok"])
        finally:
            conn.close()


class TextTests(unittest.TestCase):
    def test_snippet_starts_near_the_match(self):
        text = "가" * 300 + " 프로필 수정 " + "나" * 300
        segs = snippet(text, ["프로필"])
        self.assertEqual(segs[0], ("…", False))
        joined = "".join(t for t, _ in segs)
        self.assertLess(joined.index("프로필"), 20)

    def test_snippet_strips_markdown(self):
        segs = snippet("**굵게** `code` ## 제목 [링크](https://x.y) 프로필", ["프로필"])
        joined = "".join(t for t, _ in segs)
        self.assertNotIn("**", joined)
        self.assertNotIn("https://", joined)

    def test_highlight_case_insensitive(self):
        self.assertEqual(highlight("Hello UI world", ["ui"]), [("Hello ", False), ("UI", True), (" world", False)])

    def test_excerpt_keeps_the_match_in_view(self):
        text = "a" * 3000 + " needle " + "b" * 3000
        out = excerpt(text, ["needle"])
        self.assertIn("needle", out)
        self.assertLess(out.index("needle"), 400)


class LiveTests(Env):
    def table(self, rows):
        return live.ProcessTable(rows)

    def test_claude_pid_file_with_matching_start(self):
        sessions = self.claude / "sessions"
        sessions.mkdir()
        (sessions / "200.json").write_text(json.dumps({"pid": 200, "sessionId": "s-ok", "procStart": "Thu Nov 19 06:18:43 2026"}))
        procs = self.table({100: (1, "Thu Nov 19 06:18:40 2026", "zsh"), 200: (100, "Thu Nov 19 06:18:43 2026", "2.1.283")})
        out = live.resolve([{"address": "t1", "pid": 100, "fg_pid": 200, "fg_argv": ["claude"], "program": "claude"}], load_config(), procs)
        self.assertEqual(out["terminals"][0]["session_id"], "s-ok")
        self.assertEqual(out["terminals"][0]["method"], "claude-pid-file")

    def test_stale_pid_file_is_ignored(self):
        sessions = self.claude / "sessions"
        sessions.mkdir()
        (sessions / "200.json").write_text(json.dumps({"pid": 200, "sessionId": "s-old", "procStart": "Mon Nov 16 01:00:00 2026"}))
        procs = self.table({200: (1, "Thu Nov 19 06:18:43 2026", "2.1.283")})
        out = live.resolve([{"address": "t1", "pid": 200, "fg_pid": 200, "fg_argv": ["claude"], "program": "claude"}], load_config(), procs)
        self.assertIsNone(out["terminals"][0]["session_id"])

    def test_pid_file_without_proc_start_needs_a_matching_started_at(self):
        sessions = self.claude / "sessions"
        sessions.mkdir()
        start = "Thu Nov 19 06:18:43 2026"
        began = live._lstart_epoch(start)
        procs = self.table({200: (1, start, "claude")})
        term = [{"address": "t1", "pid": 200, "fg_pid": 200, "fg_argv": ["claude"], "program": "claude"}]
        (sessions / "200.json").write_text(json.dumps({"pid": 200, "sessionId": "s-new", "startedAt": (began + 3) * 1000}))
        self.assertEqual(live.resolve(term, load_config(), procs)["terminals"][0]["session_id"], "s-new")
        (sessions / "200.json").write_text(json.dumps({"pid": 200, "sessionId": "s-stale", "startedAt": (began - 86400) * 1000}))
        self.assertIsNone(live.resolve(term, load_config(), procs)["terminals"][0]["session_id"])
        (sessions / "200.json").write_text(json.dumps({"pid": 200, "sessionId": "s-unknown"}))
        self.assertIsNone(live.resolve(term, load_config(), procs)["terminals"][0]["session_id"])

    def test_codex_process_with_several_rollouts_open(self):
        root = self.codex / "sessions" / "2026" / "11" / "19"
        main_id, sub_id, other_id = ("01a1f20b-aaaa-7000-8000-000000000001", "01a1f20b-bbbb-7000-8000-000000000002", "01a1f20b-cccc-7000-8000-000000000003")
        def rollout(sid, sub):
            p = root / f"rollout-2026-11-19T10-00-00-{sid}.jsonl"
            payload = {"id": sid, "cwd": "/x"}
            if sub:
                payload["source"] = {"subagent": {"parent": main_id}}
            p.write_text(json.dumps({"type": "session_meta", "payload": payload}) + "\n")
            return str(p)
        a, b, c = rollout(main_id, False), rollout(sub_id, True), rollout(other_id, False)

        class Out:
            def __init__(self, text):
                self.stdout = text

        with mock.patch.object(live.subprocess, "run", return_value=Out(f"p10\nn{a}\nn{b}\n")):
            self.assertEqual(live.codex_sessions_by_pid([10], self.codex), {10: main_id})
        with mock.patch.object(live.subprocess, "run", return_value=Out(f"p10\nn{a}\nn{c}\n")):
            self.assertEqual(live.codex_sessions_by_pid([10], self.codex), {10: None})  # two threads: don't guess
        with mock.patch.object(live.subprocess, "run", return_value=Out(f"p10\nn{b}\n")):
            self.assertEqual(live.codex_sessions_by_pid([10], self.codex), {10: None})  # a sub-agent alone isn't it
        # Known-unknown wins over the launch argv: `codex resume A` that now holds two threads stays unresolved.
        procs = self.table({10: (1, "x", "codex")})
        term = [{"address": "t5", "pid": 10, "fg_pid": 10, "fg_argv": ["codex", "resume", main_id], "program": "codex"}]
        with mock.patch.object(live, "codex_sessions_by_pid", return_value={10: None}):
            got = live.resolve(term, load_config(), procs)["terminals"][0]
        self.assertIsNone(got["session_id"])
        self.assertEqual(got["method"], "codex-ambiguous")
        with mock.patch.object(live, "codex_sessions_by_pid", return_value={}):
            self.assertEqual(live.resolve(term, load_config(), procs)["terminals"][0]["session_id"], main_id)

    def test_child_process_of_the_shell(self):
        sessions = self.claude / "sessions"
        sessions.mkdir()
        (sessions / "300.json").write_text(json.dumps({"pid": 300, "sessionId": "s-child", "procStart": "Thu Nov 19 06:00:00 2026"}))
        procs = self.table({100: (1, "x", "zsh"), 300: (100, "Thu Nov 19 06:00:00 2026", "claude")})
        out = live.resolve([{"address": "t9", "pid": 100, "fg_pid": None, "fg_argv": ["/bin/zsh", "claude"], "app": "claude-code"}], load_config(), procs)
        self.assertEqual(out["terminals"][0]["session_id"], "s-child")

    def test_argv_fallback_and_agent_detection(self):
        self.assertEqual(live.argv_session(["codex", "resume", "01a1f20b-4ca5-7793-bba3-b10e946bfb82"]), "01a1f20b-4ca5-7793-bba3-b10e946bfb82")
        self.assertEqual(live.argv_session(["claude", "--resume=11111111-1111-1111-1111-111111111111"]), "11111111-1111-1111-1111-111111111111")
        self.assertIsNone(live.argv_session(["rg", "11111111-1111-1111-1111-111111111111"]))
        self.assertEqual(live.agent_of({"app": "codex"}), "codex")
        self.assertEqual(live.agent_of({"program": "pi"}), "pi")
        self.assertEqual(live.agent_of({"fg_argv": ["/opt/bin/claude", "-c"]}), "claude")
        # A path argument that merely contains "claude" doesn't make Codex a Claude terminal.
        codex_argv = ["/x/bin/codex", "--no-daemon", "resume", "id", "-C", "/private/tmp/claude-501/scratch"]
        self.assertEqual(live.agent_of({"fg_argv": codex_argv}), "codex")
        self.assertEqual(live.agent_of({"fg_argv": codex_argv, "program": "codex"}), "codex")
        self.assertEqual(live.agent_of({"fg_argv": ["/bin/zsh", "-lic", "x", "/bin/zsh", "/u/.local/bin/claude"]}), "claude")
        self.assertEqual(live.agent_of({"fg_argv": ["nvim", "/src/codex"]}), "other")

    def test_remember_records_the_space(self):
        self.claude_session("bbbbbbbb-0000-0000-0000-000000000001", self.project("p"), [("user", "hi")])
        self.index()
        live.remember([{"address": "t1", "space_id": "sp9", "space_name": "My Space", "tab_id": "tb9", "tab_name": "T"}],
                      [{"address": "t1", "agent": "claude", "session_id": "bbbbbbbb-0000-0000-0000-000000000001"}])
        r = self.search()["results"][0]
        self.assertEqual(r["space_name"], "My Space")
        self.assertEqual(r["last_space_id"], "sp9")
        self.assertEqual(self.titles("project:my space"), ["hi"])


if __name__ == "__main__":
    unittest.main()
