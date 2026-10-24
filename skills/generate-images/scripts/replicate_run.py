#!/usr/bin/env python3
"""Run Replicate models with a price check, a spend cap and safe downloads.

Changed by Aya Taleb from Replicate's run-models skill (Apache 2.0): upstream had no code.
This tool is new. Standard library only, Python 3.8+.

Commands
  check                      Is REPLICATE_API_TOKEN set and valid? (free call)
  search QUERY               Search live models on Replicate (free call)
  schema MODEL               Show a model's inputs: types, defaults, allowed values (free)
  price MODEL [--input ...]  Look up the price and estimate one run (free)
  run MODEL --input ...      Estimate, then run ONLY with --yes, inside the spend cap
  ledger                     Show this session's spend. --set-cap X / --new-session

Money rules built in
  * Nothing is spent without --yes. Without it, run is a dry run that prints the estimate.
  * One prediction per call. No batches, no parallel fan-out.
  * Each session (ends after 12 idle hours) has a cap, default $2. The estimate is
    reserved before the run starts, so two calls at once cannot both slip under the cap.
  * If the price cannot be found, the tool refuses unless you pass --assume-cost.
  * A failed create (5xx, dropped connection) is never retried blindly, since it may
    have started a paid run. Only 429 (throttled, nothing created) is retried.

Exit codes: 0 ok or dry run, 2 setup or bad input, 4 over the spend cap,
5 API error, 6 prediction failed, 7 timed out or canceled, 8 download failed.
"""
import argparse
import base64
import datetime as _dt
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid



def _local_override(name, default):
    """Tests may point the tool at a mock server, but only on this machine.

    A base URL on any other host could receive the user's token, so it is ignored.
    """
    value = os.environ.get(name, "").rstrip("/")
    if re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?(/|$)", value):
        return value
    return default


API = _local_override("REPLICATE_API_BASE", "https://api.replicate.com/v1")
SITE = _local_override("REPLICATE_SITE_BASE", "https://replicate.com")
USER_AGENT = "aya-taleb-multimedia-skills/0.1 (+https://github.com/aya-taleb/multimedia-skills)"
DEFAULT_CAP = 2.00
SESSION_IDLE_HOURS = 12
DATA_URL_LIMIT = 256 * 1024
TERMINAL = ("succeeded", "failed", "canceled", "aborted")

EXIT_OK, EXIT_SETUP, EXIT_CAP, EXIT_API, EXIT_FAILED, EXIT_TIMEOUT, EXIT_DOWNLOAD = 0, 2, 4, 5, 6, 7, 8

SETUP_HELP = """REPLICATE_API_TOKEN is not set.

1. Make an account at https://replicate.com and add a payment method or credit.
2. Copy a token from https://replicate.com/account/api-tokens
3. Put it in your shell, not in a file you might commit:
     export REPLICATE_API_TOKEN=r8_...        (macOS / Linux, add to ~/.zshrc to keep it)
     setx REPLICATE_API_TOKEN r8_...          (Windows, then open a new terminal)
4. Check it: python3 replicate_run.py check
Never paste the token into chat or a project file."""


class ToolError(Exception):
    def __init__(self, message, code=EXIT_API):
        Exception.__init__(self, message)
        self.code = code


# ---------------------------------------------------------------- HTTP (patched in tests)

def http(method, url, headers=None, body=None, timeout=60):
    """Return (status, headers_dict_lowercase, body_bytes). Never raises on HTTP status."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
        hdrs = {k.lower(): v for k, v in (err.headers.items() if err.headers else [])}
        return err.code, hdrs, err.read() or b""


def sleep(seconds):
    time.sleep(seconds)


def now():
    return _dt.datetime.now(_dt.timezone.utc)


def out(msg=""):
    print(msg)
    sys.stdout.flush()


# ---------------------------------------------------------------- token and API calls

def get_token():
    token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not token:
        raise ToolError(SETUP_HELP, EXIT_SETUP)
    return token


def api_headers(token, extra=None):
    h = {"Authorization": "Bearer " + token, "User-Agent": USER_AGENT,
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def parse_json(raw):
    try:
        return json.loads(raw.decode("utf-8") or "null")
    except (ValueError, UnicodeDecodeError):
        return None


def detail_of(raw):
    data = parse_json(raw)
    if isinstance(data, dict):
        return str(data.get("detail") or data.get("title") or data)
    return raw.decode("utf-8", "replace")[:300]


def retry_after_seconds(headers, raw, default=10.0):
    value = headers.get("retry-after")
    if value:
        try:
            return max(1.0, float(value))
        except ValueError:
            pass
    m = re.search(r"~?(\d+)\s*s", detail_of(raw))
    if m:
        return max(1.0, float(m.group(1)))
    return default


def explain_status(status, raw):
    detail = detail_of(raw)
    if status == 401:
        return "Replicate says the token is not valid (401). Make a new one at https://replicate.com/account/api-tokens."
    if status == 402:
        return "Replicate says there is not enough credit (402): %s. Add credit at https://replicate.com/account/billing." % detail
    if status == 404:
        return "Not found (404): %s. Check the model name with: replicate_run.py search" % detail
    if status == 422:
        return "Replicate rejected the input (422): %s. Check it with: replicate_run.py schema MODEL" % detail
    if status == 429:
        return "Rate limited (429): %s" % detail
    return "Replicate returned %s: %s" % (status, detail)


def api_get(token, path_or_url, retries=3):
    url = path_or_url if path_or_url.startswith("http") else API + path_or_url
    for attempt in range(retries + 1):
        status, headers, raw = http("GET", url, api_headers(token))
        if status == 429 and attempt < retries:
            wait = retry_after_seconds(headers, raw)
            out("Rate limited. Waiting %ds before trying again." % wait)
            sleep(wait)
            continue
        if status >= 500 and attempt < retries:
            sleep(2 * (attempt + 1))
            continue
        if status != 200:
            raise ToolError(explain_status(status, raw))
        return parse_json(raw)
    raise ToolError("Gave up after repeated rate limits.")


# ---------------------------------------------------------------- models and schemas

def split_model(ref):
    m = re.match(r"^([\w.-]+)/([\w.-]+)(?::([0-9a-f]{64}))?$", ref.strip())
    if not m:
        raise ToolError("Model must look like owner/name or owner/name:<64-char version>. Got %r." % ref, EXIT_SETUP)
    return m.group(1), m.group(2), m.group(3)


def get_model(token, ref):
    owner, name, version = split_model(ref)
    model = api_get(token, "/models/%s/%s" % (owner, name))
    if version:
        ver = api_get(token, "/models/%s/%s/versions/%s" % (owner, name, version))
        model["latest_version"] = ver
        model["_pinned_version"] = version
    return model


def input_schema(model):
    try:
        schemas = model["latest_version"]["openapi_schema"]["components"]["schemas"]
        return schemas["Input"], schemas
    except (KeyError, TypeError):
        return {"properties": {}, "required": []}, {}


def resolve_prop(prop, schemas):
    """Inputs with enums are often allOf: [{$ref: '#/components/schemas/x'}]."""
    merged = dict(prop)
    for part in prop.get("allOf", []):
        ref = part.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            merged.update(schemas.get(ref.rsplit("/", 1)[1], {}))
    return merged


def validate_input(model, data):
    schema, schemas = input_schema(model)
    props = schema.get("properties", {})
    problems = []
    if not props:
        return problems  # no schema to check against
    for key in schema.get("required", []):
        if key not in data:
            problems.append("missing required input '%s'" % key)
    for key, value in data.items():
        if key not in props:
            problems.append("unknown input '%s' (the model has: %s)" % (key, ", ".join(sorted(props))))
            continue
        prop = resolve_prop(props[key], schemas)
        if "enum" in prop and value not in prop["enum"]:
            problems.append("'%s' must be one of %s" % (key, prop["enum"]))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in prop and value < prop["minimum"]:
                problems.append("'%s' is below the minimum %s" % (key, prop["minimum"]))
            if "maximum" in prop and value > prop["maximum"]:
                problems.append("'%s' is above the maximum %s" % (key, prop["maximum"]))
    return problems


def schema_defaults(model):
    schema, schemas = input_schema(model)
    defaults = {}
    for key, prop in schema.get("properties", {}).items():
        prop = resolve_prop(prop, schemas)
        if "default" in prop:
            defaults[key] = prop["default"]
    return defaults


def describe_schema(model):
    schema, schemas = input_schema(model)
    required = set(schema.get("required", []))
    props = schema.get("properties", {})
    rows = sorted(props.items(), key=lambda kv: kv[1].get("x-order", 999))
    lines = []
    for key, prop in rows:
        prop = resolve_prop(prop, schemas)
        bits = [prop.get("type", "any")]
        if prop.get("format") == "uri":
            bits.append("file or URL")
        if key in required:
            bits.append("REQUIRED")
        if "default" in prop:
            bits.append("default=%s" % json.dumps(prop["default"]))
        if "enum" in prop:
            bits.append("one of %s" % prop["enum"])
        if "minimum" in prop or "maximum" in prop:
            bits.append("range %s..%s" % (prop.get("minimum", ""), prop.get("maximum", "")))
        lines.append("- %s (%s): %s" % (key, ", ".join(bits), (prop.get("description") or "").strip()))
    return "\n".join(lines) or "(this model publishes no input schema)"


# ---------------------------------------------------------------- price lookup

UNIT_WORDS = {"thousand": 1000.0, "million": 1000000.0, "hundred": 100.0}


def parse_money(text):
    m = re.search(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj
        for value in obj.values():
            hit = find_key(value, key)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for value in obj:
            hit = find_key(value, key)
            if hit is not None:
                return hit
    return None


def parse_price_page(html):
    """Pull the pricing data Replicate embeds in a model page.

    The API has no price field, so this reads the JSON blocks on the public model page.
    Returns {"tiers": [...], "per_second": float|None, "typical_run": float|None}
    or None when nothing usable is found (the page layout may have changed).
    """
    blocks = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.S)
    for block in blocks:
        if "billingConfig" not in block and "p50price" not in block:
            continue
        try:
            data = json.loads(block)
        except ValueError:
            continue
        holder = find_key(data, "billingConfig") or find_key(data, "p50price")
        if holder is None:
            continue
        tiers = []
        config = holder.get("billingConfig") or {}
        for tier in config.get("current_tiers") or []:
            criteria = [("%g" % c["value"]) if isinstance(c.get("value"), (int, float)) else str(c.get("value", ""))
                        for c in tier.get("criteria") or []]
            for price in tier.get("prices") or []:
                amount = parse_money(price.get("price", ""))
                if amount is None:
                    continue
                title = (price.get("title") or "").lower()
                divisor = 1.0
                for word, size in UNIT_WORDS.items():
                    if word in title:
                        divisor = size
                tiers.append({
                    "metric": price.get("metric", ""),
                    "unit": price.get("metric_display") or price.get("metric", ""),
                    "per_unit": amount / divisor,
                    "label": "%s %s" % (price.get("price"), price.get("title", "")),
                    "criteria": criteria,
                })
            if not tier.get("prices") and tier.get("description"):
                tiers.append({"metric": "external", "unit": "", "per_unit": None,
                              "label": tier.get("description"), "criteria": []})
        per_second = holder.get("price")
        return {
            "tiers": tiers,
            "per_second": parse_money(per_second) if isinstance(per_second, str) and "second" in per_second else None,
            "typical_run": parse_money(holder.get("p50price", "")) if holder.get("p50price") else None,
        }
    return None


def fetch_price(ref):
    owner, name, _ = split_model(ref)
    status, _, raw = http("GET", "%s/%s/%s" % (SITE, owner, name), {"User-Agent": USER_AGENT})
    if status != 200:
        return None
    return parse_price_page(raw.decode("utf-8", "replace"))


COUNT_KEYS = ("num_outputs", "num_images", "number_of_images", "n", "batch_size", "max_images", "count")
DURATION_KEYS = ("duration", "seconds", "duration_seconds", "video_length", "length", "num_seconds")


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*s?\s*$", value)
        if m:
            return float(m.group(1))
    return None


def units_for(metric, values):
    if metric.endswith("_output_count"):  # image, video or audio files out
        for key in COUNT_KEYS:
            if key in values and _number(values[key]):
                return _number(values[key])
        return 1.0
    if metric.endswith("duration_seconds"):
        for key in DURATION_KEYS:
            if key in values and _number(values[key]):
                return _number(values[key])
        frames, fps = _number(values.get("num_frames")), _number(values.get("fps") or values.get("frames_per_second"))
        if frames and fps:
            return frames / fps
        return None
    text = sum(len(v) for v in values.values() if isinstance(v, str))
    if metric.startswith("token"):
        return max(1.0, text / 3.0)  # about 4 chars per token; 3 keeps the guess high
    if metric.startswith("character"):
        return float(max(1, text))
    return None


def tier_matches(tier, values):
    if not tier["criteria"]:
        return True
    flat = set()
    for key, value in values.items():
        flat.add(str(value).lower())
        num = _number(value)
        if num is not None:
            flat.add(("%g" % num).lower())  # 6, "6", "6s" and 6.0 all match a tier value of 6
        if isinstance(value, bool):  # e.g. generate_audio=False matches "without_audio"
            stem = key.split("_")[-1]
            flat.add(("with_" if value else "without_") + stem)
    return all(str(c).lower() in flat for c in tier["criteria"])


def estimate_cost(price, user_input, defaults):
    """Return (cost or None, explanation lines). Picks the highest price when unsure."""
    values = dict(defaults or {})
    values.update(user_input or {})
    if price is None:
        return None, ["Could not read the price from the model page."]
    tiers = [t for t in price["tiers"] if t["per_unit"] is not None]
    if any(t["metric"] == "external" for t in price["tiers"]) and not tiers:
        return None, ["This model bills through another company's key: %s" % price["tiers"][0]["label"]]
    if tiers:
        matching = [t for t in tiers if tier_matches(t, values)]
        note = []
        if not matching:
            matching = tiers
            note.append("Could not tell which price tier applies, so the estimate uses the most expensive one.")
        best = None
        for tier in matching:
            units = units_for(tier["metric"], values)
            if units is None:
                continue
            cost = units * tier["per_unit"]
            if best is None or cost > best[0]:
                best = (cost, tier, units)
        if best is None:
            return None, ["Price is %s, but the tool cannot tell how many units this input uses." % tiers[0]["label"]]
        cost, tier, units = best
        lines = ["Price: %s" % tier["label"].strip(),
                 "This run: %g %s(s) x $%.6g = $%.4f" % (units, tier["unit"], tier["per_unit"], cost)]
        return cost, lines + note
    if price.get("typical_run"):
        cost = price["typical_run"] * 2
        lines = ["Billed by GPU time%s. A typical run costs about $%.4f." % (
            " ($%.6f per second)" % price["per_second"] if price.get("per_second") else "", price["typical_run"]),
            "Estimate doubles that to $%.4f to allow for a cold boot or a slow run. Real cost can differ." % cost]
        return cost, lines
    return None, ["The model page lists no usable price."]


# ---------------------------------------------------------------- spend ledger

def founder_home():
    """$FOUNDER_HOME if set, else ~/.founder. Claude Code protects ~/.claude, so not there."""
    return os.path.expanduser(os.environ.get("FOUNDER_HOME") or "~/.founder")


def ledger_path():
    """$MEDIA_LEDGER if set, else <founder home>/media/spend-ledger.json."""
    if os.environ.get("MEDIA_LEDGER"):
        return os.path.expanduser(os.environ["MEDIA_LEDGER"])
    return os.path.join(founder_home(), "media", "spend-ledger.json")


class LedgerLock(object):
    def __init__(self, path):
        self.lock = path + ".lock"

    def __enter__(self):
        deadline = time.time() + 15
        while True:
            try:
                fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.lock) > 120:
                        os.remove(self.lock)  # stale lock from a crashed run
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise ToolError("The spend ledger is locked by another run. Try again in a minute.", EXIT_API)
                time.sleep(0.2)

    def __exit__(self, *exc):
        try:
            os.remove(self.lock)
        except OSError:
            pass


def load_ledger(path=None):
    path = path or ledger_path()
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
    data.setdefault("cap", DEFAULT_CAP)
    data.setdefault("entries", [])
    last = data.get("last_activity")
    stale = True
    if last:
        try:
            stale = now() - _dt.datetime.fromisoformat(last) > _dt.timedelta(hours=SESSION_IDLE_HOURS)
        except ValueError:
            stale = True
    if stale or not data.get("session_started"):
        data["session_started"] = now().isoformat()
        data["entries"] = []
    return data


def save_ledger(data, path=None):
    path = path or ledger_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    data["last_activity"] = now().isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)


def spent(data):
    return round(sum(e.get("cost", 0.0) for e in data["entries"]), 6)


def reserve(model_ref, cost, note):
    """Add a pending charge if it fits under the cap. Returns the entry id."""
    path = ledger_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with LedgerLock(path):
        data = load_ledger(path)
        total = spent(data)
        if total + cost > data["cap"] + 1e-9:
            raise ToolError(
                "Stopped: this run (about $%.4f) would take the session past its $%.2f cap "
                "($%.4f spent so far). Nothing was run. If you want to spend more, ask the user, then: "
                "replicate_run.py ledger --set-cap <dollars>" % (cost, data["cap"], total), EXIT_CAP)
        entry = {"id": uuid.uuid4().hex[:12], "model": model_ref, "cost": round(cost, 6),
                 "status": "pending", "note": note, "at": now().isoformat()}
        data["entries"].append(entry)
        save_ledger(data, path)
        return entry["id"]


def settle(entry_id, status, prediction_id=None, cost=None):
    path = ledger_path()
    with LedgerLock(path):
        data = load_ledger(path)
        for entry in data["entries"]:
            if entry["id"] == entry_id:
                entry["status"] = status
                if prediction_id:
                    entry["prediction"] = prediction_id
                if cost is not None:
                    entry["cost"] = round(cost, 6)
        save_ledger(data, path)


# ---------------------------------------------------------------- inputs

def load_input(args):
    data = {}
    if args.input_file:
        with open(args.input_file, encoding="utf-8") as fh:
            data.update(json.load(fh))
    if args.input:
        try:
            data.update(json.loads(args.input))
        except ValueError as exc:
            raise ToolError("--input is not valid JSON: %s" % exc, EXIT_SETUP)
    for pair in args.set or []:
        if "=" not in pair:
            raise ToolError("-i needs key=value, got %r" % pair, EXIT_SETUP)
        key, value = pair.split("=", 1)
        try:
            data[key] = json.loads(value)
        except ValueError:
            data[key] = value
    return data


def multipart(fields, file_field, filename, content, content_type):
    boundary = "----aya" + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, key, value)).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n" % (boundary, file_field, filename, content_type)).encode())
    parts.append(content)
    parts.append(("\r\n--%s--\r\n" % boundary).encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def prepare_files(token, data):
    """Values like "@photo.jpg" become a data URL (small) or an uploaded file URL (large)."""
    for key, value in list(data.items()):
        if not (isinstance(value, str) and value.startswith("@")):
            continue
        path = os.path.expanduser(value[1:])
        if not os.path.isfile(path):
            raise ToolError("Input '%s' points to %s, which is not a file." % (key, path), EXIT_SETUP)
        with open(path, "rb") as fh:
            content = fh.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if len(content) <= DATA_URL_LIMIT:
            data[key] = "data:%s;base64,%s" % (ctype, base64.b64encode(content).decode())
            continue
        body, header = multipart({"type": ctype}, "content", os.path.basename(path), content, ctype)
        status, _, raw = http("POST", API + "/files",
                              {"Authorization": "Bearer " + token, "User-Agent": USER_AGENT, "Content-Type": header},
                              body, timeout=300)
        if status not in (200, 201):
            raise ToolError("Could not upload %s: %s" % (path, explain_status(status, raw)))
        data[key] = parse_json(raw)["urls"]["get"]
    return data


# ---------------------------------------------------------------- running

def create_prediction(token, model, ref, data, deadline):
    owner, name, version = split_model(ref)
    headers = api_headers(token, {"Cancel-After": deadline} if deadline else None)
    if version or not model.get("is_official", False):
        version = version or (model.get("latest_version") or {}).get("id")
        if not version:
            raise ToolError("This model has no published version to run.", EXIT_SETUP)
        url, body = API + "/predictions", {"version": "%s/%s:%s" % (owner, name, version), "input": data}
    else:
        url, body = API + "/models/%s/%s/predictions" % (owner, name), {"input": data}
    payload = json.dumps(body).encode()
    for attempt in range(4):
        try:
            status, hdrs, raw = http("POST", url, headers, payload, timeout=60)
        except (urllib.error.URLError, OSError) as exc:
            raise ToolError(
                "The connection dropped while creating the prediction (%s). It may or may not have started, "
                "so the tool will not retry. Check https://replicate.com/predictions before running again." % exc)
        if status == 429 and attempt < 3:
            wait = retry_after_seconds(hdrs, raw)
            out("Rate limited before the run was created (nothing charged). Waiting %ds." % wait)
            sleep(wait)
            continue
        if status in (200, 201, 202):
            return parse_json(raw)
        if status >= 500:
            raise ToolError(
                "Replicate had a server error (%s) while creating the run. It may have started anyway, "
                "so the tool will not retry. Check https://replicate.com/predictions first." % status)
        raise ToolError(explain_status(status, raw))
    raise ToolError("Still rate limited after 3 waits. Try again in a few minutes.")


def wait_for(token, prediction, timeout):
    started = time.time()
    delay, warned = 1.0, False
    pred = prediction
    while pred.get("status") not in TERMINAL:
        elapsed = time.time() - started
        if elapsed > timeout:
            out("No result after %ds. Canceling so it stops billing." % timeout)
            cancel_url = (pred.get("urls") or {}).get("cancel") or "%s/predictions/%s/cancel" % (API, pred["id"])
            http("POST", cancel_url, api_headers(token))
            pred["status"] = "timed_out"
            return pred
        if pred.get("status") == "starting" and elapsed > 20 and not warned:
            out("Still starting. That usually means a cold boot (the model is loading). Waiting.")
            warned = True
        sleep(delay)
        delay = min(delay * 1.5, 10.0)
        get_url = (pred.get("urls") or {}).get("get") or "%s/predictions/%s" % (API, pred["id"])
        try:
            pred = api_get(token, get_url)
        except ToolError as exc:
            out("Could not check status (%s). Trying again." % exc)
        except (urllib.error.URLError, OSError) as exc:
            out("Network hiccup while checking status (%s). Trying again." % exc)
    return pred


def output_urls(output):
    found = []
    if isinstance(output, str):
        if output.startswith(("http://", "https://", "data:")):
            found.append(output)
    elif isinstance(output, list):
        for item in output:
            found.extend(output_urls(item))
    elif isinstance(output, dict):
        for item in output.values():
            found.extend(output_urls(item))
    return found


def ext_for(url, content_type):
    if url.startswith("data:"):
        return mimetypes.guess_extension(url[5:].split(";", 1)[0]) or ".bin"
    path_ext = os.path.splitext(urllib.parse.urlparse(url).path)[1]
    if path_ext and len(path_ext) <= 6:
        return path_ext
    return mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ".bin"


def slugify(text, limit=40):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "output").lower()).strip("-")
    return slug[:limit].strip("-") or "output"


def download_all(token, urls, out_dir, stem):
    os.makedirs(out_dir, exist_ok=True)
    saved, failed = [], []
    for n, url in enumerate(urls, 1):
        if url.startswith("data:"):
            header, _, payload = url.partition(",")
            content = base64.b64decode(payload) if ";base64" in header else urllib.parse.unquote_to_bytes(payload)
            path = os.path.join(out_dir, "%s-%d%s" % (stem, n, ext_for(url, None)))
            with open(path, "wb") as fh:
                fh.write(content)
            saved.append(path)
            continue
        headers = {"User-Agent": USER_AGENT}
        if urllib.parse.urlparse(url).netloc == "api.replicate.com":
            headers["Authorization"] = "Bearer " + token
        for attempt in range(3):
            try:
                status, hdrs, raw = http("GET", url, headers, timeout=300)
            except (urllib.error.URLError, OSError):
                status, hdrs, raw = 0, {}, b""
            if status == 200 and raw:
                path = os.path.join(out_dir, "%s-%d%s" % (stem, n, ext_for(url, hdrs.get("content-type"))))
                with open(path, "wb") as fh:
                    fh.write(raw)
                saved.append(path)
                break
            sleep(2 * (attempt + 1))
        else:
            failed.append(url)
    return saved, failed


def cmd_run(args):
    token = get_token()
    data = load_input(args)
    model = get_model(token, args.model)
    # "@file" inputs count as present; their enum and range checks do not apply until uploaded
    problems = validate_input(model, {k: ("https://local.file/" + v[1:] if isinstance(v, str) and v.startswith("@") else v)
                                      for k, v in data.items()})
    if problems:
        raise ToolError("Input problems, nothing was run:\n  - " + "\n  - ".join(problems), EXIT_SETUP)
    if args.assume_cost is not None:
        cost, lines = args.assume_cost, ["Using the cost you gave: $%.4f (the price was not looked up)." % args.assume_cost]
    else:
        cost, lines = estimate_cost(fetch_price(args.model), data, schema_defaults(model))
    for line in lines:
        out(line)
    if cost is None:
        raise ToolError("No estimate, so nothing was run. Read the price on https://replicate.com/%s#pricing, "
                        "tell the user, and if they agree rerun with --assume-cost <dollars>."
                        % "/".join(split_model(args.model)[:2]), EXIT_SETUP)
    if args.max_cost is not None and cost > args.max_cost:
        raise ToolError("Estimate $%.4f is over --max-cost $%.4f. Nothing was run." % (cost, args.max_cost), EXIT_CAP)
    ledger = load_ledger()
    remaining = ledger["cap"] - spent(ledger)
    out("Session: $%.4f spent of a $%.2f cap. $%.4f left." % (spent(ledger), ledger["cap"], remaining))
    if not args.yes:
        out("DRY RUN. Nothing was spent. Show the user the estimate, and rerun with --yes only after they say yes.")
        return EXIT_OK
    data = prepare_files(token, data)  # free; done first so a bad path never leaves a reserved charge
    entry = reserve(args.model, cost, args.label or "")
    try:
        pred = create_prediction(token, model, args.model, data, args.deadline)
    except ToolError as exc:
        if "may have started" in str(exc) or "may or may not" in str(exc):
            settle(entry, "unknown")  # keep the charge reserved: it might be real
        else:
            settle(entry, "not-created", cost=0.0)
        raise
    out("Started prediction %s (%s)." % (pred.get("id"), (pred.get("urls") or {}).get("web", "")))
    pred = wait_for(token, pred, args.timeout)
    status = pred.get("status")
    stem = "%s-%s" % (slugify(args.label or data.get("prompt", "")), (pred.get("id") or "run")[:8])
    code, saved = EXIT_OK, []
    if status == "aborted":
        settle(entry, "aborted", pred.get("id"), cost=0.0)
        out("Replicate aborted the run before it started. Not billed.")
        code = EXIT_TIMEOUT
    elif status in ("canceled", "timed_out"):
        settle(entry, status, pred.get("id"))
        out("Run %s. You may be billed for the time it ran, so the estimate stays on the ledger." % status)
        code = EXIT_TIMEOUT
    elif status == "failed":
        settle(entry, "failed", pred.get("id"))
        out("The model failed: %s" % (pred.get("error") or "no error text"))
        logs = (pred.get("logs") or "").strip().splitlines()[-8:]
        if logs:
            out("Last log lines:\n  " + "\n  ".join(logs))
        out("The estimate stays on the ledger to be safe. Tell the user before any retry, and never rerun "
            "the same input unchanged.")
        code = EXIT_FAILED
    else:
        settle(entry, "succeeded", pred.get("id"))
        urls = output_urls(pred.get("output"))
        saved, failed = download_all(token, urls, args.out, stem)
        for path in saved:
            out("Saved %s" % path)
        if not urls and pred.get("output") is not None:
            out("Output (no files): %s" % json.dumps(pred.get("output"))[:2000])
        if failed:
            out("Could not download %d file(s). The links expire one hour after the run:\n  %s"
                % (len(failed), "\n  ".join(failed)))
            code = EXIT_DOWNLOAD
    # A sidecar for every run that reached Replicate, so failed spend is on record too.
    os.makedirs(args.out, exist_ok=True)
    record = {"model": args.model, "prediction": pred.get("id"), "status": status, "error": pred.get("error"),
              "estimate_usd": round(cost, 6),
              "input": {k: (v if not (isinstance(v, str) and v.startswith("data:")) else "<file>") for k, v in data.items()},
              "files": saved, "metrics": pred.get("metrics"), "created_at": pred.get("created_at")}
    sidecar = os.path.join(args.out, stem + ".json")
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    out("Run record: %s" % sidecar)
    ledger = load_ledger()
    out("Session spend: $%.4f of the $%.2f cap. $%.4f left." % (spent(ledger), ledger["cap"], ledger["cap"] - spent(ledger)))
    return code


def cmd_price(args):
    data = load_input(args)
    defaults = {}
    if os.environ.get("REPLICATE_API_TOKEN"):
        try:
            defaults = schema_defaults(get_model(get_token(), args.model))
        except ToolError:
            defaults = {}
    price = fetch_price(args.model)
    if price:
        for tier in price["tiers"]:
            crit = (" when %s" % ", ".join(tier["criteria"])) if tier["criteria"] else ""
            out("- %s%s" % (tier["label"].strip(), crit))
    cost, lines = estimate_cost(price, data, defaults)
    for line in lines:
        out(line)
    out("Estimate for one run: %s" % ("$%.4f" % cost if cost is not None else "unknown"))
    out("Source: %s/%s#pricing (read %s)" % (SITE, "/".join(split_model(args.model)[:2]), _dt.date.today().isoformat()))
    return EXIT_OK


def cmd_search(args):
    token = get_token()
    data = api_get(token, "/search?" + urllib.parse.urlencode({"query": args.query, "limit": args.limit}))
    for item in data.get("models", []):
        model, meta = item.get("model", {}), item.get("metadata", {})
        latest = (model.get("latest_version") or {}).get("created_at", "")[:10]
        out("- %s/%s | official: %s | runs: %s | updated: %s | tags: %s\n    %s" % (
            model.get("owner"), model.get("name"), model.get("is_official", "?"), model.get("run_count", "?"),
            latest or "?", ", ".join(meta.get("tags", [])), (model.get("description") or "").strip()[:160]))
    for coll in data.get("collections", []):
        out("collection: %s (%s)" % (coll.get("name"), coll.get("slug")))
    if not data.get("models"):
        out("No models matched. Try a shorter query, like the task: 'text to video'.")
    return EXIT_OK


def cmd_schema(args):
    token = get_token()
    model = get_model(token, args.model)
    out("%s/%s | official: %s | version: %s" % (model.get("owner"), model.get("name"), model.get("is_official"),
                                                (model.get("latest_version") or {}).get("id", "?")[:12]))
    out(describe_schema(model))
    return EXIT_OK


def cmd_check(_args):
    token = get_token()
    data = api_get(token, "/account")
    out("Token works. Account: %s (%s)." % (data.get("username"), data.get("type")))
    return EXIT_OK


def cmd_ledger(args):
    path = ledger_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with LedgerLock(path):
        data = load_ledger(path)
        if args.new_session:
            data["entries"] = []
            data["session_started"] = now().isoformat()
        if args.set_cap is not None:
            if args.set_cap < 0:
                raise ToolError("The cap cannot be negative.", EXIT_SETUP)
            data["cap"] = args.set_cap
        save_ledger(data, path)
    out("Session started %s. Cap $%.2f. Spent $%.4f." % (data["session_started"][:16], data["cap"], spent(data)))
    for e in data["entries"]:
        out("- %s %s $%.4f %s %s" % (e["at"][:16], e["model"], e["cost"], e["status"], e.get("prediction", "")))
    out("Ledger file: %s" % path)
    return EXIT_OK


def build_parser():
    p = argparse.ArgumentParser(description="Run Replicate models with a price check and a spend cap.")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("check", help="check the token (free)")
    s = sub.add_parser("search", help="search live models (free)")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s = sub.add_parser("schema", help="show a model's inputs (free)")
    s.add_argument("model")
    for name in ("price", "run"):
        s = sub.add_parser(name)
        s.add_argument("model")
        s.add_argument("--input", help="JSON object of inputs")
        s.add_argument("--input-file", help="JSON file of inputs")
        s.add_argument("-i", "--set", action="append", help="key=value (value read as JSON if it parses)")
        if name == "run":
            s.add_argument("--yes", action="store_true", help="the user said yes to the estimate: spend it")
            s.add_argument("--assume-cost", type=float, help="use this estimate when the price lookup fails")
            s.add_argument("--max-cost", type=float, help="refuse if this one run is estimated above this")
            s.add_argument("--out", default="media/images", help="folder to save outputs (default media/images)")
            s.add_argument("--label", help="short name for the files")
            s.add_argument("--timeout", type=int, default=600, help="seconds to wait before canceling")
            s.add_argument("--deadline", default="15m", help="Replicate auto-cancels after this (Cancel-After)")
    s = sub.add_parser("ledger", help="show or change the session spend")
    s.add_argument("--set-cap", type=float, help="new cap in dollars (only when the user asks)")
    s.add_argument("--new-session", action="store_true", help="start a new session (spend back to $0)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {"check": cmd_check, "search": cmd_search, "schema": cmd_schema, "price": cmd_price,
                "run": cmd_run, "ledger": cmd_ledger}
    if args.cmd not in handlers:
        build_parser().print_help()
        return EXIT_SETUP
    try:
        return handlers[args.cmd](args)
    except ToolError as exc:
        out(str(exc))
        return exc.code
    except (urllib.error.URLError, OSError) as exc:
        out("Network problem: %s. Check your connection and try again." % exc)
        return EXIT_API


if __name__ == "__main__":
    sys.exit(main())
