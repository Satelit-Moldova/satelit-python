"""Search shop prices and show the offers of the first match.   python examples/price_search.py lapte 2.5

prices.search costs 3 credits, prices.item 2; both cached 3 h.
"""

from __future__ import annotations

import sys

from satelit import Satelit, SatelitError

from _cache import attribution_line, cached

q = " ".join(sys.argv[1:]) or "lapte"
satelit = Satelit(lang="ro")

try:
    found, found_meta, _ = cached(f"prices:ro:{q}", 3 * 3600, lambda: satelit.prices.search(q=q))
    if not found:
        sys.exit(f'Nothing found for "{q}".')
    total = (found_meta.get("page") or {}).get("total", len(found))
    print(f'"{q}": {total} products, the first {min(5, len(found))}:\n')
    for p in found[:5]:
        print(f"  {p['name']}: from {p['min_price']:.2f} MDL in {p['stores']} shops")
    first = found[0]
    item, meta, _ = cached(f"item:ro:{first['id']}", 3 * 3600, lambda: satelit.prices.item(first["id"]))
except SatelitError as e:
    sys.exit(f"Satelit {e.status} {e.code}: {e.message}")

print(f"\nOffers for {item['name']}:")
for o in sorted(item["offers"], key=lambda o: o["price"])[:8]:
    # A shop price is always shown with the shop's name.
    was = f" (was {o['old_price']:.2f})" if o.get("old_price") else ""
    stock = ", out of stock" if o.get("in_stock") is False else ""
    print(f"  {o['store']['name']:<18} {o['price']:.2f} MDL{was}{stock}")
print("\n" + attribution_line(meta))
