"""Regression tests for doctor_core — guards the bugs that motivated the rewrite.

Run: python3 -m unittest context-doctor/test_doctor_core.py
 or: python3 context-doctor/test_doctor_core.py
"""

import os
import json
import tempfile
import unittest

import doctor_core


def _write(dirpath, name, records):
    os.makedirs(dirpath, exist_ok=True)
    fp = os.path.join(dirpath, name)
    with open(fp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return fp


def _assistant(usage, sid="s1", ts="2026-06-28T00:00:00Z"):
    return {"type": "assistant", "sessionId": sid, "timestamp": ts,
            "message": {"usage": usage}}


class TestIterationsDuplication(unittest.TestCase):
    def test_iterations_not_double_counted(self):
        # usage carries the canonical values AND an iterations[] copy.
        usage = {
            "input_tokens": 4548,
            "output_tokens": 1498,
            "cache_read_input_tokens": 8118,
            "cache_creation_input_tokens": 5790,
            "iterations": [{
                "input_tokens": 4548, "output_tokens": 1498,
                "cache_read_input_tokens": 8118,
                "cache_creation_input_tokens": 5790,
            }],
        }
        with tempfile.TemporaryDirectory() as d:
            fp = _write(d, "sess.jsonl", [_assistant(usage)])
            turns = doctor_core.parse_session(fp)
        self.assertEqual(len(turns), 1)
        t = turns[0]
        self.assertEqual(t["input"], 4548)       # not 9096
        self.assertEqual(t["output"], 1498)
        self.assertEqual(t["cache_read"], 8118)
        self.assertEqual(t["cache_creation"], 5790)


class TestConversationalTextIgnored(unittest.TestCase):
    def test_text_mentioning_token_field_is_ignored(self):
        # A user turn whose text literally contains `"input_tokens": 5000`
        # must not be counted (it is not an assistant usage record).
        chatter = {
            "type": "user", "sessionId": "s1", "timestamp": "2026-06-28T00:00:00Z",
            "message": {"content": 'discussing "input_tokens": 5000 here'},
        }
        real = _assistant({"input_tokens": 10, "output_tokens": 20,
                           "cache_read_input_tokens": 0,
                           "cache_creation_input_tokens": 0})
        with tempfile.TemporaryDirectory() as d:
            fp = _write(d, "sess.jsonl", [chatter, real])
            turns = doctor_core.parse_session(fp)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["input"], 10)


class TestSessionsLayoutProbe(unittest.TestCase):
    def test_sessions_dir_buckets_to_project_hash(self):
        with tempfile.TemporaryDirectory() as d:
            proj = os.path.join(d, "-home-user-repo-myproj")
            sessions = os.path.join(proj, "sessions")
            fp = _write(sessions, "abcd1234.jsonl",
                        [_assistant({"input_tokens": 1, "output_tokens": 1,
                                     "cache_read_input_tokens": 0,
                                     "cache_creation_input_tokens": 0})])
            self.assertEqual(doctor_core.project_for(fp), "-home-user-repo-myproj")
            self.assertEqual(doctor_core.parse_session(fp)[0]["project"],
                             "-home-user-repo-myproj")

    def test_flat_layout_buckets_to_parent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = os.path.join(d, "-home-user-repo-flat")
            fp = _write(proj, "abcd1234.jsonl",
                        [_assistant({"input_tokens": 1, "output_tokens": 1,
                                     "cache_read_input_tokens": 0,
                                     "cache_creation_input_tokens": 0})])
            self.assertEqual(doctor_core.project_for(fp), "-home-user-repo-flat")


class TestSummaryShape(unittest.TestCase):
    def test_summary_has_full_schema_and_tolerates_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            proj = os.path.join(d, "-proj")
            os.makedirs(proj)
            fp = os.path.join(proj, "s.jsonl")
            with open(fp, "w", encoding="utf-8") as f:
                f.write("not json\n")  # malformed -> skipped, no crash
                f.write(json.dumps(_assistant({
                    "input_tokens": 100, "output_tokens": 200,
                    "cache_read_input_tokens": 300000,
                    "cache_creation_input_tokens": 400,
                })) + "\n")
            summary = doctor_core.build_summary(days=3650, claude_dir=d)
        for key in ("period", "sessions_analyzed", "total_turns",
                    "avg_final_context_k", "max_context_k", "sessions_over_200k",
                    "sessions_over_400k", "cache_hit_rate_pct", "cache_misses",
                    "total_input_k", "total_output_k", "total_cache_read_k",
                    "total_cache_creation_k", "extra_tokens_from_misses_k",
                    "top_expensive"):
            self.assertIn(key, summary)
        self.assertEqual(summary["sessions_analyzed"], 1)
        self.assertEqual(summary["total_turns"], 1)
        self.assertEqual(summary["total_output_k"], 0)  # 200 / 1000 truncates


if __name__ == "__main__":
    unittest.main()
