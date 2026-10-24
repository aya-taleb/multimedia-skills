"""Unit tests for skills/generate-images/scripts/generate.py. The network is mocked; no key is real."""
import base64
import contextlib
import datetime
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "generate-images", "scripts"))
import generate as gen  # noqa: E402
import replicate_run as rr  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png"
JPG = b"\xff\xd8\xff\xe0" + b"fake-jpg"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"fake-mp4"
KEYS = {"REPLICATE_API_TOKEN": "r8_testtoken", "CLOUDFLARE_ACCOUNT_ID": "abc123def456abc123def456abc123de",
        "CLOUDFLARE_API_TOKEN": "cf_secret_token_1", "OPENAI_API_KEY": "sk-test-secret-1",
        "RUNWAYML_API_SECRET": "rw_secret_key_1", "GEMINI_API_KEY": "gm_secret_key_1"}
CF_RUN = "/ai/run/@cf/black-forest-labs/"


def b64(raw):
    return base64.b64encode(raw).decode()


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
    keys = ()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = dict(os.environ)
        for name in list(KEYS) + ["GOOGLE_API_KEY", "MEDIA_LEDGER"]:
            os.environ.pop(name, None)
        for name in self.keys:
            os.environ[name] = KEYS[name]
        os.environ["FOUNDER_HOME"] = os.path.join(self.tmp, "founder-home")
        self.out_dir = os.path.join(self.tmp, "media")
        self.net = FakeNet()
        self.sleeps = []
        self._http, self._sleep, self._time = rr.http, rr.sleep, time.time
        rr.http = self.net
        rr.sleep = self.sleeps.append

    def tearDown(self):
        rr.http, rr.sleep, time.time = self._http, self._sleep, self._time
        os.environ.clear()
        os.environ.update(self.env)
        shutil.rmtree(self.tmp)

    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = gen.main(list(argv))
        return code, buf.getvalue()

    def run_paid(self, model, *extra):
        return self.run_cli("run", model, "--yes", "--out", self.out_dir, *extra)

    def ledger(self):
        with open(rr.ledger_path()) as fh:
            return json.load(fh)

    def spent(self):
        return rr.spent(rr.load_ledger())

    def fake_clock(self):
        clock = [1000.0]

        def fake_sleep(s):
            self.sleeps.append(s)
            clock[0] += s
        rr.sleep = fake_sleep
        time.time = lambda: clock[0]

    def files(self, ext):
        if not os.path.isdir(self.out_dir):
            return []
        return [f for f in os.listdir(self.out_dir) if f.endswith(ext)]

    def no_secret_in(self, text):
        for value in KEYS.values():
            if value != KEYS["CLOUDFLARE_ACCOUNT_ID"]:
                self.assertNotIn(value, text)


# ---------------------------------------------------------------- table and estimates

class Table(unittest.TestCase):
    def setUp(self):
        self.table = gen.load_table()

    def test_every_model_has_source_date_and_price_rule(self):
        for name, prov in self.table["providers"].items():
            datetime.date.fromisoformat(prov["checked"])
            self.assertTrue(prov["source"].startswith("https://"), name)
            for model in prov["models"]:
                spec = gen.model_spec(self.table, name, model)
                self.assertIn(spec["price"]["method"], ("per_image", "tiles", "per_second"), model)
                self.assertTrue(spec["price"].get("why"), model)
                self.assertTrue(spec["inputs"].get("prompt"), model)

    def test_every_model_prices_at_its_defaults(self):
        for name, prov in self.table["providers"].items():
            for model in prov["models"]:
                spec = gen.model_spec(self.table, name, model)
                data = {"prompt": "x"}
                for key, rule in spec["inputs"].items():
                    if rule.get("required") and key not in data:
                        data[key] = "@f" if rule["type"] == "file" else (rule.get("enum") or [5])[0]
                data, _ = gen.apply_defaults(spec, data)
                cost, lines = gen.estimate(spec, data)
                self.assertIsNotNone(cost, (model, lines))
                self.assertGreater(cost, 0)

    def test_flux_schnell_math(self):
        spec = gen.model_spec(self.table, "cloudflare", "@cf/black-forest-labs/flux-1-schnell")
        cost, _ = gen.estimate(spec, {"prompt": "x", "steps": 4})
        self.assertAlmostEqual(cost, 4 * (0.0000528 + 4 * 0.0001056))

    def test_klein_input_images_add_cost(self):
        spec = gen.model_spec(self.table, "cloudflare", "@cf/black-forest-labs/flux-2-klein-4b")
        base, _ = gen.estimate(spec, {"prompt": "x", "width": 1024, "height": 1024})
        more, _ = gen.estimate(spec, {"prompt": "x", "width": 1024, "height": 1024, "input_image_0": "@a.png"})
        self.assertAlmostEqual(base, 4 * 0.000287)
        self.assertAlmostEqual(more - base, 16 * 0.000059)

    def test_tiles_round_up(self):
        self.assertEqual(gen.tiles(1024, 768), 4)
        self.assertEqual(gen.tiles(1920, 1080), 12)

    def test_openai_margin_and_count(self):
        spec = gen.model_spec(self.table, "openai", "gpt-image-2.5-flare")
        cost, _ = gen.estimate(spec, {"prompt": "", "quality": "low", "size": "1024x1024", "n": 4})
        self.assertAlmostEqual(cost, 0.00588 * 4 * 1.25)

    def test_openai_unpriced_size_is_unknown(self):
        spec = gen.model_spec(self.table, "openai", "gpt-image-2")
        cost, lines = gen.estimate(spec, {"prompt": "x", "quality": "high", "size": "3840x2160"})
        self.assertIsNone(cost)
        self.assertIn("No table price", lines[0])

    def test_runway_audio_rates(self):
        spec = gen.model_spec(self.table, "runway", "veo3.1_fast")
        self.assertAlmostEqual(gen.estimate(spec, {"duration": 8, "audio": True})[0], 1.2)
        self.assertAlmostEqual(gen.estimate(spec, {"duration": 8, "audio": False})[0], 0.8)

    def test_runway_needs_duration(self):
        spec = gen.model_spec(self.table, "runway", "gen4_turbo")
        cost, lines = gen.estimate(spec, {"prompt": "x"})
        self.assertIsNone(cost)
        self.assertIn("duration", lines[0])

    def test_google_assumes_longest_clip(self):
        spec = gen.model_spec(self.table, "google", "gemini-omni-1.1-flash")
        cost, lines = gen.estimate(spec, {"prompt": "x", "resolution": "720p"})
        self.assertAlmostEqual(cost, 10 * 0.10136 * 1.1)
        self.assertTrue(any("assumed" in line for line in lines))
        self.assertIsNone(gen.estimate(spec, {"prompt": "x", "resolution": "4k"})[0])

    def test_resolve_by_model_name(self):
        self.assertEqual(gen.resolve(self.table, "gen4_turbo")[0], "runway")
        self.assertEqual(gen.resolve(self.table, "@cf/black-forest-labs/flux-2-dev")[0], "cloudflare")
        self.assertEqual(gen.resolve(self.table, "black-forest-labs/flux-schnell")[0], "replicate")
        with self.assertRaises(gen.ToolError):
            gen.resolve(self.table, "mystery-model")

    def test_stale_table_warns(self):
        spec = {"checked": "2020-01-01", "source": "https://example.com"}
        self.assertIn("days ago", gen.stale_warning(spec, self.table))
        spec["checked"] = datetime.date.today().isoformat()
        self.assertIsNone(gen.stale_warning(spec, self.table))

    def test_validate(self):
        spec = gen.model_spec(self.table, "runway", "veo3.1_fast")
        problems = gen.validate(spec, {"prompt": "x", "ratio": "4:3", "duration": 5, "audio": "yes", "foo": 1})
        text = " ".join(problems)
        for word in ("ratio", "duration", "audio", "unknown input 'foo'"):
            self.assertIn(word, text)

    def test_err_info_shapes(self):
        self.assertEqual(gen.err_info(b'{"errors":[{"code":3036,"message":"limit"}]}'), ("3036", "limit"))
        self.assertEqual(gen.err_info(b'{"error":{"type":"insufficient_quota","message":"m"}}')[0], "insufficient_quota")
        self.assertEqual(gen.err_info(b'{"error":"bad ratio"}'), ("", "bad ratio"))
        self.assertEqual(gen.err_info(b'{"error":{"code":"quota_exceeded","message":"q"}}')[0], "quota_exceeded")

    def test_ext_sniffing(self):
        self.assertEqual(gen.ext_for_bytes(PNG), ".png")
        self.assertEqual(gen.ext_for_bytes(JPG), ".jpg")
        self.assertEqual(gen.ext_for_bytes(MP4), ".mp4")

    def test_multipart_has_fields_and_file(self):
        body, ctype = gen.multipart_form({"prompt": "a cat", "width": 1024}, {"input_image_0": (PNG, "image/png", "a.png")})
        self.assertIn("multipart/form-data; boundary=", ctype)
        self.assertIn(b'name="prompt"\r\n\r\na cat', body)
        self.assertIn(b'name="width"\r\n\r\n1024', body)
        self.assertIn(PNG, body)


# ---------------------------------------------------------------- providers, keys, auto-pick

class Providers(Base):
    def test_no_keys_check_explains_every_provider(self):
        code, text = self.run_cli("check")
        self.assertEqual(code, gen.EXIT_SETUP)
        for word in ("REPLICATE_API_TOKEN", "CLOUDFLARE_API_TOKEN", "OPENAI_API_KEY", "RUNWAYML_API_SECRET", "GEMINI_API_KEY"):
            self.assertIn(word, text)
        self.assertEqual(self.net.calls, [])

    def test_only_one_key_is_the_default(self):
        os.environ["CLOUDFLARE_ACCOUNT_ID"] = KEYS["CLOUDFLARE_ACCOUNT_ID"]
        os.environ["CLOUDFLARE_API_TOKEN"] = KEYS["CLOUDFLARE_API_TOKEN"]
        code, text = self.run_cli("providers")
        self.assertEqual(code, 0)
        self.assertIn("Default for image: cloudflare", text)
        self.assertIn("Default for video: none", text)
        self.no_secret_in(text)

    def test_two_keys_and_no_order_means_ask(self):
        os.environ["OPENAI_API_KEY"] = KEYS["OPENAI_API_KEY"]
        os.environ["REPLICATE_API_TOKEN"] = KEYS["REPLICATE_API_TOKEN"]
        _, text = self.run_cli("providers")
        self.assertIn("Default for image: none (ask the user", text)

    def test_saved_order_wins(self):
        os.environ["OPENAI_API_KEY"] = KEYS["OPENAI_API_KEY"]
        os.environ["REPLICATE_API_TOKEN"] = KEYS["REPLICATE_API_TOKEN"]
        code, text = self.run_cli("providers", "--order", "openai,replicate")
        self.assertEqual(code, 0)
        self.assertIn("Default for image: openai", text)
        self.assertIn("Default for video: replicate", text)

    def test_bad_order_rejected(self):
        code, _ = self.run_cli("providers", "--order", "openai,midjourney")
        self.assertEqual(code, gen.EXIT_SETUP)

    def test_google_api_key_also_works(self):
        os.environ["GOOGLE_API_KEY"] = "gk_other_secret"
        self.assertTrue(gen.has_key("google"))
        self.assertEqual(gen.get_keys("google")["key"], "gk_other_secret")

    def test_missing_key_on_paid_run(self):
        code, text = self.run_paid("@cf/black-forest-labs/flux-1-schnell", "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_SETUP)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID", text)
        self.assertEqual(self.net.calls, [])
        self.assertEqual(self.spent(), 0)

    def test_dry_run_needs_no_key_and_no_network(self):
        code, text = self.run_cli("run", "gpt-image-2.5-flare", "-i", "prompt=a cat")
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", text)
        self.assertIn("NOT set", text)
        self.assertEqual(self.net.calls, [])

    def test_unknown_model_refuses_without_assume_cost(self):
        code, text = self.run_cli("run", "@cf/someone/new-model", "--provider", "cloudflare", "-i", "prompt=x", "--yes")
        self.assertEqual(code, gen.EXIT_SETUP)
        self.assertIn("--assume-cost", text)
        self.assertEqual(self.net.calls, [])


class SharedLedger(Base):
    keys = ("REPLICATE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "OPENAI_API_KEY")

    def test_one_cap_across_providers(self):
        rr.reserve("replicate:acme/img", 1.95, "")
        code, text = self.run_paid("gpt-image-2.5-flare", "-i", "prompt=x", "-i", "quality=high")
        self.assertEqual(code, gen.EXIT_CAP)
        self.assertIn("cap", text)
        self.assertEqual(self.net.count("POST", "/images/generations"), 0)

    def test_cap_accumulates_over_cloudflare_runs(self):
        self.net.add("POST", CF_RUN, (200, {}, {"result": {"image": b64(JPG)}, "success": True}))
        self.run_cli("ledger", "--set-cap", "0.004")
        self.assertEqual(self.run_paid("@cf/black-forest-labs/flux-1-schnell", "-i", "prompt=a")[0], 0)
        self.assertEqual(self.run_paid("@cf/black-forest-labs/flux-1-schnell", "-i", "prompt=b")[0], 0)
        code, _ = self.run_paid("@cf/black-forest-labs/flux-1-schnell", "-i", "prompt=c")
        self.assertEqual(code, gen.EXIT_CAP)
        self.assertEqual(self.net.count("POST", CF_RUN), 2)

    def test_replicate_still_goes_through_replicate_run(self):
        from test_replicate_run import PER_IMAGE, model_json, page, pred
        self.net.add("GET", "/v1/models/acme/img", (200, {}, model_json()))
        self.net.add("GET", "replicate.com/acme/img", (200, {}, page(PER_IMAGE)))
        self.net.add("POST", "/v1/models/acme/img/predictions", (201, {}, pred("succeeded", output=[])))
        code, text = self.run_paid("acme/img", "-i", "prompt=x")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.ledger()["entries"][0]["model"], "acme/img")
        self.assertEqual(self.net.count("POST", "/predictions"), 1)

    def test_replicate_run_alias_still_works(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rr.main(["ledger"])
        self.assertEqual(code, 0)

    def test_max_cost(self):
        code, _ = self.run_paid("gpt-image-2", "-i", "prompt=x", "-i", "quality=high", "--max-cost", "0.05")
        self.assertEqual(code, gen.EXIT_CAP)
        self.assertEqual(self.net.calls, [])


# ---------------------------------------------------------------- Cloudflare

class Cloudflare(Base):
    keys = ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
    model = "@cf/black-forest-labs/flux-1-schnell"

    def test_success_saves_image_and_record(self):
        self.net.add("POST", CF_RUN, (200, {}, {"result": {"image": b64(JPG)}, "success": True, "errors": []}))
        code, text = self.run_paid(self.model, "-i", "prompt=a red bike", "--label", "bike")
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.files(".jpg")), 1)
        self.assertEqual(len(self.files(".json")), 1)
        call = [c for c in self.net.calls if c[0] == "POST"][0]
        self.assertIn("/accounts/%s/ai/run/%s" % (KEYS["CLOUDFLARE_ACCOUNT_ID"], self.model), call[1])
        self.assertEqual(call[2]["Authorization"], "Bearer " + KEYS["CLOUDFLARE_API_TOKEN"])
        self.assertEqual(json.loads(call[3]), {"prompt": "a red bike", "steps": 4})
        self.assertEqual(self.ledger()["entries"][0]["status"], "succeeded")
        self.no_secret_in(text)

    def test_multipart_model_sends_form(self):
        self.net.add("POST", CF_RUN, (200, {}, {"result": {"image": b64(PNG)}, "success": True}))
        img = os.path.join(self.tmp, "ref.png")
        with open(img, "wb") as fh:
            fh.write(PNG)
        code, text = self.run_paid("@cf/black-forest-labs/flux-2-klein-4b", "-i", "prompt=x", "-i", "input_image_0=@" + img)
        self.assertEqual(code, 0, text)
        call = [c for c in self.net.calls if c[0] == "POST"][0]
        self.assertTrue(call[2]["Content-Type"].startswith("multipart/form-data; boundary="))
        self.assertIn(PNG, call[3])
        self.assertIn(b'name="height"\r\n\r\n768', call[3])

    def test_capacity_429_retries_with_backoff(self):
        self.net.add("POST", CF_RUN,
                     (429, {}, {"errors": [{"code": 3040, "message": "Capacity temporarily exceeded"}], "success": False}),
                     (429, {}, {"errors": [{"code": 3040, "message": "Capacity temporarily exceeded"}], "success": False}),
                     (200, {}, {"result": {"image": b64(JPG)}, "success": True}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.sleeps[:2], [5.0, 10.0])
        self.assertEqual(self.net.count("POST", CF_RUN), 3)

    def test_free_allocation_429_is_not_retried(self):
        self.net.add("POST", CF_RUN, (429, {}, {"errors": [{"code": 3036, "message": "daily free allocation"}]}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.assertEqual(self.net.count("POST", CF_RUN), 1)
        self.assertIn("Waiting will not fix", text)
        self.assertEqual(self.spent(), 0)

    def test_bad_input_400_frees_reservation(self):
        self.net.add("POST", CF_RUN, (400, {}, {"errors": [{"code": 5004, "message": "Invalid data"}], "success": False}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.assertIn("Invalid data", text)
        self.assertEqual(self.spent(), 0)

    def test_timeout_keeps_charge(self):
        self.net.add("POST", CF_RUN, socket.timeout("timed out"))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_TIMEOUT)
        self.assertIn("will not retry", text)
        self.assertEqual(self.net.count("POST", CF_RUN), 1)
        self.assertEqual(self.ledger()["entries"][0]["status"], "unknown")
        self.assertGreater(self.spent(), 0)

    def test_server_error_on_create_is_not_retried(self):
        self.net.add("POST", CF_RUN, (500, {}, b"oops"))
        code, _ = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.assertEqual(self.net.count("POST", CF_RUN), 1)
        self.assertGreater(self.spent(), 0)

    def test_408_counts_as_timed_out(self):
        self.net.add("POST", CF_RUN, (408, {}, {"errors": [{"code": 3007, "message": "Request timeout"}]}))
        code, _ = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_TIMEOUT)
        self.assertGreater(self.spent(), 0)

    def test_answer_without_image_is_a_failure(self):
        self.net.add("POST", CF_RUN, (200, {}, {"result": {}, "success": False, "errors": [{"code": 1, "message": "no"}]}))
        code, _ = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_FAILED)

    def test_unknown_input_refused_before_any_call(self):
        code, text = self.run_paid(self.model, "-i", "prompt=x", "-i", "seed=4")
        self.assertEqual(code, gen.EXIT_SETUP)
        self.assertIn("unknown input 'seed'", text)
        self.assertEqual(self.net.calls, [])

    def test_check_is_free_model_search(self):
        self.net.add("GET", "/ai/models/search", (200, {}, {"result": [{"name": self.model}], "success": True}))
        code, text = self.run_cli("check", "--provider", "cloudflare")
        self.assertEqual(code, 0, text)
        self.assertIn("key works", text)
        self.assertEqual(self.net.count("POST", ""), 0)

    def test_check_bad_token(self):
        self.net.add("GET", "/ai/models/search", (401, {}, {"errors": [{"code": 10000, "message": "Authentication error"}]}))
        code, text = self.run_cli("check", "--provider", "cloudflare")
        self.assertEqual(code, gen.EXIT_API)
        self.assertIn("not valid", text)

    def test_models_marks_live_listing(self):
        self.net.add("GET", "/ai/models/search", (200, {}, {"result": [{"name": self.model}, {"name": "@cf/x/new"}]}))
        code, text = self.run_cli("models", "--provider", "cloudflare")
        self.assertEqual(code, 0)
        self.assertIn("flux-1-schnell | FLUX.1", text)
        self.assertIn("listed live: yes", text)
        self.assertIn("listed live: NO", text)
        self.assertIn("@cf/x/new", text)


# ---------------------------------------------------------------- OpenAI

class OpenAI(Base):
    keys = ("OPENAI_API_KEY",)
    model = "gpt-image-2.5-flare"

    def test_success_with_n(self):
        self.net.add("POST", "/v1/images/generations", (200, {"x-request-id": "req_abc123"},
                                                         {"created": 1, "data": [{"b64_json": b64(PNG)}, {"b64_json": b64(PNG)}]}))
        code, text = self.run_paid(self.model, "-i", "prompt=a cat", "-i", "n=2")
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.files(".png")), 2)
        body = json.loads([c for c in self.net.calls if c[0] == "POST"][0][3])
        self.assertEqual(body["model"], self.model)
        self.assertEqual(body["quality"], "medium")
        self.assertEqual(body["size"], "1024x1024")

    def test_moderation_block_is_a_refusal(self):
        self.net.add("POST", "/v1/images/generations", (400, {}, {"error": {
            "type": "image_generation_user_error", "code": "moderation_blocked", "message": "blocked",
            "moderation_details": {"moderation_stage": "input", "categories": ["harassment"]}}}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_FAILED)
        self.assertIn("safety system blocked", text)
        self.assertIn("Do not retry the same input", text)
        self.assertEqual(self.net.count("POST", "/images"), 1)
        self.assertEqual(self.ledger()["entries"][0]["status"], "refused")

    def test_rate_limit_waits_for_retry_after(self):
        self.net.add("POST", "/v1/images/generations",
                     (429, {"retry-after": "7"}, {"error": {"code": "rate_limit_exceeded", "message": "slow down"}}),
                     (200, {}, {"data": [{"b64_json": b64(PNG)}]}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, 0, text)
        self.assertIn(7.0, self.sleeps)

    def test_out_of_credit_429_is_not_retried(self):
        self.net.add("POST", "/v1/images/generations", (429, {}, {"error": {
            "type": "insufficient_quota", "code": "credit_balance_exhausted", "message": "no credits"}}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.assertEqual(self.net.count("POST", "/images"), 1)
        self.assertEqual(self.spent(), 0)

    def test_429_forever_gives_up(self):
        self.net.add("POST", "/v1/images/generations", (429, {}, {"error": {"code": "rate_limit_exceeded", "message": "x"}}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.assertEqual(self.net.count("POST", "/images"), 4)
        self.assertIn("after 3 waits", text)
        self.assertEqual(self.spent(), 0)

    def test_huge_retry_after_stops(self):
        self.net.add("POST", "/v1/images/generations",
                     (429, {"retry-after": "3600"}, {"error": {"code": "rate_limit_exceeded", "message": "x"}}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.assertNotIn(3600.0, self.sleeps)

    def test_timeout_keeps_charge(self):
        self.net.add("POST", "/v1/images/generations", socket.timeout("The read operation timed out"))
        code, _ = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_TIMEOUT)
        self.assertGreater(self.spent(), 0)

    def test_bad_key_message_never_echoes_key(self):
        self.net.add("POST", "/v1/images/generations", (401, {}, {"error": {
            "message": "Incorrect API key provided: %s." % KEYS["OPENAI_API_KEY"], "code": "invalid_api_key"}}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.no_secret_in(text)
        self.assertEqual(self.spent(), 0)

    def test_403_message_is_scrubbed(self):
        self.net.add("POST", "/v1/images/generations", (403, {}, {"error": {
            "message": "key %s not verified" % KEYS["OPENAI_API_KEY"], "code": "org_unverified"}}))
        _, text = self.run_paid(self.model, "-i", "prompt=x")
        self.no_secret_in(text)
        self.assertIn("<key>", text)

    def test_unpriced_size_refuses(self):
        code, text = self.run_paid(self.model, "-i", "prompt=x", "-i", "size=2048x2048")
        self.assertEqual(code, gen.EXIT_SETUP)
        self.assertIn("--assume-cost", text)
        self.assertEqual(self.net.calls, [])

    def test_assume_cost_lets_it_run(self):
        self.net.add("POST", "/v1/images/generations", (200, {}, {"data": [{"b64_json": b64(PNG)}]}))
        code, text = self.run_paid(self.model, "-i", "prompt=x", "-i", "size=2048x2048", "--assume-cost", "0.2")
        self.assertEqual(code, 0, text)
        self.assertAlmostEqual(self.ledger()["entries"][0]["cost"], 0.2)

    def test_check_lists_image_models(self):
        self.net.add("GET", "/v1/models", (200, {}, {"data": [{"id": "gpt-image-2.5-flare"}, {"id": "gpt-6-luna"}]}))
        code, text = self.run_cli("check", "--provider", "openai")
        self.assertEqual(code, 0)
        self.assertIn("gpt-image-2.5-flare", text)
        self.assertNotIn("gpt-6-luna", text)


# ---------------------------------------------------------------- Runway

def task(status, **extra):
    data = {"id": "11111111-2222-3333-4444-555555555555", "status": status, "createdAt": "2026-10-24T00:00:00Z"}
    data.update(extra)
    return data


class Runway(Base):
    keys = ("RUNWAYML_API_SECRET",)

    def setUp(self):
        Base.setUp(self)
        self.img = os.path.join(self.tmp, "start.png")
        with open(self.img, "wb") as fh:
            fh.write(PNG)

    def paid_turbo(self, *extra):
        return self.run_paid("gen4_turbo", "-i", "prompt=slow push in", "-i", "promptImage=@" + self.img,
                             "-i", "ratio=720:1280", "-i", "duration=5", "--out", self.out_dir, *extra)

    def test_success_polls_and_downloads(self):
        self.net.add("POST", "/v1/image_to_video", (200, {}, {"id": task("PENDING")["id"]}))
        self.net.add("GET", "/v1/tasks/", (200, {}, task("THROTTLED")), (200, {}, task("RUNNING")),
                     (200, {}, task("SUCCEEDED", output=["https://dnznrvs05pmza.cloudfront.net/out.mp4"],
                                    cost={"credits": 25})))
        self.net.add("GET", "cloudfront.net", (200, {"content-type": "video/mp4"}, MP4))
        code, text = self.paid_turbo()
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.files(".mp4")), 1)
        post = [c for c in self.net.calls if c[0] == "POST"][0]
        self.assertEqual(post[2]["X-Runway-Version"], "2024-11-06")
        self.assertEqual(post[2]["Authorization"], "Bearer " + KEYS["RUNWAYML_API_SECRET"])
        body = json.loads(post[3])
        self.assertEqual(body["model"], "gen4_turbo")
        self.assertEqual(body["promptText"], "slow push in")
        self.assertTrue(body["promptImage"].startswith("data:image/png;base64,"))
        self.assertIn("THROTTLED", text)
        self.assertEqual(self.sleeps[:3], [5.0, 7.5, 11.25])
        self.assertAlmostEqual(self.ledger()["entries"][0]["cost"], 0.25)
        download = [c for c in self.net.calls if "cloudfront" in c[1]][0]
        self.assertNotIn("Authorization", download[2])

    def test_text_to_video_endpoint(self):
        self.net.add("POST", "/v1/text_to_video", (200, {}, {"id": "t1"}))
        self.net.add("GET", "/v1/tasks/t1", (200, {}, task("SUCCEEDED", output=[])))
        code, text = self.run_paid("veo3.1_fast", "-i", "prompt=waves", "-i", "ratio=720:1280", "-i", "duration=4",
                                   "-i", "audio=false")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.net.count("POST", "/v1/text_to_video"), 1)

    def test_turbo_needs_an_image(self):
        code, text = self.run_paid("gen4_turbo", "-i", "prompt=x", "-i", "ratio=720:1280", "-i", "duration=5")
        self.assertEqual(code, gen.EXIT_SETUP)
        self.assertIn("promptImage", text)
        self.assertEqual(self.net.calls, [])

    def test_safety_failure_is_a_refusal_and_not_retried(self):
        self.net.add("POST", "/v1/image_to_video", (200, {}, {"id": "t1"}))
        self.net.add("GET", "/v1/tasks/t1", (200, {}, task("FAILED", failure="Input rejected", failureCode="SAFETY.INPUT.TEXT")))
        code, text = self.paid_turbo()
        self.assertEqual(code, gen.EXIT_FAILED)
        self.assertIn("SAFETY.INPUT.TEXT", text)
        self.assertEqual(self.net.count("POST", "/v1/image_to_video"), 1)
        self.assertEqual(self.ledger()["entries"][0]["status"], "refused")
        self.assertGreater(self.spent(), 0)

    def test_failure_uses_reported_cost(self):
        self.net.add("POST", "/v1/image_to_video", (200, {}, {"id": "t1"}))
        self.net.add("GET", "/v1/tasks/t1", (200, {}, task("FAILED", failure="x", failureCode="INTERNAL", cost={"credits": 0})))
        code, _ = self.paid_turbo()
        self.assertEqual(code, gen.EXIT_FAILED)
        self.assertEqual(self.spent(), 0)

    def test_429_on_create_retries(self):
        self.net.add("POST", "/v1/image_to_video", (429, {}, {"error": "Too many requests"}), (200, {}, {"id": "t1"}))
        self.net.add("GET", "/v1/tasks/t1", (200, {}, task("SUCCEEDED", output=[])))
        code, text = self.paid_turbo()
        self.assertEqual(code, 0, text)
        self.assertEqual(self.net.count("POST", "/v1/image_to_video"), 2)

    def test_load_shedding_503_on_create_retries(self):
        self.net.add("POST", "/v1/image_to_video", (503, {}, b""), (200, {}, {"id": "t1"}))
        self.net.add("GET", "/v1/tasks/t1", (200, {}, task("SUCCEEDED", output=[])))
        code, _ = self.paid_turbo()
        self.assertEqual(code, 0)

    def test_504_on_create_is_not_retried(self):
        self.net.add("POST", "/v1/image_to_video", (504, {}, b""))
        code, _ = self.paid_turbo()
        self.assertEqual(code, gen.EXIT_API)
        self.assertEqual(self.net.count("POST", "/v1/image_to_video"), 1)
        self.assertEqual(self.ledger()["entries"][0]["status"], "unknown")

    def test_400_frees_reservation(self):
        self.net.add("POST", "/v1/image_to_video", (400, {}, {"error": "ratio is not valid"}))
        code, text = self.paid_turbo()
        self.assertEqual(code, gen.EXIT_API)
        self.assertIn("ratio is not valid", text)
        self.assertEqual(self.spent(), 0)

    def test_timeout_cancels_task(self):
        self.fake_clock()
        self.net.add("POST", "/v1/image_to_video", (200, {}, {"id": "t1"}))
        self.net.add("GET", "/v1/tasks/t1", (200, {}, task("RUNNING")))
        self.net.add("DELETE", "/v1/tasks/t1", (204, {}, b""))
        code, _ = self.paid_turbo("--timeout", "30")
        self.assertEqual(code, gen.EXIT_TIMEOUT)
        self.assertEqual(self.net.count("DELETE", "/v1/tasks/t1"), 1)
        self.assertEqual(self.ledger()["entries"][0]["status"], "timed_out")
        self.assertGreater(self.spent(), 0)

    def test_failed_cancel_still_keeps_charge(self):
        self.fake_clock()
        self.net.add("POST", "/v1/image_to_video", (200, {}, {"id": "t1"}))
        self.net.add("GET", "/v1/tasks/t1", (200, {}, task("RUNNING")))
        self.net.add("DELETE", "/v1/tasks/t1", OSError("reset"))
        code, text = self.paid_turbo("--timeout", "30")
        self.assertEqual(code, gen.EXIT_TIMEOUT)
        self.assertIn("Could not cancel", text)
        self.assertGreater(self.spent(), 0)

    def test_big_image_refused_before_charge(self):
        with open(self.img, "wb") as fh:
            fh.write(b"x" * (gen.RUNWAY_DATA_URI_MAX + 1))
        code, _ = self.paid_turbo()
        self.assertEqual(code, gen.EXIT_SETUP)
        self.assertEqual(self.net.calls, [])
        self.assertEqual(self.spent(), 0)

    def test_check_shows_credit(self):
        self.net.add("GET", "/v1/organization", (200, {}, {"creditBalance": 1234, "tier": {"models": {}}, "usage": {}}))
        code, text = self.run_cli("check", "--provider", "runway")
        self.assertEqual(code, 0)
        self.assertIn("$12.34", text)


# ---------------------------------------------------------------- Google (Gemini API)

def interaction(status, **extra):
    data = {"id": "v1_abc123", "status": status, "object": "interaction", "model": "gemini-omni-1.1-flash"}
    data.update(extra)
    return data


def video_steps(**part):
    content = {"type": "video", "mime_type": "video/mp4"}
    content.update(part)
    return [{"type": "thought", "content": []}, {"type": "model_output", "content": [content]}]


class Google(Base):
    keys = ("GEMINI_API_KEY",)
    model = "gemini-omni-1.1-flash"

    def test_background_create_then_poll(self):
        self.net.add("POST", "/v1beta/interactions", (200, {}, interaction("in_progress")))
        self.net.add("GET", "/v1beta/interactions/v1_abc123", (200, {}, interaction("in_progress")),
                     (200, {}, interaction("completed", steps=video_steps(data=b64(MP4)),
                                           usage={"total_input_tokens": 100, "total_output_tokens": 57920,
                                                  "total_thought_tokens": 0})))
        code, text = self.run_paid(self.model, "-i", "prompt=waves at dawn", "-i", "aspect_ratio=9:16")
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.files(".mp4")), 1)
        post = [c for c in self.net.calls if c[0] == "POST"][0]
        self.assertEqual(post[2]["x-goog-api-key"], KEYS["GEMINI_API_KEY"])
        self.assertNotIn("key=", post[1])
        body = json.loads(post[3])
        self.assertTrue(body["background"])
        self.assertEqual(body["response_format"], {"type": "video", "aspect_ratio": "9:16", "resolution": "720p"})
        self.assertAlmostEqual(self.ledger()["entries"][0]["cost"], 57920 * 17.5 / 1e6 + 100 * 1.5 / 1e6)

    def test_image_input_goes_inline(self):
        img = os.path.join(self.tmp, "a.png")
        with open(img, "wb") as fh:
            fh.write(PNG)
        self.net.add("POST", "/v1beta/interactions", (200, {}, interaction("completed", steps=video_steps(data=b64(MP4)))))
        code, _ = self.run_paid(self.model, "-i", "prompt=steam rises", "-i", "image=@" + img)
        self.assertEqual(code, 0)
        body = json.loads([c for c in self.net.calls if c[0] == "POST"][0][3])
        self.assertEqual(body["input"][0]["type"], "image")
        self.assertEqual(body["input"][1], {"type": "text", "text": "steam rises"})

    def test_uri_output_sends_key_only_to_google(self):
        uri = "https://generativelanguage.googleapis.com/v1beta/files/abc:download?alt=media"
        self.net.add("POST", "/v1beta/interactions", (200, {}, interaction("completed", steps=video_steps(uri=uri))))
        self.net.add("GET", "/files/abc:download", (200, {}, MP4))
        code, _ = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, 0)
        dl = [c for c in self.net.calls if "download" in c[1]][0]
        self.assertEqual(dl[2].get("x-goog-api-key"), KEYS["GEMINI_API_KEY"])

    def test_blocked_on_create_is_a_refusal(self):
        self.net.add("POST", "/v1beta/interactions", (400, {}, {"error": {"code": "prohibited_content", "message": "blocked"}}))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_FAILED)
        self.assertIn("prohibited_content", text)
        self.assertEqual(self.ledger()["entries"][0]["status"], "refused")

    def test_failed_interaction_with_safety_code(self):
        self.net.add("POST", "/v1beta/interactions", (200, {}, interaction("in_progress")))
        self.net.add("GET", "/v1beta/interactions/v1_abc123",
                     (200, {}, interaction("failed", error={"code": "safety", "message": "Safety violation"})))
        code, text = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_FAILED)
        self.assertEqual(self.ledger()["entries"][0]["status"], "refused")
        self.assertIn("Do not retry", text)

    def test_quota_429_not_retried_but_rate_429_is(self):
        self.net.add("POST", "/v1beta/interactions", (429, {}, {"error": {"code": "quota_exceeded", "message": "daily"}}))
        code, _ = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_API)
        self.assertEqual(self.net.count("POST", "/interactions"), 1)
        self.net.routes.clear()
        self.net.add("POST", "/v1beta/interactions",
                     (429, {}, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "spend limit"}}),
                     (200, {}, interaction("completed", steps=video_steps(data=b64(MP4)))))
        code, text = self.run_paid(self.model, "-i", "prompt=y")
        self.assertEqual(code, 0, text)

    def test_timeout_cancels_interaction(self):
        self.fake_clock()
        self.net.add("POST", "/v1beta/interactions", (200, {}, interaction("in_progress")))
        self.net.add("GET", "/v1beta/interactions/v1_abc123", (200, {}, interaction("in_progress")))
        self.net.add("POST", "/interactions/v1_abc123/cancel", (200, {}, interaction("cancelled")))
        code, _ = self.run_paid(self.model, "-i", "prompt=x", "--timeout", "40")
        self.assertEqual(code, gen.EXIT_TIMEOUT)
        self.assertEqual(self.net.count("POST", "/cancel"), 1)
        self.assertGreater(self.spent(), 0)

    def test_completed_without_video_is_failure(self):
        self.net.add("POST", "/v1beta/interactions", (200, {}, interaction("completed", steps=[])))
        code, _ = self.run_paid(self.model, "-i", "prompt=x")
        self.assertEqual(code, gen.EXIT_FAILED)

    def test_4k_needs_assume_cost(self):
        code, text = self.run_paid(self.model, "-i", "prompt=x", "-i", "resolution=4k")
        self.assertEqual(code, gen.EXIT_SETUP)
        self.assertIn("--assume-cost", text)
        self.assertEqual(self.net.calls, [])

    def test_check_lists_video_models(self):
        self.net.add("GET", "/v1beta/models", (200, {}, {"models": [{"name": "models/gemini-omni-1.1-flash"},
                                                                    {"name": "models/gemini-4-argon"}]}))
        code, text = self.run_cli("check", "--provider", "google")
        self.assertEqual(code, 0)
        self.assertIn("gemini-omni-1.1-flash", text)
        self.assertIn("no free check for the paid tier", text)


if __name__ == "__main__":
    unittest.main()
