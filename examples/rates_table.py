"""Today's official leu rates (BNM) as a table.   python examples/rates_table.py [EUR,USD,RON,...]

1 credit per fresh call; cached 3 h (BNM publishes once a working day).
"""

from __future__ import annotations

import sys

from satelit import Satelit, SatelitError

from _cache import attribution_line, cached

want = (sys.argv[1] if len(sys.argv) > 1 else "EUR,USD,RON,UAH,GBP").upper().split(",")
satelit = Satelit(lang="en")  # the key comes from SATELIT_API_KEY

try:
    data, meta, hit = cached("rates:en", 3 * 3600, satelit.rates.list)
except SatelitError as e:
    sys.exit(f"Satelit {e.status} {e.code}: {e.message} {e.docs or ''}")

print(f"{'code':<5} {'name':<20} {'MDL per unit':>12} {'7 days %':>9} {'30 days %':>10}  date")
for r in data:
    if r["code"] in want:
        print(
            f"{r['code']:<5} {r['name']:<20} {r['value'] / r['nominal']:>12.4f} "
            f"{r['change_7d_pct'] if r['change_7d_pct'] is not None else '':>9} "
            f"{r['change_30d_pct'] if r['change_30d_pct'] is not None else '':>10}  {r['date']}"
        )
print(attribution_line(meta))
if meta.get("notice"):
    print(meta["notice"])
print(
    "(from the cache)"
    if hit
    else f"(fresh: {satelit.last_rate['credits_cost']} credit, {satelit.last_rate['credits_remaining']} left)"
)
