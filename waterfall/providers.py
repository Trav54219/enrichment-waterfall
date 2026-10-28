"""Providers. Each takes (row, ctx) and returns a value or None. All are free and stdlib-only.

`fetch` is injectable so tests run without a network.
"""
import html as htmllib
import re
import urllib.request

from .engine import Provider

UA = {"User-Agent": "Mozilla/5.0 (enrichment-waterfall; portfolio project)"}

# Signature -> tool. A script tag, asset path or global is how a site gives away its stack.
TECH = {
    "HubSpot": r"js\.hs-scripts\.com|hs-analytics|hubspot\.com",
    "Salesforce": r"pardot|salesforce\.com|force\.com",
    "Segment": r"cdn\.segment\.com|analytics\.js",
    "Google Tag Manager": r"googletagmanager\.com",
    "Intercom": r"intercomcdn|widget\.intercom\.io",
    "Drift": r"js\.driftt\.com|drift\.com",
    "Marketo": r"munchkin|marketo\.(com|net)",
    "6sense": r"6sc\.co|6sense\.com",
    "Clearbit": r"clearbit\.com",
    "Calendly": r"calendly\.com",
    "Stripe": r"js\.stripe\.com",
}


def default_fetch(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(400_000).decode("utf-8", "replace")


def _homepage(row, ctx, fetch):
    if "html" not in ctx:
        domain = row.get("domain", "").strip().lower()
        ctx["html"] = fetch(f"https://{domain}") if domain else ""
    return ctx["html"]


def _meta(html, *names):
    for n in names:
        for pat in (rf'<meta[^>]+(?:name|property)=["\']{n}["\'][^>]+content=["\']([^"\']+)',
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{n}["\']'):
            m = re.search(pat, html, re.I)
            if m and len(m.group(1).strip()) > 20:
                return re.sub(r"\s+", " ", htmllib.unescape(m.group(1))).strip()
    return None


def build(fetch=default_fetch):
    def description_meta(row, ctx):
        return _meta(_homepage(row, ctx, fetch), "description", "og:description", "twitter:description")

    def description_body(row, ctx):
        html = _homepage(row, ctx, fetch)
        html = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", html)
        for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", html):
            text = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", p))).strip()
            if len(text) > 60:
                return text[:300]
        return None

    def tech_stack(row, ctx):
        html = _homepage(row, ctx, fetch)
        found = sorted(t for t, pat in TECH.items() if re.search(pat, html, re.I))
        return ", ".join(found) or None

    def careers_page(row, ctx):
        html = _homepage(row, ctx, fetch)
        m = re.search(r'href=["\']([^"\']*(?:careers|jobs)[^"\']*)["\']', html, re.I)
        if not m:
            return None
        href = m.group(1)
        return href if href.startswith("http") else f"https://{row['domain']}/{href.lstrip('/')}"

    return [
        Provider("site_meta", "description", description_meta),
        Provider("site_body", "description", description_body),
        Provider("site_scripts", "tech_stack", tech_stack),
        Provider("site_links", "careers_url", careers_page),
    ]
