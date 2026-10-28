# Enrichment waterfall

A small version of the Clay pattern: for each field, try providers in order, stop at the first hit,
charge nothing for a miss, and keep a ledger of which provider earned its place. It also has a client
for Clay's public API and for a Clay table's webhook source, so the output can flow into a real
Clay workspace.

```
python -m waterfall --input sample_data/companies.csv --out enriched.csv
```

```
12 rows -> sample_data/enriched.csv
site_meta          tried  12  hits  10  (83%)  errors 2  spend $0.00
site_scripts       tried  12  hits   7  (58%)  errors 2  spend $0.00
site_links         tried  12  hits   9  (75%)  errors 2  spend $0.00
site_body          tried   2  hits   0  (0%)  errors 2  spend $0.00
```

That run used 12 real company homepages (companies hiring GTM engineers). The 2 errors are
6sense.com and bitsight.com answering HTTP 403 to a script. `site_body`, the fallback description
provider, only ran for those two and could not reach them either, which is what a fallback looks like
when the failure is upstream of both providers.

## Fields and providers

| Field | Providers, in order | What it reads |
|---|---|---|
| `description` | `site_meta`, then `site_body` | meta/og description, else the first real paragraph outside nav |
| `tech_stack` | `site_scripts` | script and asset signatures for HubSpot, Salesforce/Pardot, Marketo, Segment, 6sense, Intercom and others |
| `careers_url` | `site_links` | a link to a careers or jobs page |

Each enriched row gets `<field>_source` so you can see which provider answered. One homepage fetch is
shared by every provider through a per-row context. Add a provider with
`Provider(name, field, fn, cost)`; a paid one (an email finder, say) goes after the free ones and is
only called when they all missed.

## Clay

`waterfall/clay.py` follows Clay's developer docs:

- `ClayClient(key).credits()` reads `GET /credits/balance` (free to call). I ran this against a real
  workspace key and got the balance back.
- `ClayClient(key).run_routine(id, items)` starts a routine for 1 to 100 items and returns the run id.
  Clay answers 202, which means still running, not done.
- `push_to_webhook(url, rows, token)` posts rows to a table's webhook source, paced, and counts them,
  because a webhook source accepts 50,000 submissions for its lifetime.
- 429 is retried after the `Retry-After` header. Other errors raise `ClayError(status, message)`;
  Clay's error bodies carry no stable codes, so branch on status.

```
CLAY_API_KEY=... python -m waterfall --input sample_data/companies.csv --clay-credits
python -m waterfall --input ... --push-clay-webhook https://api.clay.com/v3/sources/webhook/... --clay-webhook-token ...
```

## Tests

```
python -m unittest discover -s tests -t .
```

Eleven tests, no network: stop at first hit, a miss costs nothing, a known field is never paid for
twice, provider errors fall through and are counted, one fetch is shared, entity decoding, and the
Clay client's header, 429 retry, error mapping, the 100-item cap and the webhook push.

## Limits

- Not live-tested: `run_routine` and `push_to_webhook`. Only the credit balance call was run for real.
  Webhook sources need Clay's Growth plan, and I had no webhook URL to post to.
- Tech detection is signature matching on the homepage HTML. A tool loaded through a tag manager or on
  an inner page is missed, and a missing signature is not proof a company does not use the tool.
- The providers are free and only read public homepages. There is no email finding, since that needs a
  paid data provider or an SMTP check; the engine is built so one can be added in the right order.
- 12 companies is a demo, not a benchmark. The hit rates describe those 12 sites.
