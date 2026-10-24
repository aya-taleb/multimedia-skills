"""Unit tests for skills/youtube-audit/scripts/channel_stats.py."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "youtube-audit", "scripts"))
import channel_stats as cs  # noqa: E402

EXPORT = """Content,Video title,Video publish time,Duration,Views,Impressions,Impressions click-through rate (%),Average view duration,Average percentage viewed (%),Subscribers gained
Total,,,,10450,180000,4.1,2:10,,95
a1,How I price lunch subscriptions,"Sep 2, 2026",612,4200,52000,6.8,4:05,40.0,48
a2,Our kitchen tour,"Sep 9, 2026",305,600,30000,1.6,1:10,23.0,2
a3,3 mistakes with office catering,"Sep 16, 2026",540,2100,31000,5.2,3:30,38.9,20
a4,Weekly menu planning,"Sep 23, 2026",480,1800,29000,4.9,1:05,13.5,12
a5,Behind the truck,"Sep 30, 2026",420,1750,38000,3.6,2:40,38.1,13
"""


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Parsing(unittest.TestCase):
    def test_times(self):
        self.assertEqual(cs.parse_time("4:05"), 245)
        self.assertEqual(cs.parse_time("1:00:05"), 3605)
        self.assertEqual(cs.parse_time("612"), 612)
        self.assertIsNone(cs.parse_time(""))

    def test_numbers(self):
        self.assertEqual(cs.parse_num("1,234"), 1234)
        self.assertEqual(cs.parse_num("6.8%"), 6.8)
        self.assertIsNone(cs.parse_num("-"))
        self.assertIsNone(cs.parse_num("n/a"))

    def test_columns(self):
        cols = cs.find_columns(["Content", "Video title", "Views", "Impressions click-through rate (%)"])
        self.assertEqual(cols["title"], 1)
        self.assertEqual(cols["video_id"], 0)
        self.assertEqual(cols["ctr"], 3)


class Summary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "export.csv")
        write(self.path, EXPORT)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_total_row_skipped(self):
        videos, _ = cs.load(self.path)
        self.assertEqual(len(videos), 5)

    def test_medians_and_flags(self):
        videos, cols = cs.load(self.path)
        s = cs.summarize(videos, cols)
        self.assertEqual(s["medians"]["views"], 1800)
        self.assertEqual(s["medians"]["ctr"], 4.9)
        flagged = {f["title"]: f["why"] for f in s["flags"]}
        self.assertIn("Our kitchen tour", flagged)
        self.assertTrue(any("click rate 1.6%" in w for w in flagged["Our kitchen tour"]))
        self.assertIn("Weekly menu planning", flagged)
        self.assertTrue(any("viewed 14%" in w for w in flagged["Weekly menu planning"]))
        self.assertEqual(s["standouts"][0]["title"], "How I price lunch subscriptions")
        self.assertIn("support.google.com/youtube/answer/7628154", s["funnel"]["click"])

    def test_small_sample_note(self):
        write(self.path, "\n".join(EXPORT.splitlines()[:4]) + "\n")
        videos, cols = cs.load(self.path)
        s = cs.summarize(videos, cols)
        self.assertTrue(any("weak" in n for n in s["notes"]))

    def test_apv_computed_when_missing(self):
        write(self.path, "Video title,Duration,Views,Average view duration\nA,200,100,1:40\n")
        videos, cols = cs.load(self.path)
        self.assertEqual(videos[0]["apv"], 50.0)
        s = cs.summarize(videos, cols)
        self.assertTrue(any("Missing columns" in n for n in s["notes"]))

    def test_no_views_column(self):
        write(self.path, "Title,Likes\nA,3\n")
        with self.assertRaises(SystemExit) as ctx:
            cs.load(self.path)
        self.assertIn("Views", str(ctx.exception))

    def test_cli_text_and_json(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cs.main([self.path])
        self.assertEqual(code, 0)
        self.assertIn("Channel medians", buf.getvalue())
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cs.main([self.path, "--json"])
        data = json.loads(buf.getvalue())
        self.assertEqual(data["summary"]["videos"], 5)

    def test_bom_and_blank_lines(self):
        write(self.path, "﻿" + EXPORT + "\n\n")
        videos, _ = cs.load(self.path)
        self.assertEqual(len(videos), 5)


if __name__ == "__main__":
    unittest.main()
