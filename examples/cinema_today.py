"""What is on in Moldova's cinemas today.   python examples/cinema_today.py [city]

movies.board needs no key and costs 0 credits; cached 1 h. (movies.today, with a city or a date, costs 40.)
"""

from __future__ import annotations

import sys
import unicodedata

from satelit import Satelit, SatelitError

from _cache import attribution_line, cached


def plain(text: str) -> str:
    """Lowercase without diacritics, so "chisinau" finds "Chișinău"."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


city = plain(sys.argv[1] if len(sys.argv) > 1 else "")
satelit = Satelit(lang="en")

try:
    data, meta, _ = cached("board:en", 3600, satelit.movies.board)
except SatelitError as e:
    sys.exit(f"Satelit {e.status} {e.code}: {e.message}")

print(f"Cinemas on {data['day']}\n")
for entry in data["cinemas"]:
    cinema = entry["cinema"]
    if city and city not in plain(cinema.get("city") or ""):
        continue
    print(f"{cinema['name']} ({cinema.get('city')})")
    for film in entry["films"]:
        times = [s["time"] for s in film["sessions"] if s["date"] == data["day"]]
        title = film.get("title") or film.get("listed_title") or ""
        if times:
            print(f"  {title[:34]:<34} {'  '.join(times)}")
    print()
print(attribution_line(meta))
