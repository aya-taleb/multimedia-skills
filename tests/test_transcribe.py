"""Unit tests for skills/transcribe/scripts/transcribe.py. faster-whisper is mocked."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "transcribe", "scripts"))
import transcribe as tr  # noqa: E402


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class W(object):
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word


class Seg(object):
    def __init__(self, start, end, text, words=None):
        self.start, self.end, self.text, self.words = start, end, text, words


class Info(object):
    language = "en"
    language_probability = 0.97
    duration = 12.5


def fake_model_factory(segments, record):
    class FakeModel(object):
        def __init__(self, name, device=None, compute_type=None):
            record["init"] = (name, device, compute_type)

        def transcribe(self, path, **kwargs):
            record["call"] = (path, kwargs)
            return iter(segments), Info()
    return FakeModel


SEGS = [
    Seg(0.0, 3.2, " Hi, I'm Dana and this is the first episode.",
        [W(0.0, 0.4, " Hi,"), W(0.5, 0.9, " I'm"), W(1.0, 1.3, " Nora"), W(1.4, 3.2, " and this is the first episode.")]),
    Seg(3.5, 9.0, " Today we talk about pricing a lunch subscription for offices, and why most people start too low "
                  "and then cannot raise it later without losing half of the list."),
    Seg(9.0, 12.5, "   "),
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.media = os.path.join(self.tmp, "episode.mp4")
        with open(self.media, "wb") as fh:
            fh.write(b"\x00\x00\x00\x18ftypmp42")
        self.record = {}
        self._load = tr.load_backend
        self._dev = tr.pick_device
        tr.load_backend = lambda: fake_model_factory(SEGS, self.record)
        tr.pick_device = lambda: ("cpu", "int8")

    def tearDown(self):
        tr.load_backend = self._load
        tr.pick_device = self._dev
        shutil.rmtree(self.tmp)

    def cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tr.main(list(argv))
        return code, buf.getvalue()


class Sources(Base):
    def test_youtube_link_refused(self):
        code, text = self.cli("run", "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(code, 2)
        self.assertIn("does not download", text)
        self.assertIn("export", text.lower())
        self.assertNotIn("init", self.record)

    def test_instagram_and_tiktok_refused(self):
        for url in ("https://www.instagram.com/reel/xyz/", "tiktok.com/@me/video/1", "https://youtu.be/abc"):
            code, _ = self.cli("run", url)
            self.assertEqual(code, 2, url)

    def test_other_url_refused(self):
        code, text = self.cli("run", "https://example.com/audio.mp3")
        self.assertEqual(code, 2)
        self.assertIn("only reads files", text)

    def test_missing_file(self):
        code, text = self.cli("run", os.path.join(self.tmp, "nope.mp3"))
        self.assertEqual(code, 2)
        self.assertIn("No file", text)

    def test_not_media(self):
        p = os.path.join(self.tmp, "notes.pdf")
        write_text(p, "x")
        code, text = self.cli("run", p)
        self.assertEqual(code, 2)
        self.assertIn("does not look like audio or video", text)

    def test_empty_file(self):
        p = os.path.join(self.tmp, "empty.wav")
        write_text(p, "")
        self.assertEqual(self.cli("run", p)[0], 2)

    def test_folder(self):
        self.assertEqual(self.cli("run", self.tmp)[0], 2)

    def test_bad_model(self):
        code, text = self.cli("run", self.media, "--model", "gpt-9")
        self.assertEqual(code, 2)
        self.assertIn("Unknown model", text)


class Missing(Base):
    def test_not_installed_gives_install_steps(self):
        tr.load_backend = lambda: None
        code, text = self.cli("run", self.media)
        self.assertEqual(code, 3)
        self.assertIn("pip install faster-whisper", text)

    def test_doctor_reports_missing(self):
        tr.load_backend = lambda: None
        code, text = self.cli("doctor")
        self.assertEqual(code, 3)
        self.assertIn("NOT installed", text)

    def test_doctor_ok(self):
        code, text = self.cli("doctor")
        self.assertEqual(code, 0)
        self.assertIn("installed", text)


class Running(Base):
    def test_default_outputs(self):
        out_dir = os.path.join(self.tmp, "media", "transcripts")
        code, text = self.cli("run", self.media, "--out", out_dir)
        self.assertEqual(code, 0, text)
        self.assertEqual(sorted(os.listdir(out_dir)), ["episode.json", "episode.md"])
        md = read_text(os.path.join(out_dir, "episode.md"))
        self.assertIn("[00:00] Hi, I'm Dana", md)
        self.assertIn("[00:03] Today we talk", md)
        self.assertIn("check names, numbers and quotes", md)
        data = json.loads(read_text(os.path.join(out_dir, "episode.json")))
        self.assertEqual(data["meta"]["language"], "en")
        self.assertEqual(len(data["segments"]), 3)

    def test_model_called_with_vad_and_language(self):
        self.cli("run", self.media, "--out", self.tmp, "--language", "ar", "--model", "medium")
        path, kwargs = self.record["call"]
        self.assertEqual(path, os.path.abspath(self.media))
        self.assertEqual(kwargs["language"], "ar")
        self.assertTrue(kwargs["vad_filter"])
        self.assertEqual(self.record["init"], ("medium", "cpu", "int8"))

    def test_captions_turn_on_word_timestamps(self):
        self.cli("run", self.media, "--out", self.tmp, "--formats", "srt,vtt")
        self.assertTrue(self.record["call"][1]["word_timestamps"])

    def test_srt_and_vtt(self):
        code, _ = self.cli("run", self.media, "--out", self.tmp, "--formats", "srt,vtt")
        self.assertEqual(code, 0)
        srt = read_text(os.path.join(self.tmp, "episode.srt"))
        vtt = read_text(os.path.join(self.tmp, "episode.vtt"))
        self.assertTrue(srt.startswith("1\n00:00:00,000 --> "))
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> ", vtt)
        for block in srt.strip().split("\n\n"):
            lines = block.split("\n")[2:]
            self.assertLessEqual(len(lines), 2, block)
            for line in lines:
                self.assertLessEqual(len(line), 42, line)

    def test_failure_is_reported(self):
        class Broken(object):
            def __init__(self, *a, **k):
                pass

            def transcribe(self, *a, **k):
                raise RuntimeError("Invalid data found when processing input")
        tr.load_backend = lambda: Broken
        code, text = self.cli("run", self.media, "--out", self.tmp)
        self.assertEqual(code, 4)
        self.assertIn("Invalid data", text)

    def test_silence_warning(self):
        tr.load_backend = lambda: fake_model_factory([Seg(0, 2, "  ")], self.record)
        code, text = self.cli("run", self.media, "--out", self.tmp)
        self.assertEqual(code, 0)
        self.assertIn("No speech found", text)

    def test_convert_without_model(self):
        tr.load_backend = lambda: None
        p = os.path.join(self.tmp, "t.json")
        write_json(p, {"meta": {}, "segments": [{"start": 0, "end": 1.5, "text": "Hello there"}]})
        code, _ = self.cli("convert", p, "--formats", "srt")
        self.assertEqual(code, 0)
        self.assertIn("Hello there", read_text(os.path.join(self.tmp, "t.srt")))

    def test_unknown_format(self):
        code, text = self.cli("run", self.media, "--out", self.tmp, "--formats", "docx")
        self.assertEqual(code, 2)


class Formatting(unittest.TestCase):
    def test_stamp(self):
        self.assertEqual(tr.stamp(3723.456), "01:02:03,456")
        self.assertEqual(tr.stamp(3723.456, "."), "01:02:03.456")
        self.assertEqual(tr.stamp(75.2, hours=False), "01:15")
        self.assertEqual(tr.stamp(-1), "00:00:00,000")

    def test_long_segment_split_by_time(self):
        seg = {"start": 0.0, "end": 10.0, "text": "word " * 60}
        parts = tr.split_cue(seg)
        self.assertGreater(len(parts), 1)
        self.assertAlmostEqual(parts[-1]["end"], 10.0, places=3)
        self.assertAlmostEqual(parts[0]["start"], 0.0)

    def test_split_uses_word_times(self):
        words = [{"start": i * 0.5, "end": i * 0.5 + 0.4, "word": "longerword%d" % i} for i in range(20)]
        seg = {"start": 0.0, "end": 10.0, "text": " ".join(w["word"] for w in words), "words": words}
        parts = tr.split_cue(seg)
        self.assertGreater(len(parts), 1)
        self.assertEqual(parts[1]["start"], words[len(parts[0]["text"].split())]["start"])

    def test_lines_always_fit(self):
        import random
        rnd = random.Random(7)
        for _ in range(500):
            words = ["".join(rnd.choice("abcdefgh") for _ in range(rnd.randint(1, 14))) for _ in range(rnd.randint(1, 60))]
            got = tr.cues([{"start": 0, "end": rnd.uniform(1, 30), "text": " ".join(words)}])
            self.assertEqual(" ".join(c["text"].replace("\n", " ") for c in got), " ".join(words))
            for c in got:
                self.assertLessEqual(c["text"].count("\n"), 1)
                for line in c["text"].split("\n"):
                    self.assertLessEqual(len(line), 42)

    def test_no_overlap(self):
        segs = [{"start": 0, "end": 5, "text": "a"}, {"start": 4, "end": 6, "text": "b"}]
        c = tr.cues(segs)
        self.assertLessEqual(c[0]["end"], c[1]["start"])


if __name__ == "__main__":
    unittest.main()
