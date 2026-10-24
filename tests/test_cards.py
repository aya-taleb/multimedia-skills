"""Unit tests for skills/talking-head-cards/scripts/cards.py. Real ffmpeg is used only if installed."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "talking-head-cards", "scripts"))
import cards as cd  # noqa: E402


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()

TRANSCRIPT = {"meta": {"duration": 20.0}, "segments": [
    {"start": 0.0, "end": 4.0, "text": "Most founders price for the first customer."},
    {"start": 4.2, "end": 9.0, "text": "But you price for the last customer, the one who has ten other options.",
     "words": [{"start": 4.2, "end": 4.4, "word": "But"}, {"start": 4.5, "end": 4.7, "word": "you"},
               {"start": 4.8, "end": 5.1, "word": "price"}, {"start": 5.2, "end": 5.4, "word": "for"},
               {"start": 5.5, "end": 5.7, "word": "the"}, {"start": 5.8, "end": 6.1, "word": "last"},
               {"start": 6.2, "end": 6.6, "word": "customer,"}]},
    {"start": 9.5, "end": 14.0, "text": "We had three offices in the first month."},
    {"start": 14.5, "end": 20.0, "text": "Churn is just people leaving."},
]}


def plan(*cards, style=None):
    return {"style": style or {}, "cards": list(cards)}


GOOD = [
    {"start": 4.8, "end": 8.4, "type": "point", "text": "Price for the last customer", "quote": "price for the last customer"},
    {"start": 9.6, "end": 13.0, "type": "number", "text": "3 offices", "sub": "first month", "quote": "three offices"},
    {"start": 14.6, "end": 18.0, "type": "term", "text": "Churn", "sub": "people leaving", "quote": "churn is just people leaving"},
]


class Checks(unittest.TestCase):
    def test_good_plan(self):
        errors, warnings = cd.check(plan(*GOOD), TRANSCRIPT)
        self.assertEqual(errors, [])

    def test_too_short(self):
        c = dict(GOOD[0], end=5.3)
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("read it" in e for e in errors))

    def test_overlap(self):
        a = dict(GOOD[0])
        b = dict(GOOD[1], start=8.0)
        errors, _ = cd.check(plan(a, b), TRANSCRIPT)
        self.assertTrue(any("overlaps" in e for e in errors))

    def test_past_end(self):
        c = dict(GOOD[2], end=25.0)
        errors, _ = cd.check(plan(c), TRANSCRIPT, {"duration": 20.0})
        self.assertTrue(any("after the video ends" in e for e in errors))

    def test_invented_number(self):
        c = dict(GOOD[1], text="40% more offices")
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("number 40" in e for e in errors))

    def test_number_word_matches_digit(self):
        errors, _ = cd.check(plan(GOOD[1]), TRANSCRIPT)
        self.assertEqual(errors, [])

    def test_quote_not_in_transcript(self):
        c = dict(GOOD[0], quote="charge more and win")
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("not in the transcript" in e for e in errors))

    def test_quote_from_far_away_fails(self):
        c = dict(GOOD[2], quote="most founders price for the first customer")
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("not in the transcript" in e for e in errors))

    def test_missing_quote(self):
        c = dict(GOOD[0])
        del c["quote"]
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("add \"quote\"" in e for e in errors))

    def test_quote_card_must_be_verbatim(self):
        c = {"start": 4.8, "end": 8.4, "type": "quote", "text": "Always price high", "quote": "price for the last customer"}
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("exact words" in e for e in errors))
        c["text"] = "you price for the last customer"
        self.assertEqual(cd.check(plan(c), TRANSCRIPT)[0], [])

    def test_text_too_long(self):
        c = dict(GOOD[1], text="3 offices and counting fast")
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("characters" in e for e in errors))

    def test_list_needs_items(self):
        c = {"start": 0.5, "end": 3.5, "type": "list", "text": "Pricing", "items": ["one"], "quote": "most founders"}
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("2 or 3 items" in e for e in errors))

    def test_bad_type_and_position(self):
        c = dict(GOOD[0], type="meme", position="middle")
        errors, _ = cd.check(plan(c), TRANSCRIPT)
        self.assertTrue(any("type must be" in e for e in errors))
        self.assertTrue(any("position must be" in e for e in errors))

    def test_timing_drift_warns(self):
        c = dict(GOOD[0], start=2.5, end=6.5)
        errors, warnings = cd.check(plan(c), TRANSCRIPT)
        self.assertEqual(errors, [])
        self.assertTrue(any("away from when the words are said" in w for w in warnings))

    def test_empty(self):
        self.assertTrue(cd.check({"cards": []})[0])


class Ass(unittest.TestCase):
    def test_colors(self):
        self.assertEqual(cd.ass_color("#FF6B4A"), "&H004A6BFF")
        self.assertEqual(cd.ass_color("#000000", 0.5), "&H80000000")
        with self.assertRaises(SystemExit):
            cd.ass_color("red")

    def test_time(self):
        self.assertEqual(cd.ass_time(3723.456), "1:02:03.46")

    def test_build_vertical(self):
        text = cd.build_ass(plan(*GOOD), {"width": 1080, "height": 1920})
        self.assertIn("PlayResX: 1080", text)
        self.assertEqual(text.count("Dialogue:"), 3)
        self.assertIn(r"{\rBig}3 offices", text)
        mv = int(text.split("Dialogue:")[1].split(",")[7])
        self.assertGreaterEqual(mv, int(1920 * 0.22))  # above the app buttons

    def test_escapes_braces(self):
        c = dict(GOOD[0], text="Price {last}")
        text = cd.build_ass(plan(c), {"width": 1920, "height": 1080})
        self.assertIn("Price (last)", text)

    def test_layout_wide_vs_tall(self):
        self.assertLess(cd.layout("lower", 1920, 1080)[3], cd.layout("lower", 1080, 1920)[3])
        self.assertEqual(cd.layout("upper", 1920, 1080)[0], 8)

    def test_render_cmd_keeps_audio(self):
        cmd = cd.render_cmd("in.mp4", "/tmp/a b.ass", "out.mp4")
        self.assertIn("copy", cmd)
        self.assertIn("ass='/tmp/a b.ass'", cmd)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cards = os.path.join(self.tmp, "cards.json")
        self.tr = os.path.join(self.tmp, "t.json")
        write_json(self.cards, plan(*GOOD))
        write_json(self.tr, TRANSCRIPT)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cd.main(list(argv))
        return code, buf.getvalue()

    def test_check_ok(self):
        code, text = self.cli("check", self.cards, "--transcript", self.tr)
        self.assertEqual(code, 0, text)

    def test_check_blocks_bad(self):
        write_json(self.cards, plan(dict(GOOD[1], text="99 offices")))
        code, text = self.cli("check", self.cards, "--transcript", self.tr)
        self.assertEqual(code, 1)
        self.assertIn("Nothing was rendered", text)

    def test_ass_file(self):
        out = os.path.join(self.tmp, "c.ass")
        code, _ = self.cli("ass", self.cards, "--out", out, "--transcript", self.tr)
        self.assertEqual(code, 0)
        self.assertTrue(read_text(out).startswith("[Script Info]"))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_real_render(self):
        video = os.path.join(self.tmp, "in.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=320x568:d=20:r=10",
                        "-f", "lavfi", "-i", "sine=frequency=200:duration=20", "-shortest", "-c:v", "libx264",
                        "-c:a", "aac", video], check=True)
        out = os.path.join(self.tmp, "out.mp4")
        code, text = self.cli("render", self.cards, "--video", video, "--out", out, "--transcript", self.tr)
        self.assertEqual(code, 0, text)
        self.assertGreater(os.path.getsize(out), 1000)
        info = cd.probe(out)
        self.assertEqual((info["width"], info["height"]), (320, 568))
        code, text = self.cli("frames", self.cards, "--video", video, "--out", os.path.join(self.tmp, "fr"))
        self.assertEqual(code, 0, text)
        self.assertEqual(len([f for f in os.listdir(os.path.join(self.tmp, "fr")) if f.endswith(".png")]), 3)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_refuses_overwrite(self):
        video = os.path.join(self.tmp, "in.mp4")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=20:r=5",
                        "-c:v", "libx264", video], check=True)
        code, _ = self.cli("render", self.cards, "--video", video, "--out", video)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
