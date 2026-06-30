"""Slice 1 tests — warehouse `turns` columns + offset-aware generator.

Covers the parser delta added for the metrics warehouse: the richer `turns`
columns on each row, `<synthetic>` flagging, byte-offset incremental resume via
`iter_session`, and partial-trailing-line handling. These are additive; the
existing `test_doctor_core.py` regression suite remains the source of truth for
the legacy summary path.

Run: python3 context-doctor/test_doctor_core_warehouse.py
"""

import os
import json
import tempfile
import unittest

import doctor_core


def _drain(gen):
    """Exhaust a generator, returning (rows, return_value)."""
    rows = []
    while True:
        try:
            rows.append(next(gen))
        except StopIteration as stop:
            return rows, stop.value


def _write_lines(fp, records):
    with open(fp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _append_lines(fp, records):
    with open(fp, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _assistant(usage, sid="s1", ts="2026-06-28T00:00:00Z", **message_extra):
    msg = {"usage": usage}
    msg.update(message_extra)
    return {"type": "assistant", "sessionId": sid, "timestamp": ts, "message": msg}


_USAGE = {"input_tokens": 100, "output_tokens": 200,
          "cache_read_input_tokens": 300, "cache_creation_input_tokens": 400}


class TestNewColumns(unittest.TestCase):
    def test_rich_columns_populated(self):
        rec = {
            "type": "assistant",
            "sessionId": "sess-1",
            "timestamp": "2026-06-28T12:00:00Z",
            "uuid": "u-123",
            "parentUuid": "u-000",
            "gitBranch": "feature/x",
            "cwd": "/home/u/repo",
            "message": {
                "model": "claude-opus-4-8",
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 600,
                    "cache_creation_input_tokens": 300,
                    "server_tool_use": {
                        "web_search_requests": 2,
                        "web_fetch_requests": 5,
                    },
                },
                "content": [
                    {"type": "text", "text": "hi"},
                    {"type": "thinking", "thinking": "..."},
                    {"type": "tool_use", "name": "Bash"},
                    {"type": "tool_use", "name": "Read"},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            _write_lines(fp, [rec])
            rows = doctor_core.parse_session(fp)
        self.assertEqual(len(rows), 1)
        t = rows[0]
        self.assertEqual(t["uuid"], "u-123")
        self.assertEqual(t["parent_uuid"], "u-000")
        self.assertEqual(t["git_branch"], "feature/x")
        self.assertEqual(t["cwd"], "/home/u/repo")
        self.assertEqual(t["model"], "claude-opus-4-8")
        self.assertEqual(t["stop_reason"], "end_turn")
        self.assertIs(t["is_synthetic"], False)
        self.assertEqual(t["n_text"], 1)
        self.assertEqual(t["n_thinking"], 1)
        self.assertEqual(t["n_tool_use"], 2)
        self.assertEqual(t["web_search"], 2)
        self.assertEqual(t["web_fetch"], 5)
        self.assertEqual(t["source_file"], fp)
        # context = 600 + 100 + 300 = 1000; hit_pct = 600/1000*100 = 60.0
        self.assertEqual(t["context"], 1000)
        self.assertAlmostEqual(t["hit_pct"], 60.0)
        # ctx 1000 < CTX_MIN_FOR_MISS (5000) -> not a miss
        self.assertIs(t["is_miss"], False)

    def test_hit_pct_none_when_context_zero(self):
        usage = {"input_tokens": 0, "output_tokens": 10,
                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            _write_lines(fp, [_assistant(usage)])
            rows = doctor_core.parse_session(fp)
        self.assertIsNone(rows[0]["hit_pct"])
        self.assertIs(rows[0]["is_miss"], False)

    def test_is_miss_true_for_large_low_hit_context(self):
        # ctx = 10000 (>5000), hit_pct = 100/10000*100 = 1.0 (<20) -> miss
        usage = {"input_tokens": 9900, "output_tokens": 10,
                 "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0}
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            _write_lines(fp, [_assistant(usage)])
            rows = doctor_core.parse_session(fp)
        self.assertEqual(rows[0]["context"], 10000)
        self.assertAlmostEqual(rows[0]["hit_pct"], 1.0)
        self.assertIs(rows[0]["is_miss"], True)

    def test_missing_content_and_server_tool_use_default_zero(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            _write_lines(fp, [_assistant(_USAGE)])
            rows = doctor_core.parse_session(fp)
        t = rows[0]
        self.assertEqual(t["n_tool_use"], 0)
        self.assertEqual(t["n_thinking"], 0)
        self.assertEqual(t["n_text"], 0)
        self.assertEqual(t["web_search"], 0)
        self.assertEqual(t["web_fetch"], 0)


class TestSyntheticFlagging(unittest.TestCase):
    def test_synthetic_model_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            _write_lines(fp, [_assistant(_USAGE, model="<synthetic>")])
            rows = doctor_core.parse_session(fp)
        self.assertIs(rows[0]["is_synthetic"], True)
        self.assertEqual(rows[0]["model"], "<synthetic>")


class TestOffsetResume(unittest.TestCase):
    def test_resume_yields_only_tail(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            n = 3
            _write_lines(fp, [_assistant(_USAGE, sid="s%d" % i) for i in range(n)])

            rows1, ret1 = _drain(doctor_core.iter_session(fp))
            self.assertEqual(len(rows1), n)
            end_offset, end_line_no = ret1
            self.assertEqual(end_line_no, n)
            self.assertEqual(end_offset, os.path.getsize(fp))

            m = 2
            _append_lines(fp, [_assistant(_USAGE, sid="t%d" % i) for i in range(m)])

            rows2, ret2 = _drain(
                doctor_core.iter_session(fp, start_offset=end_offset,
                                         start_line_no=end_line_no))
            self.assertEqual(len(rows2), m)
            self.assertEqual([r["session"] for r in rows2], ["t0", "t1"])
            end_offset2, end_line_no2 = ret2
            # absolute line numbering continues: N + M
            self.assertEqual(end_line_no2, n + m)
            self.assertEqual(end_offset2, os.path.getsize(fp))


class TestPartialTrailingLine(unittest.TestCase):
    def test_partial_line_not_consumed_until_newline_arrives(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            first = json.dumps(_assistant(_USAGE, sid="a")).encode("utf-8") + b"\n"
            partial = json.dumps(_assistant(_USAGE, sid="b")).encode("utf-8")  # no \n
            with open(fp, "wb") as f:
                f.write(first)
                f.write(partial)

            rows1, ret1 = _drain(doctor_core.iter_session(fp))
            self.assertEqual(len(rows1), 1)
            self.assertEqual(rows1[0]["session"], "a")
            end_offset, end_line_no = ret1
            # offset stops before the partial line.
            self.assertEqual(end_offset, len(first))
            self.assertEqual(end_line_no, 1)

            # append the missing newline (+ a further full line); resume.
            second_tail = b"\n" + json.dumps(_assistant(_USAGE, sid="c")).encode("utf-8") + b"\n"
            with open(fp, "ab") as f:
                f.write(second_tail)

            rows2, ret2 = _drain(
                doctor_core.iter_session(fp, start_offset=end_offset,
                                         start_line_no=end_line_no))
            self.assertEqual([r["session"] for r in rows2], ["b", "c"])
            self.assertEqual(ret2[1], 3)
            self.assertEqual(ret2[0], os.path.getsize(fp))


class TestParseEvents(unittest.TestCase):
    """Slice 2 — `parse_events` projection of curated non-turn records."""

    def _events(self, records):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            _write_lines(fp, records)
            rows, ret = _drain(doctor_core.parse_events(fp))
        return rows, ret

    def test_one_of_each_kept_type(self):
        assistant = {
            "type": "assistant", "sessionId": "s1",
            "timestamp": "2026-06-28T00:00:00Z", "uuid": "turn-uuid-1",
            "message": {"content": [
                {"type": "text", "text": "hi"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                {"type": "tool_use", "name": "Skill",
                 "input": {"skill": "context-doctor"}},
            ]},
        }
        user_prompt = {"type": "user", "sessionId": "s1",
                       "timestamp": "2026-06-28T00:00:01Z",
                       "message": {"content": "do the thing"}}
        user_result = {"type": "user", "sessionId": "s1",
                       "timestamp": "2026-06-28T00:00:02Z",
                       "promptId": "p-9", "toolUseResult": {"ok": True},
                       "message": {"content": [
                           {"type": "tool_result", "content": "a"},
                           {"type": "tool_result", "content": "b"},
                       ]}}
        sys_dur = {"type": "system", "subtype": "turn_duration", "sessionId": "s1",
                   "timestamp": "2026-06-28T00:00:03Z",
                   "durationMs": 1234, "messageCount": 7}
        sys_compact = {"type": "system", "subtype": "compact_boundary",
                       "sessionId": "s1", "timestamp": "2026-06-28T00:00:04Z"}
        sys_local = {"type": "system", "subtype": "local_command", "sessionId": "s1",
                     "timestamp": "2026-06-28T00:00:05Z",
                     "content": "<command-name>/context</command-name>"}
        att_plan = {"type": "attachment", "sessionId": "s1",
                    "timestamp": "2026-06-28T00:00:06Z",
                    "attachment": {"type": "plan_mode", "reminderType": "full"}}
        att_queued = {"type": "attachment", "sessionId": "s1",
                      "timestamp": "2026-06-28T00:00:07Z",
                      "attachment": {"type": "queued_command",
                                     "prompt": "/compact", "commandMode": "prompt"}}
        mode = {"type": "mode", "sessionId": "s1", "mode": "plan"}
        perm = {"type": "permission-mode", "sessionId": "s1",
                "permissionMode": "acceptEdits"}

        rows, _ = self._events([
            assistant, user_prompt, user_result, sys_dur, sys_compact,
            sys_local, att_plan, att_queued, mode, perm,
        ])
        triples = [(r["type"], r["subtype"], r["key"], r["num"], r["ref"])
                   for r in rows]

        # assistant line yields TWO tool_use events.
        self.assertEqual(triples[0], ("tool_use", "Bash", None, None, "turn-uuid-1"))
        self.assertEqual(
            triples[1],
            ("tool_use", "Skill", "context-doctor", None, "turn-uuid-1"))
        self.assertEqual(triples[2], ("user", "prompt", None, None, None))
        self.assertEqual(triples[3], ("user", "tool_result", None, 2, "p-9"))
        self.assertEqual(triples[4], ("system", "turn_duration", "7", 1234, None))
        self.assertEqual(
            triples[5], ("system", "compact_boundary", None, None, None))
        # local_command reclassified to type="command"; name from <command-name>.
        self.assertEqual(triples[6], ("command", "local_command", "/context",
                                      None, None))
        self.assertEqual(triples[7], ("attachment", "plan_mode", None, None, None))
        # queued_command reclassified to type="command".
        self.assertEqual(triples[8], ("command", "queued_command", "/compact",
                                      None, None))
        self.assertEqual(triples[9], ("mode", None, "plan", None, None))
        self.assertEqual(
            triples[10], ("permission-mode", None, "acceptEdits", None, None))
        self.assertEqual(len(rows), 11)

        # every row carries the full key set and session/ts/line_no.
        for r in rows:
            self.assertEqual(set(r.keys()),
                             {"session_id", "ts", "line_no", "type",
                              "subtype", "key", "num", "ref"})
            self.assertEqual(r["session_id"], "s1")
        # control records (mode/permission-mode) keep ts None (not fabricated).
        self.assertIsNone(rows[9]["ts"])
        self.assertIsNone(rows[10]["ts"])
        # line_no is absolute: assistant is line 1 -> both its events carry 1.
        self.assertEqual(rows[0]["line_no"], 1)
        self.assertEqual(rows[1]["line_no"], 1)
        self.assertEqual(rows[2]["line_no"], 2)  # user_prompt is line 2

    def test_unknown_types_ignored(self):
        records = [
            {"type": "ai-title", "sessionId": "s1", "aiTitle": "Some title"},
            {"type": "file-history-snapshot", "messageId": "m1",
             "snapshot": {}, "isSnapshotUpdate": False},
        ]
        rows, ret = self._events(records)
        self.assertEqual(rows, [])
        # no crash; offset reaches EOF, two lines consumed.
        self.assertEqual(ret[1], 2)

    def test_offset_resume_yields_only_tail(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "sess.jsonl")
            _write_lines(fp, [
                {"type": "mode", "sessionId": "s1", "mode": "plan"},
                {"type": "user", "sessionId": "s1",
                 "timestamp": "2026-06-28T00:00:00Z",
                 "message": {"content": "first prompt"}},
            ])
            rows1, ret1 = _drain(doctor_core.parse_events(fp))
            self.assertEqual([r["type"] for r in rows1], ["mode", "user"])
            end_offset, end_line_no = ret1
            self.assertEqual(end_line_no, 2)
            self.assertEqual(end_offset, os.path.getsize(fp))

            _append_lines(fp, [
                {"type": "system", "subtype": "compact_boundary",
                 "sessionId": "s1", "timestamp": "2026-06-28T00:00:01Z"},
                {"type": "permission-mode", "sessionId": "s1",
                 "permissionMode": "default"},
            ])
            rows2, ret2 = _drain(doctor_core.parse_events(
                fp, start_offset=end_offset, start_line_no=end_line_no))
            self.assertEqual([r["type"] for r in rows2],
                             ["system", "permission-mode"])
            # absolute line numbering continues from the prior end.
            self.assertEqual(rows2[0]["line_no"], 3)
            self.assertEqual(rows2[1]["line_no"], 4)
            self.assertEqual(ret2[1], 4)
            self.assertEqual(ret2[0], os.path.getsize(fp))


if __name__ == "__main__":
    unittest.main()
