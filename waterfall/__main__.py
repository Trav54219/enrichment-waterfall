import argparse
import csv
import os
import sys

from . import providers
from .clay import ClayClient, push_to_webhook
from .engine import Waterfall


def main(argv=None):
    ap = argparse.ArgumentParser(prog="waterfall", description="Clay-style enrichment waterfall")
    ap.add_argument("--input", required=True, help="CSV with a `domain` column")
    ap.add_argument("--out", default="enriched.csv")
    ap.add_argument("--push-clay-webhook", metavar="URL", help="also post each enriched row to a Clay webhook source")
    ap.add_argument("--clay-webhook-token", default=os.environ.get("CLAY_WEBHOOK_TOKEN"))
    ap.add_argument("--clay-credits", action="store_true", help="print the Clay credit balance (needs CLAY_API_KEY)")
    a = ap.parse_args(argv)

    if a.clay_credits:
        print("Clay credits:", ClayClient(os.environ["CLAY_API_KEY"]).credits())

    with open(a.input, newline="") as f:
        rows = list(csv.DictReader(f))
    wf = Waterfall(providers.build())
    out = wf.run(rows)
    cols = list(dict.fromkeys(k for r in out for k in r))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} rows -> {a.out}\n{wf.report()}")
    if a.push_clay_webhook:
        print("pushed to Clay:", push_to_webhook(a.push_clay_webhook, out, a.clay_webhook_token))


if __name__ == "__main__":
    sys.exit(main())
