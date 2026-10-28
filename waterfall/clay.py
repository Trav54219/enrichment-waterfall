"""Small client for Clay's public API (https://api.clay.com/public/v0) and for a table's webhook source.

Behaviour comes from Clay's developer docs: a `clay-api-key` header, 202 means still running, 429
carries Retry-After, error bodies have a `message` and no stable codes, so branch on status.
"""
import json
import time
import urllib.error
import urllib.request

BASE = "https://api.clay.com/public/v0"


class ClayError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status, self.message = status, message


def urllib_transport(method, url, headers, body, timeout=30):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _request(transport, sleep, method, url, headers, payload=None, retries=4):
    body = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(retries + 1):
        status, hdrs, raw = transport(method, url, headers, body)
        if status == 429 and attempt < retries:
            sleep(float({k.lower(): v for k, v in hdrs.items()}.get("retry-after", 2 ** attempt)))
            continue
        if status >= 400 or status == 0:
            try:
                msg = json.loads(raw).get("message", "")
            except Exception:
                msg = raw[:200].decode("utf-8", "replace")
            raise ClayError(status, msg)
        return status, (json.loads(raw) if raw else {})


class ClayClient:
    def __init__(self, api_key, transport=urllib_transport, sleep=time.sleep):
        self.headers = {"clay-api-key": api_key, "Content-Type": "application/json"}
        self.transport, self.sleep = transport, sleep

    def credits(self):
        return _request(self.transport, self.sleep, "GET", f"{BASE}/credits/balance", self.headers)[1]["balance"]

    def run_routine(self, routine_id, items):
        """Start a routine run for 1-100 items. Returns the run id; the run is async (202)."""
        if not 1 <= len(items) <= 100:
            raise ValueError("inline routine runs take 1 to 100 items; use the batch endpoints beyond that")
        status, body = _request(self.transport, self.sleep, "POST",
                                f"{BASE}/routines/{routine_id}/run", self.headers, {"items": items})
        return body.get("routine_run_id")


def push_to_webhook(url, rows, token=None, transport=urllib_transport, sleep=time.sleep, per_second=5):
    """Post each row to a Clay table's webhook source. Paces itself and retries 429.

    A webhook source accepts 50,000 submissions for its lifetime, so count what you send.
    """
    headers = {"Content-Type": "application/json"}
    if token:
        headers["x-clay-webhook-auth"] = token
    sent = 0
    for row in rows:
        _request(transport, sleep, "POST", url, headers, row)
        sent += 1
        sleep(1 / per_second)
    return sent
