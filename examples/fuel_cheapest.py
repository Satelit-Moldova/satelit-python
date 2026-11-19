"""Which station network sells each fuel cheapest today, next to ANRE's cap.   python examples/fuel_cheapest.py

1 credit per fresh call; cached 2 h.
"""

from __future__ import annotations

import sys

from satelit import Satelit, SatelitError

from _cache import attribution_line, cached

LABEL = {"a95": "Petrol A95", "diesel": "Diesel", "lpg": "LPG"}
satelit = Satelit(lang="en")

try:
    data, meta, hit = cached("fuel:en", 2 * 3600, satelit.fuel.today)
except SatelitError as e:
    sys.exit(f"Satelit {e.status} {e.code}: {e.message}")

print(f"Fuel prices on {data['date']}, MDL per litre\n")
for fuel, label in LABEL.items():
    rng = (data.get("range") or {}).get(fuel)
    if not rng:
        continue
    # Every network at the lowest price, not only the first one named.
    cheapest = [n["name"] for n in data["networks"] if n["prices"].get(fuel) == rng["min"]]
    cap = (data.get("cap") or {}).get(fuel)
    cap_text = f", ANRE cap {cap:.2f}" if cap else ""
    others = f"dearest {rng['max']:.2f}, {rng['networks']} networks{cap_text}"
    print(f"{label:<11} {rng['min']:.2f} at {', '.join(cheapest)}  ({others})")
print("\n" + attribution_line(meta) + ("  (from the cache)" if hit else ""))
