"""Unit tests for skills/launch-video/scripts/plan.py."""
import contextlib
import copy
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "launch-video", "scripts"))
import plan as pl  # noqa: E402

PLAN = {
    "title": "Tally launch", "format": "vertical",
    "brand": {"bg": "#1B2433", "ink": "#FFFFFF", "accent": "#E8664F", "font": "Inter"},
    "voice": "founder", "cta": "Try Tally free at tallyapp.io",
    "claims": [{"text": "212 teams in beta", "source": "founder/context.md"}],
    "scenes": [
        {"id": "hook", "seconds": 4, "vo": "Your standup runs long because nobody says they're stuck.",
         "on_screen": "Nobody says they're stuck", "visual": "Tally board", "motion": "slow push in"},
        {"id": "problem", "seconds": 7, "vo": "So the meeting turns into a read-out and the real blocker waits a day.",
         "on_screen": "Blockers wait a day", "visual": "founder to camera"},
        {"id": "product", "seconds": 9, "vo": "Tally asks one question first: where are you stuck? Everyone sees the answer.",
         "on_screen": "Where are you stuck?", "visual": "screen recording"},
        {"id": "proof", "seconds": 5, "vo": "212 teams used it in our beta.", "on_screen": "212 teams in beta",
         "visual": "end of beta stat card"},
        {"id": "cta", "seconds": 6, "vo": "Try Tally free at tallyapp dot io.", "on_screen": "tallyapp.io",
         "visual": "logo end card"},
    ],
}


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


class Checks(unittest.TestCase):
    def test_good(self):
        errors, _ = pl.check(PLAN)
        self.assertEqual(errors, [])

    def test_too_short_total(self):
        p = copy.deepcopy(PLAN)
        p["scenes"] = p["scenes"][:2]
        errors, _ = pl.check(p)
        self.assertTrue(any("Total length" in e for e in errors))

    def test_too_long_total(self):
        p = copy.deepcopy(PLAN)
        p["scenes"] += [dict(p["scenes"][1], id="x%d" % i) for i in range(6)]
        errors, _ = pl.check(p)
        self.assertTrue(any("Total length" in e for e in errors))

    def test_vo_too_long_for_scene(self):
        p = copy.deepcopy(PLAN)
        p["scenes"][0]["vo"] = "word " * 30
        errors, _ = pl.check(p)
        self.assertTrue(any("words of voiceover" in e for e in errors))

    def test_text_only_ignores_vo_length(self):
        p = copy.deepcopy(PLAN)
        p["voice"] = "none"
        p["scenes"][0]["vo"] = "word " * 30
        self.assertEqual(pl.check(p)[0], [])

    def test_unsourced_number(self):
        p = copy.deepcopy(PLAN)
        p["scenes"][3]["on_screen"] = "Saves 40% of meeting time"
        errors, _ = pl.check(p)
        self.assertTrue(any("40%" in e for e in errors))

    def test_placeholder_number_allowed(self):
        p = copy.deepcopy(PLAN)
        p["scenes"][3]["on_screen"] = "Saves {{your number}} hours"
        self.assertEqual(pl.check(p)[0], [])

    def test_claim_needs_source(self):
        p = copy.deepcopy(PLAN)
        p["claims"][0]["source"] = ""
        errors, _ = pl.check(p)
        self.assertTrue(any("no source" in e for e in errors))

    def test_long_on_screen(self):
        p = copy.deepcopy(PLAN)
        p["scenes"][1]["on_screen"] = "x" * 60
        self.assertTrue(any("characters" in e for e in pl.check(p)[0]))

    def test_needs_cta_and_visual(self):
        p = copy.deepcopy(PLAN)
        p["cta"] = ""
        p["scenes"][2]["visual"] = ""
        errors, _ = pl.check(p)
        self.assertTrue(any("call to action" in e for e in errors))
        self.assertTrue(any("visual" in e for e in errors))

    def test_bad_color_and_format(self):
        p = copy.deepcopy(PLAN)
        p["brand"]["accent"] = "coral"
        p["format"] = "tall"
        errors, _ = pl.check(p)
        self.assertTrue(any("brand.accent" in e for e in errors))
        self.assertTrue(any("format must be" in e for e in errors))

    def test_short_scene(self):
        p = copy.deepcopy(PLAN)
        p["scenes"][0]["seconds"] = 1
        self.assertTrue(any("too short" in e for e in pl.check(p)[0]))

    def test_duplicate_ids(self):
        p = copy.deepcopy(PLAN)
        p["scenes"][1]["id"] = "hook"
        self.assertTrue(any("used twice" in e for e in pl.check(p)[0]))


class Outputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plan_path = os.path.join(self.tmp, "plan.json")
        write_json(self.plan_path, PLAN)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = pl.main(list(argv))
        return code, buf.getvalue()

    def test_storyboard_and_shotlist(self):
        out = os.path.join(self.tmp, "launch")
        code, text = self.cli("storyboard", self.plan_path, "--out", out)
        self.assertEqual(code, 0, text)
        with open(os.path.join(out, "storyboard.md"), encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn("31 seconds", md)
        self.assertIn("212 teams in beta (source: founder/context.md)", md)
        self.assertIn("### 5. cta  (0:25.0 to 0:31.0)", md)
        with open(os.path.join(out, "shotlist.csv"), encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["asset_status"], "to capture or make")

    def test_bad_plan_writes_nothing(self):
        p = copy.deepcopy(PLAN)
        p["cta"] = ""
        write_json(self.plan_path, p)
        out = os.path.join(self.tmp, "launch")
        code, _ = self.cli("storyboard", self.plan_path, "--out", out)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(out))

    def test_hyperframes_files(self):
        files = pl.hyperframes_files(PLAN)
        self.assertEqual(len(files), 6)
        index = files["index.html"]
        self.assertIn('data-duration="31.0"', index)
        self.assertIn('data-composition-src="compositions/hook.html"', index)
        self.assertIn('width=1080, height=1920', index)
        scene = files["compositions/hook.html"]
        self.assertTrue(scene.startswith("<template>"))
        self.assertIn('id="hook" data-composition-id="hook"', scene)
        self.assertIn('window.__timelines["hook"]', scene)
        self.assertIn("fromTo", scene)
        self.assertIn("Visual to add", scene)

    def test_hyperframes_escapes_text(self):
        p = copy.deepcopy(PLAN)
        p["scenes"][1]["on_screen"] = "<b>Blockers</b> & delays"
        files = pl.hyperframes_files(p)
        self.assertIn("&lt;b&gt;Blockers&lt;/b&gt; &amp; delays", files["compositions/problem.html"])

    def test_hyperframes_cli_copies_assets_and_wont_overwrite(self):
        asset = os.path.join(self.tmp, "board.png")
        with open(asset, "wb") as fh:
            fh.write(b"\x89PNG")
        p = copy.deepcopy(PLAN)
        p["scenes"][0]["asset"] = asset
        write_json(self.plan_path, p)
        out = os.path.join(self.tmp, "hf")
        code, text = self.cli("hyperframes", self.plan_path, "--out", out)
        self.assertEqual(code, 0, text)
        self.assertTrue(os.path.exists(os.path.join(out, "assets", "board.png")))
        with open(os.path.join(out, "compositions", "hook.html"), encoding="utf-8") as fh:
            self.assertIn('src="../assets/board.png"', fh.read())
        code, _ = self.cli("hyperframes", self.plan_path, "--out", out)
        self.assertEqual(code, 2)

    def test_scene_ids_are_safe(self):
        self.assertEqual(pl._sid("1 Hook!"), "s-1-hook")
        self.assertEqual(pl._sid("CTA"), "cta")


if __name__ == "__main__":
    unittest.main()
