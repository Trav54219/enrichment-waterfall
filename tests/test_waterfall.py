import json
import unittest

from waterfall import providers
from waterfall.clay import ClayClient, ClayError, push_to_webhook
from waterfall.engine import Provider, Waterfall

HTML = """<html><head><title>Acme</title>
<meta name="description" content="Acme builds routing software for logistics teams.">
<script src="//js.hs-scripts.com/123.js"></script><script src="https://js.stripe.com/v3"></script></head>
<body><a href="/careers">Careers</a><p>Short.</p></body></html>"""
BARE = "<html><body><nav><p>menu menu menu menu menu menu menu menu menu menu menu menu menu menu menu menu</p></nav>" \
       "<p>We help revenue teams book more meetings with less manual research every single week.</p></body></html>"


class EngineTests(unittest.TestCase):
    def test_stops_at_first_hit_and_charges_only_hits(self):
        calls = []
        wf = Waterfall([
            Provider("a", "email", lambda r, c: calls.append("a"), cost=0.5),   # miss
            Provider("b", "email", lambda r, c: calls.append("b") or "x@y.com", cost=0.2),
            Provider("c", "email", lambda r, c: calls.append("c") or "z@y.com", cost=0.9),
        ])
        row = wf.enrich({"domain": "y.com"})
        self.assertEqual((row["email"], row["email_source"], calls), ("x@y.com", "b", ["a", "b"]))
        self.assertEqual(wf.ledger["a"]["spend"], 0)      # a miss is free
        self.assertEqual(wf.ledger["b"]["spend"], 0.2)
        self.assertEqual(wf.ledger["c"]["tried"], 0)      # never reached

    def test_known_field_is_never_paid_for_again(self):
        wf = Waterfall([Provider("a", "email", lambda r, c: "new@y.com", cost=1)])
        self.assertEqual(wf.enrich({"email": "old@y.com"})["email"], "old@y.com")
        self.assertEqual(wf.ledger["a"]["tried"], 0)

    def test_provider_error_falls_through_and_is_counted(self):
        def boom(r, c): raise RuntimeError("timeout")
        wf = Waterfall([Provider("a", "f", boom), Provider("b", "f", lambda r, c: "ok")])
        self.assertEqual(wf.enrich({})["f"], "ok")
        self.assertEqual(wf.ledger["a"]["errors"], 1)


class ProviderTests(unittest.TestCase):
    def run_wf(self, html):
        calls = []
        def fetch(url): calls.append(url); return html
        wf = Waterfall(providers.build(fetch))
        return wf.enrich({"domain": "acme.com"}), calls

    def test_meta_description_tech_and_careers(self):
        row, calls = self.run_wf(HTML)
        self.assertEqual(row["description_source"], "site_meta")
        self.assertEqual(row["tech_stack"], "HubSpot, Stripe")
        self.assertEqual(row["careers_url"], "https://acme.com/careers")
        self.assertEqual(len(calls), 1)  # one homepage fetch shared by every provider

    def test_falls_back_to_body_paragraph_and_skips_nav(self):
        row, _ = self.run_wf(BARE)
        self.assertEqual(row["description_source"], "site_body")
        self.assertTrue(row["description"].startswith("We help revenue teams"))
        self.assertNotIn("tech_stack", row)  # nothing found stays empty rather than guessed


class EntityTests(unittest.TestCase):
    def test_html_entities_are_decoded(self):
        html = '<meta name="description" content="EDI, sales &amp; item data for retailers">'
        wf = Waterfall(providers.build(lambda url: html))
        self.assertEqual(wf.enrich({"domain": "a.com"})["description"], "EDI, sales & item data for retailers")


class ClayTests(unittest.TestCase):
    def test_credits_sends_key_header(self):
        seen = {}
        def transport(method, url, headers, body):
            seen.update(method=method, url=url, key=headers["clay-api-key"])
            return 200, {}, b'{"balance": 200}'
        self.assertEqual(ClayClient("k", transport).credits(), 200)
        self.assertEqual(seen["url"], "https://api.clay.com/public/v0/credits/balance")
        self.assertEqual(seen["key"], "k")

    def test_429_honours_retry_after_then_succeeds(self):
        replies = [(429, {"Retry-After": "3"}, b'{"message":"slow down"}'), (200, {}, b'{"balance": 5}')]
        sleeps = []
        c = ClayClient("k", lambda *a: replies.pop(0), sleeps.append)
        self.assertEqual(c.credits(), 5)
        self.assertEqual(sleeps, [3.0])

    def test_error_surfaces_status_and_message(self):
        c = ClayClient("bad", lambda *a: (401, {}, b'{"message":"Authentication failed"}'), lambda s: None)
        with self.assertRaises(ClayError) as cm:
            c.credits()
        self.assertEqual(cm.exception.status, 401)

    def test_run_routine_enforces_1_to_100_items(self):
        c = ClayClient("k", lambda *a: (202, {}, b'{"routine_run_id":"r1"}'), lambda s: None)
        self.assertEqual(c.run_routine("function:t_1", [{"domain": "a.com"}]), "r1")
        with self.assertRaises(ValueError):
            c.run_routine("function:t_1", [{}] * 101)

    def test_webhook_push_posts_every_row_with_token(self):
        posted = []
        def transport(method, url, headers, body):
            posted.append((url, headers.get("x-clay-webhook-auth"), json.loads(body)))
            return 200, {}, b"{}"
        n = push_to_webhook("https://hook", [{"a": 1}, {"a": 2}], "tok", transport, lambda s: None)
        self.assertEqual((n, [p[2] for p in posted], posted[0][1]), (2, [{"a": 1}, {"a": 2}], "tok"))


if __name__ == "__main__":
    unittest.main()
