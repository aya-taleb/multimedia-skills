"""Unit tests for skills/generate-images/scripts/replicate_run.py. The network is mocked."""
import base64
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "generate-images", "scripts"))
import replicate_run as rr  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")


def page(billing, price="$0.0001 per second", p50="$0.010"):
    props = {"billingConfig": billing, "price": price, "p50price": p50, "hardware": "CPU"}
    return ('<html><script id="react-component-props-x" type="application/json">%s</script></html>'
            % json.dumps(props)).encode()


PER_IMAGE = {"current_tiers": [{"criteria": [], "prices": [
    {"metric": "image_output_count", "metric_display": "output image", "price": "$0.04", "title": "per output image"}]}]}
PER_THOUSAND = {"current_tiers": [{"criteria": [], "prices": [
    {"metric": "image_output_count", "metric_display": "output image", "price": "$3", "title": "per thousand output images"}]}]}
VIDEO_TIERS = {"current_tiers": [
    {"criteria": [{"value": "with_audio"}], "prices": [
        {"metric": "video_output_duration_seconds", "metric_display": "second of output video", "price": "$0.15",
         "title": "per second of output video"}]},
    {"criteria": [{"value": "without_audio"}], "prices": [
        {"metric": "video_output_duration_seconds", "metric_display": "second of output video", "price": "$0.10",
         "title": "per second of output video"}]}]}
EXTERNAL = {"current_tiers": [{"criteria": [], "description": "You pay OpenAI directly via your API key.", "prices": []}]}


def model_json(official=True, props=None, required=None):
    props = props if props is not None else {
        "prompt": {"type": "string", "x-order": 0},
        "num_outputs": {"type": "integer", "default": 1, "minimum": 1, "maximum": 4},
        "aspect_ratio": {"allOf": [{"$ref": "#/components/schemas/aspect_ratio"}], "default": "1:1"},
    }
    return {"owner": "acme", "name": "img", "is_official": official,
            "latest_version": {"id": "a" * 64, "openapi_schema": {"components": {"schemas": {
                "Input": {"properties": props, "required": required if required is not None else ["prompt"]},
                "aspect_ratio": {"enum": ["1:1", "16:9", "9:16"]}}}}}}


def pred(status, output=None, error=None, pid="p123"):
    return {"id": pid, "status": status, "output": output, "error": error, "logs": "line1\nline2",
            "urls": {"get": "https://api.replicate.com/v1/predictions/" + pid,
                     "cancel": "https://api.replicate.com/v1/predictions/%s/cancel" % pid,
                     "web": "https://replicate.com/p/" + pid}}


class FakeNet(object):
    """Route requests to queued responses. Each route is a list; the last item repeats."""

    def __init__(self):
        self.routes = {}
        self.calls = []

    def add(self, method, contains, *responses):
        self.routes.setdefault((method, contains), []).extend(responses)

    def __call__(self, method, url, headers=None, body=None, timeout=60):
        self.calls.append((method, url, headers or {}, body))
        best = None
        for (m, contains), queue in self.routes.items():
            if m == method and contains in url and (best is None or len(contains) > len(best[0][1])):
                best = ((m, contains), queue)
        if best is None:
            raise AssertionError("unexpected request %s %s" % (method, url))
        queue = best[1]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        status, hdrs, payload = item
        if not isinstance(payload, bytes):
            payload = json.dumps(payload).encode()
        return status, hdrs, payload

    def count(self, method, contains):
        return sum(1 for m, u, _, _ in self.calls if m == method and contains in u)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = dict(os.environ)
        os.environ.pop("MEDIA_LEDGER", None)
        os.environ["FOUNDER_HOME"] = os.path.join(self.tmp, "founder-home")
        os.environ["REPLICATE_API_TOKEN"] = "r8_test"
        self.net = FakeNet()
        self.sleeps = []
        self._http, self._sleep = rr.http, rr.sleep
        rr.http = self.net
        rr.sleep = self.sleeps.append

    def tearDown(self):
        rr.http, rr.sleep = self._http, self._sleep
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.tmp)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rr.main(list(argv))
        return code, buf.getvalue()

    def ledger(self):
        with open(rr.ledger_path()) as fh:
            return json.load(fh)

    def standard_model(self, official=True, billing=PER_IMAGE):
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json(official)))
        self.net.add("GET", "replicate.com/acme/img", (200, {}, page(billing)))


class LedgerPath(Base):
    def test_ledger_under_founder_home(self):
        self.assertEqual(rr.ledger_path(),
                         os.path.join(self.tmp, "founder-home", "media", "spend-ledger.json"))

    def test_media_ledger_still_wins(self):
        os.environ["MEDIA_LEDGER"] = os.path.join(self.tmp, "x.json")
        self.assertEqual(rr.ledger_path(), os.path.join(self.tmp, "x.json"))

    def test_default_is_dot_founder(self):
        os.environ.pop("FOUNDER_HOME")
        self.assertEqual(rr.ledger_path(),
                         os.path.expanduser(os.path.join("~", ".founder", "media", "spend-ledger.json")))


class Overrides(unittest.TestCase):
    def test_only_localhost_overrides(self):
        os.environ["X_BASE"] = "https://evil.example.com/v1"
        self.assertEqual(rr._local_override("X_BASE", "d"), "d")
        os.environ["X_BASE"] = "http://localhost.evil.com/v1"
        self.assertEqual(rr._local_override("X_BASE", "d"), "d")
        os.environ["X_BASE"] = "http://127.0.0.1:8765/v1"
        self.assertEqual(rr._local_override("X_BASE", "d"), "http://127.0.0.1:8765/v1")
        del os.environ["X_BASE"]


class PriceParsing(unittest.TestCase):
    def test_per_image(self):
        p = rr.parse_price_page(page(PER_IMAGE).decode())
        self.assertAlmostEqual(p["tiers"][0]["per_unit"], 0.04)

    def test_per_thousand_is_divided(self):
        p = rr.parse_price_page(page(PER_THOUSAND).decode())
        self.assertAlmostEqual(p["tiers"][0]["per_unit"], 0.003)

    def test_fixture_page(self):
        with open(os.path.join(FIXTURES, "model-page-video.html"), encoding="utf-8") as fh:
            p = rr.parse_price_page(fh.read())
        self.assertEqual(len(p["tiers"]), 3)
        self.assertEqual(p["tiers"][2]["criteria"], ["1080p"])

    def test_no_price_block(self):
        self.assertIsNone(rr.parse_price_page("<html>nothing here</html>"))

    def test_bad_json_block_is_skipped(self):
        html = '<script type="application/json">{billingConfig broken</script>'
        self.assertIsNone(rr.parse_price_page(html))


class Estimates(unittest.TestCase):
    def test_counts_outputs(self):
        p = rr.parse_price_page(page(PER_IMAGE).decode())
        cost, _ = rr.estimate_cost(p, {"num_outputs": 3}, {})
        self.assertAlmostEqual(cost, 0.12)

    def test_default_from_schema(self):
        p = rr.parse_price_page(page(PER_IMAGE).decode())
        cost, _ = rr.estimate_cost(p, {}, {"num_outputs": 2})
        self.assertAlmostEqual(cost, 0.08)

    def test_video_tier_by_bool(self):
        p = rr.parse_price_page(page(VIDEO_TIERS).decode())
        cost, _ = rr.estimate_cost(p, {"duration": 8, "generate_audio": False}, {})
        self.assertAlmostEqual(cost, 0.8)
        cost, _ = rr.estimate_cost(p, {"duration": 8, "generate_audio": True}, {})
        self.assertAlmostEqual(cost, 1.2)

    def test_unknown_tier_uses_highest(self):
        p = rr.parse_price_page(page(VIDEO_TIERS).decode())
        cost, lines = rr.estimate_cost(p, {"duration": "4s"}, {})
        self.assertAlmostEqual(cost, 0.6)
        self.assertTrue(any("most expensive" in line for line in lines))

    def test_video_without_duration_is_unknown(self):
        p = rr.parse_price_page(page(VIDEO_TIERS).decode())
        cost, _ = rr.estimate_cost(p, {"prompt": "x"}, {})
        self.assertIsNone(cost)

    def test_frames_and_fps(self):
        p = rr.parse_price_page(page(VIDEO_TIERS).decode())
        cost, _ = rr.estimate_cost(p, {"num_frames": 81, "fps": 16, "generate_audio": False}, {})
        self.assertAlmostEqual(cost, 81 / 16 * 0.10)

    def test_gpu_time_doubles_typical(self):
        p = rr.parse_price_page(page({"current_tiers": []}, price="$0.000975 per second", p50="$0.014").decode())
        cost, _ = rr.estimate_cost(p, {}, {})
        self.assertAlmostEqual(cost, 0.028)

    def test_external_billing(self):
        p = rr.parse_price_page(page(EXTERNAL).decode())
        cost, lines = rr.estimate_cost(p, {}, {})
        self.assertIsNone(cost)
        self.assertIn("another company", lines[0])

    def test_none_price(self):
        self.assertIsNone(rr.estimate_cost(None, {}, {})[0])


HAILUO = {"current_tiers": [
    {"criteria": [{"value": "512P"}, {"value": 6}], "prices": [
        {"metric": "video_output_count", "metric_display": "output video", "price": "$0.10", "title": "per output video"}]},
    {"criteria": [{"value": "768P"}, {"value": 6}], "prices": [
        {"metric": "video_output_count", "metric_display": "output video", "price": "$0.27", "title": "per output video"}]},
    {"criteria": [{"value": "768P"}, {"value": 10}], "prices": [
        {"metric": "video_output_count", "metric_display": "output video", "price": "$0.45", "title": "per output video"}]}]}


class TierMatching(unittest.TestCase):
    def test_per_output_video_with_numeric_and_case(self):
        p = rr.parse_price_page(page(HAILUO).decode())
        cost, _ = rr.estimate_cost(p, {"duration": 6, "resolution": "768p"}, {})
        self.assertAlmostEqual(cost, 0.27)
        cost, _ = rr.estimate_cost(p, {"duration": "10", "resolution": "768p"}, {})
        self.assertAlmostEqual(cost, 0.45)

    def test_audio_file_count(self):
        audio = {"current_tiers": [{"criteria": [], "prices": [
            {"metric": "audio_output_count", "metric_display": "output audio file", "price": "$0.03",
             "title": "per output audio file"}]}]}
        cost, _ = rr.estimate_cost(rr.parse_price_page(page(audio).decode()), {"lyrics": "la"}, {})
        self.assertAlmostEqual(cost, 0.03)


class Validation(unittest.TestCase):
    def test_missing_required(self):
        self.assertIn("missing required input 'prompt'", rr.validate_input(model_json(), {}))

    def test_unknown_key(self):
        problems = rr.validate_input(model_json(), {"prompt": "x", "steps": 4})
        self.assertTrue(any("unknown input 'steps'" in p for p in problems))

    def test_enum_via_ref(self):
        problems = rr.validate_input(model_json(), {"prompt": "x", "aspect_ratio": "5:4"})
        self.assertTrue(any("aspect_ratio" in p for p in problems))

    def test_range(self):
        problems = rr.validate_input(model_json(), {"prompt": "x", "num_outputs": 9})
        self.assertTrue(any("maximum" in p for p in problems))

    def test_ok(self):
        self.assertEqual(rr.validate_input(model_json(), {"prompt": "x", "aspect_ratio": "16:9"}), [])

    def test_bad_model_ref(self):
        with self.assertRaises(rr.ToolError):
            rr.split_model("not a model")


class Setup(Base):
    def test_missing_token_explains_setup(self):
        del os.environ["REPLICATE_API_TOKEN"]
        code, text = self.run_cli("check")
        self.assertEqual(code, rr.EXIT_SETUP)
        self.assertIn("replicate.com/account/api-tokens", text)
        self.assertEqual(self.net.calls, [])

    def test_check_ok(self):
        self.net.add("GET", "/v1/account", (200, {}, {"username": "aya", "type": "user"}))
        code, text = self.run_cli("check")
        self.assertEqual(code, 0)
        self.assertIn("aya", text)

    def test_bad_token(self):
        self.net.add("GET", "/v1/account", (401, {}, {"detail": "Invalid token"}))
        code, text = self.run_cli("check")
        self.assertEqual(code, rr.EXIT_API)
        self.assertIn("not valid", text)

    def test_token_not_printed(self):
        self.net.add("GET", "/v1/account", (200, {}, {"username": "aya", "type": "user"}))
        _, text = self.run_cli("check")
        self.assertNotIn("r8_test", text)


class DryRunAndCap(Base):
    def test_no_yes_means_no_spend(self):
        self.standard_model()
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=a cat")
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", text)
        self.assertIn("$0.0400", text)
        self.assertEqual(self.net.count("POST", "/predictions"), 0)

    def test_over_cap_refuses_before_create(self):
        self.standard_model()
        self.run_cli("ledger", "--set-cap", "0.05")
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=a cat", "-i", "num_outputs=2", "--yes")
        self.assertEqual(code, rr.EXIT_CAP)
        self.assertIn("cap", text)
        self.assertEqual(self.net.count("POST", "/predictions"), 0)

    def test_cap_accumulates_across_runs(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("succeeded", output=[])))
        self.run_cli("ledger", "--set-cap", "0.10")
        self.assertEqual(self.run_cli("run", "acme/img", "-i", "prompt=a", "--yes", "--out", self.tmp)[0], 0)
        self.assertEqual(self.run_cli("run", "acme/img", "-i", "prompt=b", "--yes", "--out", self.tmp)[0], 0)
        code, _ = self.run_cli("run", "acme/img", "-i", "prompt=c", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_CAP)
        self.assertEqual(self.net.count("POST", "/predictions"), 2)

    def test_default_cap_is_five(self):
        self.assertEqual(rr.load_ledger(rr.ledger_path())["cap"], 5.0)

    def test_session_resets_after_idle(self):
        rr.reserve("acme/img", 1.0, "")
        data = self.ledger()
        data["last_activity"] = "2000-01-01T00:00:00+00:00"
        with open(rr.ledger_path(), "w") as fh:
            json.dump(data, fh)
        self.assertEqual(rr.spent(rr.load_ledger()), 0)

    def test_unknown_price_refuses(self):
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json()))
        self.net.add("GET", "replicate.com/acme/img", (404, {}, b"nope"))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes")
        self.assertEqual(code, rr.EXIT_SETUP)
        self.assertIn("--assume-cost", text)
        self.assertEqual(self.net.count("POST", "/predictions"), 0)

    def test_assume_cost_skips_lookup(self):
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json()))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--assume-cost", "0.5")
        self.assertEqual(code, 0)
        self.assertIn("$0.5000", text)
        self.assertEqual(self.net.count("GET", "replicate.com/acme"), 0)

    def test_max_cost(self):
        self.standard_model()
        code, _ = self.run_cli("run", "acme/img", "-i", "prompt=x", "--max-cost", "0.01", "--yes")
        self.assertEqual(code, rr.EXIT_CAP)

    def test_bad_input_refuses(self):
        self.standard_model()
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "-i", "aspect_ratio=7:3", "--yes")
        self.assertEqual(code, rr.EXIT_SETUP)
        self.assertIn("aspect_ratio", text)
        self.assertEqual(self.net.count("POST", "/predictions"), 0)

    def test_negative_cap_rejected(self):
        code, _ = self.run_cli("ledger", "--set-cap", "-1")
        self.assertEqual(code, rr.EXIT_SETUP)


class Running(Base):
    def test_success_downloads_right_away(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("starting")))
        self.net.add("GET", "/v1/predictions/p123",
                     (200, {}, pred("processing")),
                     (200, {}, pred("succeeded", output=["https://replicate.delivery/x/out-0.webp"])))
        self.net.add("GET", "replicate.delivery", (200, {"content-type": "image/webp"}, b"IMG"))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=A red bike", "--yes", "--out", self.tmp)
        self.assertEqual(code, 0, text)
        files = sorted(os.listdir(self.tmp))
        self.assertTrue(any(f.endswith(".webp") for f in files), files)
        self.assertTrue(any(f.endswith(".json") for f in files), files)
        self.assertEqual(self.ledger()["entries"][0]["status"], "succeeded")
        self.assertEqual(self.ledger()["entries"][0]["prediction"], "p123")

    def test_backoff_grows(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("starting")))
        self.net.add("GET", "/v1/predictions/p123", *([(200, {}, pred("processing"))] * 6
                                                      + [(200, {}, pred("succeeded", output=[]))]))
        self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(self.sleeps[:3], [1.0, 1.5, 2.25])
        self.assertTrue(all(s <= 10.0 for s in self.sleeps))

    def test_community_model_uses_version(self):
        self.standard_model(official=False)
        self.net.add("POST", "/v1/predictions", (201, {}, pred("succeeded", output=[])))
        self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        body = json.loads([c for c in self.net.calls if c[0] == "POST"][0][3])
        self.assertEqual(body["version"], "acme/img:" + "a" * 64)

    def test_deadline_header_sent(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("succeeded", output=[])))
        self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp, "--deadline", "5m")
        headers = [c for c in self.net.calls if c[0] == "POST"][0][2]
        self.assertEqual(headers["Cancel-After"], "5m")

    def test_failed_prediction(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("failed", error="NSFW content")))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_FAILED)
        self.assertIn("NSFW content", text)
        self.assertEqual(self.ledger()["entries"][0]["status"], "failed")

    def test_failed_run_still_writes_record_and_totals(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("failed", error="E005 sensitive")))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp, "--label", "hero")
        self.assertEqual(code, rr.EXIT_FAILED)
        records = [f for f in os.listdir(self.tmp) if f.startswith("hero-") and f.endswith(".json")]
        self.assertEqual(len(records), 1)
        with open(os.path.join(self.tmp, records[0])) as fh:
            rec = json.load(fh)
        self.assertEqual(rec["status"], "failed")
        self.assertIn("E005", rec["error"])
        self.assertIn("Session spend: $0.0400 of the $5.00 cap", text)

    def test_canceled_prediction(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("canceled")))
        code, _ = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_TIMEOUT)
        self.assertEqual(self.ledger()["entries"][0]["status"], "canceled")
        self.assertGreater(self.ledger()["entries"][0]["cost"], 0)

    def test_aborted_is_free(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("aborted")))
        code, _ = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_TIMEOUT)
        self.assertEqual(self.ledger()["entries"][0]["cost"], 0)

    def test_429_on_create_waits_then_runs(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions",
                     (429, {}, {"detail": "Request was throttled. Your rate limit resets in ~30s."}),
                     (201, {}, pred("succeeded", output=[])))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, 0, text)
        self.assertIn(30.0, self.sleeps)
        self.assertEqual(self.net.count("POST", "/predictions"), 2)

    def test_429_retry_after_header(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions",
                     (429, {"retry-after": "7"}, {"detail": "throttled"}),
                     (201, {}, pred("succeeded", output=[])))
        self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertIn(7.0, self.sleeps)

    def test_429_forever_gives_up_and_frees_reservation(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (429, {}, {"detail": "throttled ~5s"}))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_API)
        self.assertEqual(self.net.count("POST", "/predictions"), 4)
        self.assertEqual(rr.spent(rr.load_ledger()), 0)

    def test_500_on_create_is_not_retried(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (502, {}, b"bad gateway"))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_API)
        self.assertEqual(self.net.count("POST", "/predictions"), 1)
        self.assertIn("will not retry", text)
        self.assertEqual(self.ledger()["entries"][0]["status"], "unknown")
        self.assertGreater(rr.spent(rr.load_ledger()), 0)

    def test_dropped_connection_on_create_is_not_retried(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", OSError("reset"))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_API)
        self.assertIn("may or may not", text)

    def test_402_no_credit(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (402, {}, {"detail": "Insufficient credit"}))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_API)
        self.assertIn("billing", text)
        self.assertEqual(rr.spent(rr.load_ledger()), 0)

    def test_cold_boot_message(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("starting")))
        self.net.add("GET", "/v1/predictions/p123", *([(200, {}, pred("starting"))] * 8
                                                      + [(200, {}, pred("succeeded", output=[]))]))
        clock = [1000.0]

        def fake_sleep(s):
            self.sleeps.append(s)
            clock[0] += s
        rr.sleep = fake_sleep
        real_time = rr.time.time
        rr.time.time = lambda: clock[0]
        try:
            _, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        finally:
            rr.time.time = real_time
        self.assertIn("cold boot", text)

    def test_timeout_cancels(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("processing")))
        self.net.add("GET", "/v1/predictions/p123", (200, {}, pred("processing")))
        self.net.add("POST", "/cancel", (200, {}, pred("canceled")))
        clock = [0.0]

        def fake_sleep(s):
            clock[0] += s
        rr.sleep = fake_sleep
        real_time = rr.time.time
        rr.time.time = lambda: clock[0]
        try:
            code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp, "--timeout", "30")
        finally:
            rr.time.time = real_time
        self.assertEqual(code, rr.EXIT_TIMEOUT)
        self.assertEqual(self.net.count("POST", "/cancel"), 1)
        self.assertEqual(self.ledger()["entries"][0]["status"], "timed_out")

    def test_poll_429_is_survived(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("processing")))
        self.net.add("GET", "/v1/predictions/p123", (429, {}, {"detail": "~2s"}),
                     (200, {}, pred("succeeded", output=[])))
        code, _ = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, 0)

    def test_download_failure_lists_urls(self):
        self.standard_model()
        self.net.add("POST", "/v1/models/acme/img/predictions",
                     (201, {}, pred("succeeded", output="https://replicate.delivery/y/out.png")))
        self.net.add("GET", "replicate.delivery", (500, {}, b""))
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, rr.EXIT_DOWNLOAD)
        self.assertIn("expire", text)
        self.assertIn("https://replicate.delivery/y/out.png", text)

    def test_data_url_output_saved(self):
        self.standard_model()
        data_url = "data:image/png;base64," + base64.b64encode(b"PNGDATA").decode()
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("succeeded", output=[data_url])))
        code, _ = self.run_cli("run", "acme/img", "-i", "prompt=x", "--yes", "--out", self.tmp)
        self.assertEqual(code, 0)
        pngs = [f for f in os.listdir(self.tmp) if f.endswith(".png")]
        with open(os.path.join(self.tmp, pngs[0]), "rb") as fh:
            self.assertEqual(fh.read(), b"PNGDATA")

    def test_small_file_input_becomes_data_url(self):
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json(props={
            "prompt": {"type": "string"}, "image": {"type": "string", "format": "uri"}})))
        self.net.add("GET", "replicate.com/acme/img", (200, {}, page(PER_IMAGE)))
        img = os.path.join(self.tmp, "ref.png")
        with open(img, "wb") as fh:
            fh.write(b"\x89PNG small")
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("succeeded", output=[])))
        self.run_cli("run", "acme/img", "-i", "prompt=x", "-i", "image=@" + img, "--yes", "--out", self.tmp)
        body = json.loads([c for c in self.net.calls if c[0] == "POST"][0][3])
        self.assertTrue(body["input"]["image"].startswith("data:image/png;base64,"))

    def test_large_file_input_is_uploaded(self):
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json(props={
            "prompt": {"type": "string"}, "image": {"type": "string", "format": "uri"}})))
        self.net.add("GET", "replicate.com/acme/img", (200, {}, page(PER_IMAGE)))
        img = os.path.join(self.tmp, "big.jpg")
        with open(img, "wb") as fh:
            fh.write(b"x" * (rr.DATA_URL_LIMIT + 10))
        self.net.add("POST", "/v1/files", (201, {}, {"urls": {"get": "https://api.replicate.com/v1/files/f1"}}))
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("succeeded", output=[])))
        self.run_cli("run", "acme/img", "-i", "prompt=x", "-i", "image=@" + img, "--yes", "--out", self.tmp)
        posts = [c for c in self.net.calls if c[0] == "POST" and "/predictions" in c[1]]
        self.assertEqual(json.loads(posts[0][3])["input"]["image"], "https://api.replicate.com/v1/files/f1")

    def test_required_file_input_counts_as_present(self):
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json(props={
            "prompt": {"type": "string"}, "start_image": {"type": "string", "format": "uri"}},
            required=["prompt", "start_image"])))
        self.net.add("GET", "replicate.com/acme/img", (200, {}, page(PER_IMAGE)))
        img = os.path.join(self.tmp, "start.png")
        with open(img, "wb") as fh:
            fh.write(b"\x89PNG")
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "-i", "start_image=@" + img)
        self.assertEqual(code, 0, text)
        self.assertIn("DRY RUN", text)

    def test_missing_file_input(self):
        self.standard_model()
        code, text = self.run_cli("run", "acme/img", "-i", "prompt=x", "-i", "image=@/no/such.png", "--yes")
        self.assertEqual(code, rr.EXIT_SETUP)
        self.assertEqual(rr.spent(rr.load_ledger()), 0)
        self.assertEqual(self.net.count("POST", "/predictions"), 0)


class Lookups(Base):
    def test_search_prints_models(self):
        self.net.add("GET", "/v1/search", (200, {}, {"models": [{"model": {
            "owner": "acme", "name": "img", "is_official": True, "run_count": 10, "description": "Makes images",
            "latest_version": {"created_at": "2026-09-01T00:00:00Z"}}, "metadata": {"tags": ["text-to-image"]}}],
            "collections": [], "pages": []}))
        code, text = self.run_cli("search", "text to image")
        self.assertEqual(code, 0)
        self.assertIn("acme/img", text)
        self.assertIn("2026-09-01", text)

    def test_schema_lists_enums(self):
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json()))
        code, text = self.run_cli("schema", "acme/img")
        self.assertEqual(code, 0)
        self.assertIn("16:9", text)
        self.assertIn("REQUIRED", text)

    def test_price_without_token(self):
        del os.environ["REPLICATE_API_TOKEN"]
        self.net.add("GET", "replicate.com/acme/img", (200, {}, page(PER_IMAGE)))
        code, text = self.run_cli("price", "acme/img", "-i", "num_outputs=2")
        self.assertEqual(code, 0)
        self.assertIn("$0.0800", text)

    def test_pinned_version(self):
        ver = "b" * 64
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json(official=False)))
        self.net.add("GET", "/versions/" + ver, (200, {}, {"id": ver, "openapi_schema": {}}))
        model = rr.get_model("r8_test", "acme/img:" + ver)
        self.assertEqual(model["latest_version"]["id"], ver)


if __name__ == "__main__":
    unittest.main()
