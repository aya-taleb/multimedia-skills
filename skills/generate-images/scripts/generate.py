#!/usr/bin/env python3
"""Make AI images and video with the provider account you already have.

Providers: replicate, cloudflare (Workers AI), openai (Images API), runway, google (Gemini API).
Every provider keeps the same money rules, and all of them share one spend ledger.

Commands
  providers [--order a,b,c]   Which keys are set, your preferred order, the default per kind
  check [--provider P]        Free key check for every provider with a key set (or just P)
  models [--provider P] [--kind image|video] [--query Q]
                              Live model list where the provider has one, with table prices (free)
  schema MODEL                The inputs the tool accepts for a model (free)
  price MODEL [-i k=v ...]    Estimate one run (free, no key needed)
  run MODEL [-i k=v ...]      Estimate, then run ONLY with --yes, inside the spend cap
  ledger                      This session's spend across providers. --set-cap X / --new-session

Money rules built in (same as replicate_run.py, which still works on its own)
  * Nothing is spent without --yes. Without it, run is a dry run that prints the estimate.
  * One request per call. No batches in the background, no parallel fan-out.
  * One session cap for all providers, default $2. The estimate is reserved before the run.
  * Providers with no price API use prices.json (dated, with sources). A model that is not
    in the table needs --assume-cost, after a person reads the price.
  * Only a 429 that means "slow down" is retried. A 429 that means "out of credit" is not.
    A dropped connection, timeout or 5xx while creating a run is never retried, since it may
    have started a paid run.
  * Keys come only from environment variables. They are never printed or written to a file.

Exit codes: 0 ok or dry run, 2 setup or bad input, 4 over the spend cap,
5 API error, 6 run failed or refused, 7 timed out or canceled, 8 download failed.
"""
import argparse
import base64
import datetime as _dt
import json
import math
import mimetypes
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import replicate_run as rr  # noqa: E402  (shared ledger, HTTP and Replicate engine)

ToolError = rr.ToolError
EXIT_OK, EXIT_SETUP, EXIT_CAP, EXIT_API = rr.EXIT_OK, rr.EXIT_SETUP, rr.EXIT_CAP, rr.EXIT_API
EXIT_FAILED, EXIT_TIMEOUT, EXIT_DOWNLOAD = rr.EXIT_FAILED, rr.EXIT_TIMEOUT, rr.EXIT_DOWNLOAD
out = rr.out

CF_API = rr._local_override("CLOUDFLARE_API_BASE", "https://api.cloudflare.com/client/v4")
OPENAI_API = rr._local_override("OPENAI_API_BASE", "https://api.openai.com/v1")
RUNWAY_API = rr._local_override("RUNWAY_API_BASE", "https://api.dev.runwayml.com")
GEMINI_API = rr._local_override("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta")
RUNWAY_VERSION = "2024-11-06"
RUNWAY_DATA_URI_MAX = 3300000  # Runway: a data URI image must stay under 5 MB encoded (about 3.3 MB of file)
PRICES_PATH = os.path.join(HERE, "prices.json")
MAX_WAIT = 120  # seconds; a longer Retry-After stops the run instead of sleeping
ORDER = ["replicate", "cloudflare", "openai", "runway", "google"]

PROVIDERS = {
    "replicate": {"env": ["REPLICATE_API_TOKEN"], "kinds": ["image", "video"],
                  "help": "1. Account at https://replicate.com with a payment method or credit.\n"
                          "2. Token from https://replicate.com/account/api-tokens\n"
                          "3. export REPLICATE_API_TOKEN=r8_..."},
    "cloudflare": {"env": ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"], "kinds": ["image"],
                   "help": "1. Cloudflare dashboard > Workers AI > Use REST API.\n"
                           "2. Create a Workers AI API token (it needs Workers AI Read and Edit) and copy the Account ID.\n"
                           "3. export CLOUDFLARE_ACCOUNT_ID=...  and  export CLOUDFLARE_API_TOKEN=..."},
    "openai": {"env": ["OPENAI_API_KEY"], "kinds": ["image"],
               "help": "1. Key from https://platform.openai.com/api-keys (the project needs credit).\n"
                       "2. export OPENAI_API_KEY=sk-..."},
    "runway": {"env": ["RUNWAYML_API_SECRET"], "kinds": ["video"],
               "help": "1. Key from the Runway developer portal, https://dev.runway.com (buy credits for the project).\n"
                       "2. export RUNWAYML_API_SECRET=..."},
    "google": {"env": ["GEMINI_API_KEY"], "alt_env": "GOOGLE_API_KEY", "kinds": ["video"],
               "help": "1. Key from https://aistudio.google.com/api-keys on a paid tier project (video is not on the free tier).\n"
                       "2. export GEMINI_API_KEY=...   (GOOGLE_API_KEY also works and wins if both are set)"},
}

KEY_RULE = ("Put it in your shell, not in a file you might commit (add the export line to ~/.zshrc to keep it).\n"
            "Never paste a key into chat or a project file.")

# 429s that mean money or quota ran out: waiting does not help, so they are not retried.
NO_RETRY_429 = {
    "cloudflare": {"3036"},
    "openai": {"credit_balance_exhausted", "organization_spend_limit_exceeded", "project_spend_limit_exceeded",
               "organization_usage_limit_exceeded", "insufficient_quota"},
    "google": {"quota_exceeded"},
    "runway": set(),
}
GOOGLE_BLOCKED = {"safety", "recitation", "language", "prohibited_content", "spii", "blocklist", "image_safety",
                  "image_prohibited_content", "image_recitation", "image_other", "content_blocked"}


class MaybeStarted(ToolError):
    """The create call ended in a way that may have started a paid run. Keep the charge."""


# ---------------------------------------------------------------- small helpers

def sleep(seconds):
    rr.sleep(seconds)


def parse_json(raw):
    return rr.parse_json(raw)


def scrub(text, secrets):
    text = str(text)
    for secret in secrets:
        if secret and len(secret) >= 6:
            text = text.replace(secret, "<key>")
    return text


def err_info(raw):
    """Return (code, message) from any of the five providers' error bodies."""
    data = parse_json(raw)
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            code = err.get("code") or err.get("status") or err.get("type") or ""
            if err.get("type") == "insufficient_quota":
                code = "insufficient_quota"
            return str(code), str(err.get("message") or err)
        if isinstance(err, str):
            return "", err
        errs = data.get("errors")
        if isinstance(errs, list) and errs and isinstance(errs[0], dict):
            return str(errs[0].get("code", "")), str(errs[0].get("message", ""))
        if data.get("detail"):
            return "", str(data["detail"])
    return "", raw.decode("utf-8", "replace")[:300]


def is_timeout(exc):
    return isinstance(exc, socket.timeout) or "timed out" in str(exc).lower()


def founder_media():
    return os.path.join(rr.founder_home(), "media")


def config_path():
    return os.path.join(founder_media(), "providers.json")


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        order = [p for p in data.get("order", []) if p in PROVIDERS]
        return {"order": order}
    except (OSError, ValueError):
        return {}


def save_config(order):
    os.makedirs(founder_media(), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump({"order": order, "saved": _dt.date.today().isoformat()}, fh, indent=2)


def has_key(provider):
    info = PROVIDERS[provider]
    if info.get("alt_env") and os.environ.get(info["alt_env"], "").strip():
        return True
    return all(os.environ.get(name, "").strip() for name in info["env"])


def get_keys(provider):
    info = PROVIDERS[provider]
    if provider == "google":
        key = os.environ.get("GOOGLE_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
        if key:
            return {"key": key}
    elif has_key(provider):
        keys = {name: os.environ[name].strip() for name in info["env"]}
        if provider == "cloudflare" and not re.match(r"^[A-Za-z0-9]{8,64}$", keys["CLOUDFLARE_ACCOUNT_ID"]):
            raise ToolError("CLOUDFLARE_ACCOUNT_ID does not look like an account ID (letters and digits only).", EXIT_SETUP)
        return keys
    raise ToolError("%s is not set.\n\n%s\n%s\nCheck it with: python3 generate.py check --provider %s"
                    % (" and ".join(info["env"]), info["help"], KEY_RULE, provider), EXIT_SETUP)


def secret_values(keys):
    return [v for k, v in keys.items() if k != "CLOUDFLARE_ACCOUNT_ID"]


# ---------------------------------------------------------------- the price table

def load_table(path=None):
    with open(path or PRICES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def model_spec(table, provider, model):
    """The table entry for a model, with shared inputs and prices filled in. None if absent."""
    prov = table["providers"].get(provider)
    if not prov or model not in prov["models"]:
        return None
    spec = dict(prov["models"][model])
    shared = prov.get("shared", {})
    for part in ("inputs", "price"):
        if isinstance(spec.get(part), str):
            spec[part] = shared[spec[part]][part]
    spec.setdefault("kind", prov["kind"])
    spec.setdefault("source", prov["source"])
    spec.setdefault("checked", prov["checked"])
    return spec


def resolve(table, model, provider=None):
    """Work out which provider a model belongs to. Returns (provider, spec or None)."""
    if provider:
        if provider not in PROVIDERS:
            raise ToolError("Unknown provider %r. Use one of: %s." % (provider, ", ".join(ORDER)), EXIT_SETUP)
        if provider == "replicate":
            rr.split_model(model)
        return provider, model_spec(table, provider, model)
    hits = [p for p in table["providers"] if model in table["providers"][p]["models"]]
    if len(hits) == 1:
        return hits[0], model_spec(table, hits[0], model)
    if re.match(r"^[\w.-]+/[\w.-]+(:[0-9a-f]{64})?$", model):
        return "replicate", None
    raise ToolError("Cannot tell which provider runs %r. Pass --provider (%s), or list models with: "
                    "generate.py models" % (model, ", ".join(ORDER)), EXIT_SETUP)


def stale_warning(spec, table):
    try:
        checked = _dt.date.fromisoformat(spec["checked"])
    except (KeyError, ValueError):
        return "The price table has no checked date for this model. Read the price on %s first." % spec.get("source")
    age = (_dt.date.today() - checked).days
    if age > table.get("stale_after_days", 60):
        return ("These prices were checked %s, %d days ago. Read the current price on %s and update prices.json "
                "before spending." % (spec["checked"], age, spec["source"]))
    return None


# ---------------------------------------------------------------- inputs

def apply_defaults(spec, data):
    notes = []
    for key, rule in (spec.get("inputs") or {}).items():
        if key in data and rule.get("type") == "string" and not isinstance(data[key], str):
            data[key] = json.dumps(data[key]) if isinstance(data[key], bool) else str(data[key])  # -i prompt=123
        if key not in data and rule.get("send_default"):
            data[key] = rule["default"]
            notes.append("%s=%s" % (key, json.dumps(rule["default"]) if not isinstance(rule["default"], str) else rule["default"]))
    return data, notes


def validate(spec, data):
    rules = spec.get("inputs")
    if not rules:
        return []
    problems = []
    for key, rule in rules.items():
        if rule.get("required") and key not in data:
            problems.append("missing required input '%s'" % key)
    for key, value in data.items():
        if key not in rules:
            problems.append("unknown input '%s' (this model takes: %s)" % (key, ", ".join(sorted(rules))))
            continue
        rule = rules[key]
        kind = rule.get("type")
        if kind == "file":
            if not (isinstance(value, str) and value.startswith("@")):
                problems.append("'%s' must be a local file, written as @path/to/file" % key)
            continue
        if kind == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            problems.append("'%s' must be a whole number" % key)
            continue
        if kind == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            problems.append("'%s' must be a number" % key)
            continue
        if kind == "boolean" and not isinstance(value, bool):
            problems.append("'%s' must be true or false" % key)
            continue
        if kind == "string" and not isinstance(value, str):
            value = str(value)
        if "enum" in rule and value not in rule["enum"]:
            problems.append("'%s' must be one of %s" % (key, rule["enum"]))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "min" in rule and value < rule["min"]:
                problems.append("'%s' is below the minimum %s" % (key, rule["min"]))
            if "max" in rule and value > rule["max"]:
                problems.append("'%s' is above the maximum %s" % (key, rule["max"]))
        if isinstance(value, str):
            if "max_length" in rule and len(value) > rule["max_length"]:
                problems.append("'%s' is longer than %d characters" % (key, rule["max_length"]))
            if "pattern" in rule and not re.match(rule["pattern"], value):
                problems.append("'%s' has the wrong format (%s)" % (key, rule["pattern"]))
    return problems


def read_files(data):
    """Turn "@path" values into (bytes, content type, file name). Done before any charge."""
    files = {}
    for key, value in data.items():
        if isinstance(value, str) and value.startswith("@"):
            path = os.path.expanduser(value[1:])
            if not os.path.isfile(path):
                raise ToolError("Input '%s' points to %s, which is not a file." % (key, path), EXIT_SETUP)
            with open(path, "rb") as fh:
                content = fh.read()
            files[key] = (content, mimetypes.guess_type(path)[0] or "application/octet-stream", os.path.basename(path))
    return files


def data_uri(content, ctype):
    return "data:%s;base64,%s" % (ctype, base64.b64encode(content).decode())


# ---------------------------------------------------------------- estimates

def _key(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def tiles(width, height):
    return math.ceil(width / 512.0) * math.ceil(height / 512.0)


def estimate(spec, data):
    """Return (cost or None, explanation lines). Uses only the dated table."""
    price = spec.get("price") or {}
    method = price.get("method")
    margin = float(price.get("margin", 1.0))
    lines = []
    if method == "per_image":
        count = data.get(price.get("count_key", "n"), 1)
        choice = "|".join(_key(data.get(k)) for k in price["by"])
        unit = price["table"].get(choice)
        if unit is None:
            return None, ["No table price for %s = %s. Priced sizes and qualities: %s."
                          % (" and ".join(price["by"]), choice.replace("|", ", "),
                             "; ".join(sorted(k.replace("|", " ") for k in price["table"])))]
        text = len(str(data.get("prompt", ""))) / 3.0 * price.get("text_per_million", 0) / 1e6
        cost = unit * count * margin + text
        lines.append("Price: $%.5f per image at %s (table, checked %s)" % (unit, choice.replace("|", " "), spec["checked"]))
        lines.append("This run: %d image(s) x $%.5f%s + prompt text $%.5f = $%.4f" % (
            count, unit, " x %.2f margin" % margin if margin != 1.0 else "", text, cost))
        return cost, lines
    if method == "tiles":
        width, height = (data.get("width"), data.get("height"))
        if not (width and height):
            width, height = price.get("assume_size", [None, None])
        if not (width and height):
            return None, ["Set width and height so the estimate is real."]
        steps = data.get(price.get("steps_key", ""), 1) if price.get("steps_key") else 1
        out_tiles = tiles(width, height)
        n_inputs = sum(1 for k, v in data.items() if k.startswith("input_image_") and v)
        per_out = price.get("per_output_tile", 0) + price.get("per_output_tile_step", 0) * steps
        per_in = (price.get("per_input_tile", 0) + price.get("per_input_tile_step", 0) * steps) * price.get("input_tiles_each", 0)
        cost = (out_tiles * per_out + n_inputs * per_in) * margin
        lines.append("Price: %d output tile(s) of 512x512 for %dx%d%s (table, checked %s)" % (
            out_tiles, width, height, ", %d steps" % steps if price.get("steps_key") else "", spec["checked"]))
        lines.append("This run: %d x $%.6f%s = $%.4f" % (
            out_tiles, per_out, " + %d input image(s) x $%.6f" % (n_inputs, per_in) if n_inputs else "", cost))
        return cost, lines
    if method == "per_second":
        seconds = data.get(price.get("seconds_key")) if price.get("seconds_key") else None
        assumed = False
        if seconds is None:
            seconds = price.get("assume_seconds")
            assumed = True
        if seconds is None:
            return None, ["Set %s so the estimate is real." % price.get("seconds_key")]
        if price.get("rate_key"):
            choice = _key(data.get(price["rate_key"]))
            rate = price["rates"].get(choice)
            if rate is None:
                return None, ["No table price for %s=%s. Priced: %s." % (price["rate_key"], choice, ", ".join(price["rates"]))]
            label = "%s=%s" % (price["rate_key"], choice)
        else:
            rate, label = price["rate"], "per second"
        cost = rate * seconds * margin
        lines.append("Price: $%.5f per second, %s (table, checked %s)" % (rate, label, spec["checked"]))
        lines.append("This run: %g s%s x $%.5f%s = $%.4f" % (
            seconds, " (assumed: the longest clip this model makes)" if assumed else "", rate,
            " x %.2f margin" % margin if margin != 1.0 else "", cost))
        return cost, lines
    return None, ["The table has no price rule for this model."]


# ---------------------------------------------------------------- HTTP with the shared rules

def send(provider, method, url, headers, body=None, timeout=60, create=False, secrets=()):
    """One request with the retry rules. Returns (status, headers, raw)."""
    for attempt in range(4):
        try:
            status, hdrs, raw = rr.http(method, url, headers, body, timeout=timeout)
        except (urllib.error.URLError, OSError) as exc:
            if create:
                raise MaybeStarted(
                    "%s while creating the run (%s). It may have started and been billed, so the tool will not "
                    "retry. Check the provider's dashboard before running again."
                    % ("No answer in time" if is_timeout(exc) else "The connection dropped", scrub(exc, secrets)),
                    EXIT_TIMEOUT if is_timeout(exc) else EXIT_API)
            if attempt < 3:
                sleep(2 * (attempt + 1))
                continue
            raise ToolError("Network problem: %s" % scrub(exc, secrets), EXIT_API)
        if status == 429:
            code, msg = err_info(raw)
            if code in NO_RETRY_429.get(provider, set()):
                raise ToolError("%s says the account is out of credit or quota (429 %s): %s. Waiting will not fix "
                                "this. Add credit or raise the limit in the provider's dashboard."
                                % (provider, code, scrub(msg, secrets)), EXIT_API)
            if attempt < 3:
                wait = rr.retry_after_seconds(hdrs, raw, default=5.0 * (2 ** attempt))
                if wait > MAX_WAIT:
                    raise ToolError("%s is rate limiting this account and asks to wait %ds. Nothing was created. "
                                    "Try again later." % (provider, wait), EXIT_API)
                out("Rate limited by %s (429). Nothing was created. Waiting %ds before trying again." % (provider, wait))
                sleep(wait)
                continue
            raise ToolError("Still rate limited by %s after 3 waits. Nothing was created. Try again in a few minutes."
                            % provider, EXIT_API)
        if status >= 500:
            load_shed = provider == "runway" and status in (502, 503)  # Runway: shedding load, safe to retry
            if create and not load_shed:
                raise MaybeStarted("%s had a server error (%s) while creating the run. It may have started anyway, "
                                   "so the tool will not retry. Check the provider's dashboard first." % (provider, status))
            if attempt < 3:
                sleep(5 * (attempt + 1))
                continue
        return status, hdrs, raw
    raise ToolError("Gave up after repeated server errors from %s." % provider, EXIT_API)


def explain(provider, status, raw, secrets):
    code, msg = err_info(raw)
    msg = scrub(msg, secrets)
    if status == 401:
        return "%s says the key is not valid (401). Make a new one and set it in your shell." % provider
    if status == 402:
        return "%s says there is not enough credit (402): %s" % (provider, msg)
    if status == 403:
        return "%s refused access (403%s): %s" % (provider, " " + code if code else "", msg)
    if status == 404:
        return "%s cannot find that model or resource (404): %s" % (provider, msg)
    return "%s returned %s%s: %s" % (provider, status, " (%s)" % code if code else "", msg)


def cancel_quietly(provider, method, url, headers, secrets):
    """Ask the provider to stop a run. A failed cancel must not look like 'never created'."""
    try:
        status, _, raw = send(provider, method, url, headers, secrets=secrets)
        if status >= 300:
            out("The cancel call returned %s. Check the provider's dashboard that the run stopped." % status)
    except (ToolError, urllib.error.URLError, OSError) as exc:
        out("Could not cancel (%s). Check the provider's dashboard that the run stopped." % scrub(exc, secrets))


def poll_delays(start=5.0, cap=20.0):
    delay = start
    while True:
        yield delay
        delay = min(delay * 1.5, cap)


# ---------------------------------------------------------------- providers: one run each

def multipart_form(fields, files):
    boundary = "----aya" + uuid.uuid4().hex
    parts = []
    for key, value in fields.items():
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (boundary, key, value if isinstance(value, str) else json.dumps(value))).encode())
    for key, (content, ctype, name) in files.items():
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                      % (boundary, key, name, ctype)).encode())
        parts.append(content)
        parts.append(b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def run_cloudflare(keys, model, spec, data, files, args):
    secrets = secret_values(keys)
    url = "%s/accounts/%s/ai/run/%s" % (CF_API, keys["CLOUDFLARE_ACCOUNT_ID"], model)
    headers = {"Authorization": "Bearer " + keys["CLOUDFLARE_API_TOKEN"], "User-Agent": rr.USER_AGENT}
    fields = {k: v for k, v in data.items() if k not in files}
    if (spec or {}).get("body") == "multipart":
        body, headers["Content-Type"] = multipart_form(fields, files)
    else:
        if files:
            raise ToolError("This model takes JSON only, so it cannot take a file input.", EXIT_SETUP)
        body, headers["Content-Type"] = json.dumps(fields).encode(), "application/json"
    status, hdrs, raw = send("cloudflare", "POST", url, headers, body, timeout=args.timeout, create=True, secrets=secrets)
    if status == 200 and (hdrs.get("content-type") or "").startswith("image/"):
        return {"status": "succeeded", "outputs": [raw]}
    payload = parse_json(raw) or {}
    image = (payload.get("result") or {}).get("image") if isinstance(payload.get("result"), dict) else None
    if status == 200 and image:
        return {"status": "succeeded", "outputs": [base64.b64decode(image)]}
    if status == 408:
        return {"status": "timed_out", "error": explain("cloudflare", status, raw, secrets)}
    if status == 200:
        return {"status": "failed", "error": "Cloudflare answered without an image: %s" % scrub(err_info(raw)[1], secrets)}
    raise ToolError(explain("cloudflare", status, raw, secrets))


def run_openai(keys, model, spec, data, files, args):
    secrets = secret_values(keys)
    if files:
        raise ToolError("The OpenAI generations call takes no file input. Edits are not wired into this tool.", EXIT_SETUP)
    body = dict(data)
    body["model"] = model
    headers = {"Authorization": "Bearer " + keys["OPENAI_API_KEY"], "User-Agent": rr.USER_AGENT,
               "Content-Type": "application/json"}
    status, hdrs, raw = send("openai", "POST", OPENAI_API + "/images/generations", headers, json.dumps(body).encode(),
                             timeout=args.timeout, create=True, secrets=secrets)
    payload = parse_json(raw) or {}
    if status == 200:
        images = [base64.b64decode(item["b64_json"]) for item in payload.get("data") or [] if item.get("b64_json")]
        if images:
            return {"status": "succeeded", "outputs": images, "id": hdrs.get("x-request-id")}
        return {"status": "failed", "error": "OpenAI answered without an image."}
    err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    if err.get("code") == "moderation_blocked" or err.get("type") == "image_generation_user_error":
        stage = (err.get("moderation_details") or {}).get("moderation_stage", "")
        return {"status": "refused", "error": "OpenAI's safety system blocked this (%s%s): %s" % (
            err.get("code") or err.get("type"), ", stage: " + stage if stage else "", scrub(err.get("message", ""), secrets))}
    raise ToolError(explain("openai", status, raw, secrets))


def run_runway(keys, model, spec, data, files, args):
    secrets = secret_values(keys)
    headers = {"Authorization": "Bearer " + keys["RUNWAYML_API_SECRET"], "User-Agent": rr.USER_AGENT,
               "Content-Type": "application/json", "X-Runway-Version": RUNWAY_VERSION}
    body = {k: v for k, v in data.items() if k != "prompt"}
    if "prompt" in data:
        body["promptText"] = data["prompt"]
    for key, (content, ctype, name) in files.items():
        if len(content) > RUNWAY_DATA_URI_MAX:
            raise ToolError("%s is %d bytes. Runway takes images up to about 3.3 MB inline. Make it smaller first."
                            % (name, len(content)), EXIT_SETUP)
        body[key] = data_uri(content, ctype)
    body["model"] = model
    endpoint = "image_to_video" if "promptImage" in body else "text_to_video"
    allowed = (spec or {}).get("endpoints")
    if allowed and endpoint not in allowed:
        raise ToolError("%s cannot do %s. It supports: %s." % (model, endpoint.replace("_", " "), ", ".join(allowed)),
                        EXIT_SETUP)
    status, hdrs, raw = send("runway", "POST", "%s/v1/%s" % (RUNWAY_API, endpoint), headers, json.dumps(body).encode(),
                             timeout=60, create=True, secrets=secrets)
    if status not in (200, 201):
        raise ToolError(explain("runway", status, raw, secrets))
    task_id = (parse_json(raw) or {}).get("id")
    if not task_id:
        raise MaybeStarted("Runway accepted the request but sent no task id. Check https://dev.runway.com before retrying.")
    out("Started Runway task %s." % task_id)
    started, throttled_said = time.time(), False
    task = {"status": "PENDING"}
    delays = poll_delays()
    while task.get("status") in ("PENDING", "THROTTLED", "RUNNING"):
        if time.time() - started > args.timeout:
            out("No result after %ds. Canceling so it stops." % args.timeout)
            cancel_quietly("runway", "DELETE", "%s/v1/tasks/%s" % (RUNWAY_API, task_id), headers, secrets)
            return {"status": "timed_out", "id": task_id}
        sleep(next(delays))
        try:
            s, _, r = send("runway", "GET", "%s/v1/tasks/%s" % (RUNWAY_API, task_id), headers, secrets=secrets)
        except ToolError as exc:
            out("Could not check the task (%s). Trying again." % exc)
            continue
        if s == 200:
            task = parse_json(r) or task
        if task.get("status") == "THROTTLED" and not throttled_said:
            out("Queued behind your Runway concurrency limit (THROTTLED). That is not an error; it starts on its own.")
            throttled_said = True
    actual = None
    if isinstance(task.get("cost"), dict) and isinstance(task["cost"].get("credits"), (int, float)):
        actual = task["cost"]["credits"] * 0.01
    result = {"id": task_id, "actual": actual}
    if task.get("status") == "SUCCEEDED":
        result.update(status="succeeded", urls=list(task.get("output") or []))
    elif task.get("status") == "CANCELLED":
        result.update(status="canceled")
    else:
        code = task.get("failureCode") or ""
        refused = code.startswith("SAFETY") or "SAFETY" in code
        result.update(status="refused" if refused else "failed",
                      error="%s%s" % (task.get("failure") or "no reason given", " (%s)" % code if code else ""))
    return result


def google_video(payload):
    for step in payload.get("steps") or []:
        if step.get("type") != "model_output":
            continue
        for part in step.get("content") or []:
            if part.get("type") == "video":
                return part
    return None


def run_google(keys, model, spec, data, files, args):
    secrets = secret_values(keys)
    headers = {"x-goog-api-key": keys["key"], "User-Agent": rr.USER_AGENT, "Content-Type": "application/json"}
    prompt = data.get("prompt", "")
    if files:
        parts = [{"type": "image", "data": base64.b64encode(c).decode(), "mime_type": t} for c, t, _ in files.values()]
        user_input = parts + [{"type": "text", "text": prompt}]
    else:
        user_input = prompt
    fmt = {"type": "video"}
    for key in ("aspect_ratio", "resolution"):
        if key in data:
            fmt[key] = data[key]
    body = {"model": model, "input": user_input, "response_format": fmt, "background": True}
    status, hdrs, raw = send("google", "POST", GEMINI_API + "/interactions", headers, json.dumps(body).encode(),
                             timeout=120, create=True, secrets=secrets)
    if status != 200:
        code, msg = err_info(raw)
        if code in GOOGLE_BLOCKED:
            return {"status": "refused", "error": "Google blocked the request (%s): %s" % (code, scrub(msg, secrets))}
        raise ToolError(explain("google", status, raw, secrets))
    inter = parse_json(raw) or {}
    inter_id = inter.get("id")
    if not inter_id:
        raise MaybeStarted("Google accepted the request but sent no interaction id. Check your usage in AI Studio before retrying.")
    out("Started Gemini interaction %s." % inter_id)
    started = time.time()
    delays = poll_delays()
    while inter.get("status") in (None, "in_progress"):
        if time.time() - started > args.timeout:
            out("No result after %ds. Canceling so it stops." % args.timeout)
            cancel_quietly("google", "POST", "%s/interactions/%s/cancel" % (GEMINI_API, inter_id), headers, secrets)
            return {"status": "timed_out", "id": inter_id}
        sleep(next(delays))
        try:
            s, _, r = send("google", "GET", "%s/interactions/%s" % (GEMINI_API, inter_id), headers, timeout=300,
                           secrets=secrets)
        except ToolError as exc:
            out("Could not check the interaction (%s). Trying again." % exc)
            continue
        if s == 200:
            inter = parse_json(r) or inter
    actual = None
    usage = inter.get("usage") or {}
    if usage.get("total_output_tokens") is not None:
        out_tokens = usage.get("total_output_tokens", 0) + usage.get("total_thought_tokens", 0)
        actual = out_tokens * 17.5 / 1e6 + usage.get("total_input_tokens", 0) * 1.5 / 1e6  # upper bound: thoughts at the video rate
    result = {"id": inter_id, "actual": actual}
    state = inter.get("status")
    if state == "completed":
        video = google_video(inter)
        if video and video.get("data"):
            result.update(status="succeeded", outputs=[base64.b64decode(video["data"])])
        elif video and video.get("uri"):
            result.update(status="succeeded", urls=[video["uri"]], url_headers={"x-goog-api-key": keys["key"]})
        else:
            result.update(status="failed", error="The interaction finished without a video.")
    elif state == "cancelled":
        result.update(status="canceled")
    else:
        err = inter.get("error") if isinstance(inter.get("error"), dict) else {}
        code = str(err.get("code", ""))
        result.update(status="refused" if code in GOOGLE_BLOCKED else "failed",
                      error="%s%s" % (scrub(err.get("message") or "status " + str(state), secrets),
                                      " (%s)" % code if code else ""))
    return result


RUNNERS = {"cloudflare": run_cloudflare, "openai": run_openai, "runway": run_runway, "google": run_google}


# ---------------------------------------------------------------- saving outputs

def ext_for_bytes(content):
    if content.startswith(b"\x89PNG"):
        return ".png"
    if content.startswith(b"\xff\xd8"):
        return ".jpg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    if content[4:8] == b"ftyp":
        return ".mp4"
    if content[:3] == b"GIF":
        return ".gif"
    return ".bin"


def save_outputs(result, out_dir, stem):
    os.makedirs(out_dir, exist_ok=True)
    saved, failed = [], []
    n = 0
    for content in result.get("outputs") or []:
        n += 1
        path = os.path.join(out_dir, "%s-%d%s" % (stem, n, ext_for_bytes(content)))
        with open(path, "wb") as fh:
            fh.write(content)
        saved.append(path)
    for url in result.get("urls") or []:
        n += 1
        headers = {"User-Agent": rr.USER_AGENT}
        if result.get("url_headers") and urllib.parse.urlparse(url).netloc == "generativelanguage.googleapis.com":
            headers.update(result["url_headers"])  # the key only ever goes back to Google's own host
        for attempt in range(3):
            try:
                status, hdrs, raw = rr.http("GET", url, headers, timeout=300)
            except (urllib.error.URLError, OSError):
                status, hdrs, raw = 0, {}, b""
            if status == 200 and raw:
                ext = ext_for_bytes(raw)
                if ext == ".bin":
                    ext = rr.ext_for(url, hdrs.get("content-type"))
                path = os.path.join(out_dir, "%s-%d%s" % (stem, n, ext))
                with open(path, "wb") as fh:
                    fh.write(raw)
                saved.append(path)
                break
            sleep(2 * (attempt + 1))
        else:
            failed.append(url)
    return saved, failed


# ---------------------------------------------------------------- commands

def rr_args(args, **extra):
    base = {"model": args.model, "input": getattr(args, "input", None), "input_file": getattr(args, "input_file", None),
            "set": getattr(args, "set", None)}
    base.update(extra)
    return argparse.Namespace(**base)


def cmd_run(args):
    table = load_table()
    provider, spec = resolve(table, args.model, args.provider)
    if provider == "replicate":
        return rr.cmd_run(rr_args(args, yes=args.yes, assume_cost=args.assume_cost, max_cost=args.max_cost,
                                  out=args.out, label=args.label, timeout=args.timeout, deadline=args.deadline))
    data = rr.load_input(args)
    out("Provider: %s. Model: %s." % (provider, args.model))
    if spec is None:
        if args.assume_cost is None:
            prov = table["providers"].get(provider, {})
            raise ToolError("%s is not in the price table, so there is no estimate and nothing was run. Read its price on "
                            "%s, tell the user, and if they agree rerun with --assume-cost <dollars>."
                            % (args.model, prov.get("source", "the provider's pricing page")), EXIT_SETUP)
        spec = {"inputs": None, "kind": PROVIDERS[provider]["kinds"][0]}
        out("This model is not in the price table, so its inputs are not checked here.")
    data, notes = apply_defaults(spec, data)
    if notes:
        out("Sending these settings so the price is known: %s" % ", ".join(notes))
    problems = validate(spec, data)
    if problems:
        raise ToolError("Input problems, nothing was run:\n  - " + "\n  - ".join(problems), EXIT_SETUP)
    if args.assume_cost is not None:
        cost, lines = args.assume_cost, ["Using the cost you gave: $%.4f (not from the table)." % args.assume_cost]
    else:
        cost, lines = estimate(spec, data)
        warning = stale_warning(spec, table)
        if warning:
            lines.append(warning)
    for line in lines:
        out(line)
    if cost is None:
        raise ToolError("No estimate, so nothing was run. Read the price on %s, tell the user, and if they agree "
                        "rerun with --assume-cost <dollars>." % spec.get("source", "the provider's pricing page"), EXIT_SETUP)
    if args.max_cost is not None and cost > args.max_cost:
        raise ToolError("Estimate $%.4f is over --max-cost $%.4f. Nothing was run." % (cost, args.max_cost), EXIT_CAP)
    ledger = rr.load_ledger()
    out("Session: $%.4f spent of a $%.2f cap (all providers). $%.4f left."
        % (rr.spent(ledger), ledger["cap"], ledger["cap"] - rr.spent(ledger)))
    if not args.yes:
        out("Key for %s: %s." % (provider, "set" if has_key(provider) else "NOT set (run: generate.py check --provider %s)" % provider))
        out("DRY RUN. Nothing was spent. Show the user the estimate, and rerun with --yes only after they say yes.")
        return EXIT_OK
    keys = get_keys(provider)
    files = read_files(data)  # free, done first so a bad path never leaves a reserved charge
    entry = rr.reserve("%s:%s" % (provider, args.model), cost, args.label or "")
    try:
        result = RUNNERS[provider](keys, args.model, spec, data, files, args)
    except MaybeStarted:
        rr.settle(entry, "unknown")  # keep the charge reserved: it might be real
        raise
    except ToolError:
        rr.settle(entry, "not-created", cost=0.0)
        raise
    except (urllib.error.URLError, OSError):
        rr.settle(entry, "unknown")
        raise
    status = result.get("status")
    run_id = result.get("id") or uuid.uuid4().hex[:8]
    stem = "%s-%s" % (rr.slugify(args.label or data.get("prompt", "")), re.sub(r"[^A-Za-z0-9]", "", str(run_id))[-8:] or "run")
    actual = result.get("actual")
    code, saved = EXIT_OK, []
    if status == "succeeded":
        rr.settle(entry, "succeeded", run_id, cost=actual)
        saved, failed = save_outputs(result, args.out, stem)
        for path in saved:
            out("Saved %s" % path)
        if failed:
            out("Could not download %d file(s). Fetch them soon, the links expire:\n  %s" % (len(failed), "\n  ".join(failed)))
            code = EXIT_DOWNLOAD
    elif status == "refused":
        rr.settle(entry, "refused", run_id, cost=actual)
        out("Refused by %s's content rules: %s" % (provider, result.get("error")))
        out("The estimate stays on the ledger, since some providers bill refused runs. Do not retry the same input. "
            "Tell the user, change the prompt or image, and ask before trying again.")
        code = EXIT_FAILED
    elif status == "failed":
        rr.settle(entry, "failed", run_id, cost=actual)
        out("The run failed: %s" % (result.get("error") or "no error text"))
        out("The charge stays on the ledger to be safe. Tell the user before any retry, and never rerun the same input unchanged.")
        code = EXIT_FAILED
    else:
        rr.settle(entry, status or "unknown", run_id, cost=actual)
        out("Run %s. %s" % (status, result.get("error") or "You may be billed for it, so the estimate stays on the ledger."))
        code = EXIT_TIMEOUT
    os.makedirs(args.out, exist_ok=True)
    record = {"provider": provider, "model": args.model, "id": run_id, "status": status, "error": result.get("error"),
              "estimate_usd": round(cost, 6), "actual_usd": None if actual is None else round(actual, 6),
              "input": {k: ("<file>" if isinstance(v, str) and v.startswith("@") else v) for k, v in data.items()},
              "files": saved, "created_at": rr.now().isoformat()}
    sidecar = os.path.join(args.out, stem + ".json")
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    out("Run record: %s" % sidecar)
    ledger = rr.load_ledger()
    out("Session spend: $%.4f of the $%.2f cap. $%.4f left." % (rr.spent(ledger), ledger["cap"], ledger["cap"] - rr.spent(ledger)))
    return code


def cmd_price(args):
    table = load_table()
    provider, spec = resolve(table, args.model, args.provider)
    if provider == "replicate":
        return rr.cmd_price(rr_args(args))
    if spec is None:
        out("%s is not in the price table. Read its price on %s." % (args.model, table["providers"][provider]["source"]))
        out("Estimate for one run: unknown")
        return EXIT_OK
    data, notes = apply_defaults(spec, rr.load_input(args))
    out("%s on %s: %s" % (spec.get("label", args.model), provider, spec.get("summary", "")))
    if notes:
        out("Priced with: %s" % ", ".join(notes))
    cost, lines = estimate(spec, data)
    for line in lines:
        out(line)
    if spec.get("price", {}).get("why"):
        out("How: %s" % spec["price"]["why"])
    warning = stale_warning(spec, table)
    if warning:
        out(warning)
    out("Estimate for one run: %s" % ("$%.4f" % cost if cost is not None else "unknown"))
    out("Source: %s (checked %s)" % (spec["source"], spec["checked"]))
    return EXIT_OK


def cmd_schema(args):
    table = load_table()
    provider, spec = resolve(table, args.model, args.provider)
    if provider == "replicate":
        return rr.cmd_schema(rr_args(args))
    if spec is None:
        raise ToolError("%s is not in the table, so the tool does not know its inputs. See %s."
                        % (args.model, table["providers"][provider]["source"]), EXIT_SETUP)
    out("%s | provider: %s | %s | docs: %s" % (args.model, provider, spec["kind"], spec.get("docs", spec["source"])))
    for key, rule in spec["inputs"].items():
        bits = [rule.get("type", "any")]
        if rule.get("type") == "file":
            bits.append("pass as @path")
        if rule.get("required"):
            bits.append("REQUIRED")
        if "default" in rule:
            bits.append("default=%s%s" % (json.dumps(rule["default"]), ", always sent" if rule.get("send_default") else ""))
        if "enum" in rule:
            bits.append("one of %s" % rule["enum"])
        if "min" in rule or "max" in rule:
            bits.append("range %s..%s" % (rule.get("min", ""), rule.get("max", "")))
        if "max_length" in rule:
            bits.append("max %d chars" % rule["max_length"])
        out("- %s (%s)" % (key, ", ".join(bits)))
    if spec.get("endpoints"):
        out("Endpoints: %s (a promptImage makes it image to video)" % ", ".join(spec["endpoints"]))
    return EXIT_OK


def default_for(kind, config):
    ready = [p for p in ORDER if kind in PROVIDERS[p]["kinds"] and has_key(p)]
    if config.get("order"):
        for p in config["order"]:
            if p in ready:
                return p, "first in your saved order with a key"
    if len(ready) == 1:
        return ready[0], "the only provider with a key for %s" % kind
    if ready:
        return None, "ask the user: keys are set for %s, and no order is saved" % ", ".join(ready)
    return None, "no provider key is set for %s" % kind


def cmd_providers(args):
    if args.order:
        order = [p.strip() for p in args.order.split(",") if p.strip()]
        bad = [p for p in order if p not in PROVIDERS]
        if bad:
            raise ToolError("Unknown provider(s): %s. Use: %s." % (", ".join(bad), ", ".join(ORDER)), EXIT_SETUP)
        save_config(order)
        out("Saved your order: %s (%s)" % (", ".join(order), config_path()))
    config = load_config()
    for p in ORDER:
        info = PROVIDERS[p]
        out("- %s: key %s | makes %s | env %s" % (p, "set" if has_key(p) else "not set", " and ".join(info["kinds"]),
                                                    " + ".join(info["env"])))
    out("Saved order: %s" % (", ".join(config["order"]) if config.get("order") else "none (save one with --order a,b,c)"))
    for kind in ("image", "video"):
        pick, why = default_for(kind, config)
        out("Default for %s: %s (%s)" % (kind, pick or "none", why))
    return EXIT_OK


def check_one(provider):
    keys = get_keys(provider)
    secrets = secret_values(keys)
    if provider == "replicate":
        return rr.cmd_check(None)
    if provider == "cloudflare":
        url = "%s/accounts/%s/ai/models/search?%s" % (CF_API, keys["CLOUDFLARE_ACCOUNT_ID"],
                                                      urllib.parse.urlencode({"task": "Text-to-Image", "per_page": 50}))
        s, _, raw = send(provider, "GET", url, {"Authorization": "Bearer " + keys["CLOUDFLARE_API_TOKEN"],
                                                "User-Agent": rr.USER_AGENT}, secrets=secrets)
        if s != 200:
            raise ToolError(explain(provider, s, raw, secrets) + " The token needs Workers AI Read and Edit, and the "
                            "account ID must match it.")
        names = [m.get("name") for m in (parse_json(raw) or {}).get("result") or [] if isinstance(m, dict)]
        out("cloudflare: key works (free call). %d text to image models visible: %s" % (len(names), ", ".join(names[:8])))
    elif provider == "openai":
        s, _, raw = send(provider, "GET", OPENAI_API + "/models", {"Authorization": "Bearer " + keys["OPENAI_API_KEY"],
                                                                  "User-Agent": rr.USER_AGENT}, secrets=secrets)
        if s != 200:
            raise ToolError(explain(provider, s, raw, secrets))
        ids = sorted(m.get("id", "") for m in (parse_json(raw) or {}).get("data") or [] if "image" in m.get("id", ""))
        out("openai: key works (free call). Image models on this key: %s" % (", ".join(ids) or "none listed"))
        out("  A working key does not prove there is credit. OpenAI has no free credit check in the API.")
    elif provider == "runway":
        s, _, raw = send(provider, "GET", RUNWAY_API + "/v1/organization",
                         {"Authorization": "Bearer " + keys["RUNWAYML_API_SECRET"], "User-Agent": rr.USER_AGENT,
                          "X-Runway-Version": RUNWAY_VERSION}, secrets=secrets)
        if s != 200:
            raise ToolError(explain(provider, s, raw, secrets))
        data = parse_json(raw) or {}
        credits = data.get("creditBalance", 0)
        out("runway: key works (free call). Credit balance: %s credits ($%.2f)." % (credits, credits * 0.01))
    elif provider == "google":
        s, _, raw = send(provider, "GET", GEMINI_API + "/models?pageSize=1000",
                         {"x-goog-api-key": keys["key"], "User-Agent": rr.USER_AGENT}, secrets=secrets)
        if s != 200:
            raise ToolError(explain(provider, s, raw, secrets))
        names = [m.get("name", "") for m in (parse_json(raw) or {}).get("models") or []]
        video = [n.split("/", 1)[-1] for n in names if "omni" in n or "veo" in n]
        out("google: key works (free call). Video models listed: %s" % (", ".join(video) or "none"))
        out("  There is no free check for the paid tier. Omni Flash only runs on a paid tier project.")
    return EXIT_OK


def cmd_check(args):
    targets = [args.provider] if args.provider else [p for p in ORDER if has_key(p)]
    if not targets:
        lines = ["No provider key is set. Pick the account you already have and set its key:"]
        for p in ORDER:
            lines.append("\n%s (%s):\n%s" % (p, " and ".join(PROVIDERS[p]["kinds"]), PROVIDERS[p]["help"]))
        lines.append("\n" + KEY_RULE)
        raise ToolError("\n".join(lines), EXIT_SETUP)
    code = EXIT_OK
    for p in targets:
        if p not in PROVIDERS:
            raise ToolError("Unknown provider %r." % p, EXIT_SETUP)
        try:
            check_one(p)
        except ToolError as exc:
            out("%s: %s" % (p, exc))
            code = exc.code
    return code


def live_models(provider, kind, query):
    """Names the provider lists right now (free calls). None when it has no listing we can use."""
    keys = get_keys(provider)
    secrets = secret_values(keys)
    if provider == "cloudflare":
        url = "%s/accounts/%s/ai/models/search?%s" % (CF_API, keys["CLOUDFLARE_ACCOUNT_ID"],
                                                      urllib.parse.urlencode({"task": "Text-to-Image", "per_page": 100}))
        s, _, raw = send(provider, "GET", url, {"Authorization": "Bearer " + keys["CLOUDFLARE_API_TOKEN"],
                                                "User-Agent": rr.USER_AGENT}, secrets=secrets)
        if s == 200:
            return [m.get("name") for m in (parse_json(raw) or {}).get("result") or [] if isinstance(m, dict)]
    elif provider == "openai":
        s, _, raw = send(provider, "GET", OPENAI_API + "/models", {"Authorization": "Bearer " + keys["OPENAI_API_KEY"],
                                                                  "User-Agent": rr.USER_AGENT}, secrets=secrets)
        if s == 200:
            return [m.get("id") for m in (parse_json(raw) or {}).get("data") or [] if "image" in m.get("id", "")]
    elif provider == "runway":
        s, _, raw = send(provider, "GET", RUNWAY_API + "/v1/organization",
                         {"Authorization": "Bearer " + keys["RUNWAYML_API_SECRET"], "User-Agent": rr.USER_AGENT,
                          "X-Runway-Version": RUNWAY_VERSION}, secrets=secrets)
        if s == 200:
            return list(((parse_json(raw) or {}).get("tier") or {}).get("models") or {})
    elif provider == "google":
        s, _, raw = send(provider, "GET", GEMINI_API + "/models?pageSize=1000",
                         {"x-goog-api-key": keys["key"], "User-Agent": rr.USER_AGENT}, secrets=secrets)
        if s == 200:
            return [m.get("name", "").split("/", 1)[-1] for m in (parse_json(raw) or {}).get("models") or []
                    if "omni" in m.get("name", "") or "veo" in m.get("name", "")]
    return None


def cmd_models(args):
    table = load_table()
    kind = args.kind
    targets = [args.provider] if args.provider else [p for p in ORDER if not kind or kind in PROVIDERS[p]["kinds"]]
    for provider in targets:
        if provider not in PROVIDERS:
            raise ToolError("Unknown provider %r." % provider, EXIT_SETUP)
        keyed = has_key(provider)
        out("## %s (key %s)" % (provider, "set" if keyed else "not set"))
        if provider == "replicate":
            query = args.query or ("text to video" if kind == "video" else "text to image")
            if keyed:
                try:
                    rr.cmd_search(argparse.Namespace(query=query, limit=args.limit))
                except ToolError as exc:
                    out("  search failed: %s" % exc)
            else:
                out("  Live prices per model: generate.py price owner/model (no key needed). Browse: "
                    "https://replicate.com/search?%s" % urllib.parse.urlencode({"query": query}))
            continue
        prov = table["providers"][provider]
        live = None
        if keyed:
            try:
                live = live_models(provider, kind, args.query)
            except ToolError as exc:
                out("  live list failed: %s" % exc)
        for name in prov["models"]:
            spec = model_spec(table, provider, name)
            if kind and spec["kind"] != kind:
                continue
            if args.query and args.query.lower() not in (name + " " + spec.get("label", "") + " " + spec.get("notes", "")).lower():
                continue
            seen = "" if live is None else (" | listed live: yes" if name in live else " | listed live: NO, check before use")
            out("- %s | %s | %s | %s%s\n    %s\n    price source: %s (checked %s) | docs: %s" % (
                name, spec.get("label", ""), spec["kind"], spec.get("summary", ""), seen, spec.get("notes", ""),
                spec["source"], spec["checked"], spec.get("docs", "")))
        if live:
            extra = [n for n in live if n not in prov["models"]]
            if extra:
                out("  Also listed live but not in the price table (need --assume-cost): %s" % ", ".join(extra[:20]))
        if prov.get("note"):
            out("  Note: %s" % prov["note"])
    return EXIT_OK


def cmd_ledger(args):
    return rr.cmd_ledger(args)


def build_parser():
    p = argparse.ArgumentParser(description="Make AI images and video with your own provider account, with a price "
                                            "check and one spend cap across providers.")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("providers", help="which keys are set and the default provider (free, no network)")
    s.add_argument("--order", help="save your preferred order, e.g. cloudflare,replicate,openai")
    s = sub.add_parser("check", help="check keys with a free call")
    s.add_argument("--provider", choices=ORDER)
    s = sub.add_parser("models", help="list models with prices (free)")
    s.add_argument("--provider", choices=ORDER)
    s.add_argument("--kind", choices=["image", "video"])
    s.add_argument("--query")
    s.add_argument("--limit", type=int, default=10)
    for name in ("schema", "price", "run"):
        s = sub.add_parser(name)
        s.add_argument("model")
        s.add_argument("--provider", choices=ORDER)
        if name == "schema":
            continue
        s.add_argument("--input", help="JSON object of inputs")
        s.add_argument("--input-file", help="JSON file of inputs")
        s.add_argument("-i", "--set", action="append", help="key=value (value read as JSON if it parses)")
        if name == "run":
            s.add_argument("--yes", action="store_true", help="the user said yes to the estimate: spend it")
            s.add_argument("--assume-cost", type=float, help="use this estimate when the table has no price")
            s.add_argument("--max-cost", type=float, help="refuse if this one run is estimated above this")
            s.add_argument("--out", default="media/images", help="folder to save outputs (default media/images)")
            s.add_argument("--label", help="short name for the files")
            s.add_argument("--timeout", type=int, default=600, help="seconds to wait before canceling")
            s.add_argument("--deadline", default="15m", help="Replicate only: auto-cancel after this (Cancel-After)")
    s = sub.add_parser("ledger", help="show or change the session spend (all providers)")
    s.add_argument("--set-cap", type=float, help="new cap in dollars (only when the user asks)")
    s.add_argument("--new-session", action="store_true", help="start a new session (spend back to $0)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    handlers = {"providers": cmd_providers, "check": cmd_check, "models": cmd_models, "schema": cmd_schema,
                "price": cmd_price, "run": cmd_run, "ledger": cmd_ledger}
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
