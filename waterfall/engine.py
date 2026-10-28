"""Waterfall engine: for each field, try providers in order and stop at the first hit.

A miss costs nothing (same rule Clay uses), a hit costs the provider's price, and every call is
written to a ledger so you can see which provider earned its place in the order.
"""
from collections import defaultdict


class Provider:
    def __init__(self, name, field, fn, cost=0.0):
        self.name, self.field, self.fn, self.cost = name, field, fn, cost


class Waterfall:
    def __init__(self, providers):
        self.providers = providers
        self.ledger = defaultdict(lambda: {"tried": 0, "hits": 0, "errors": 0, "spend": 0.0})

    def enrich(self, row):
        out = dict(row)
        ctx = {}  # shared scratch space so two providers can reuse one fetch
        for field in dict.fromkeys(p.field for p in self.providers):
            if out.get(field):
                continue  # already known, never pay to learn it twice
            for p in (p for p in self.providers if p.field == field):
                led = self.ledger[p.name]
                led["tried"] += 1
                try:
                    value = p.fn(out, ctx)
                except Exception:
                    led["errors"] += 1
                    continue
                if value:
                    led["hits"] += 1
                    led["spend"] += p.cost
                    out[field] = value
                    out[field + "_source"] = p.name
                    break
        return out

    def run(self, rows):
        return [self.enrich(r) for r in rows]

    def report(self):
        lines = []
        for name, l in self.ledger.items():
            rate = l["hits"] / l["tried"] if l["tried"] else 0
            lines.append(f"{name:<18} tried {l['tried']:>3}  hits {l['hits']:>3}  "
                         f"({rate:.0%})  errors {l['errors']}  spend ${l['spend']:.2f}")
        return "\n".join(lines)
