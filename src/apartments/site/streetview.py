"""Street View links that stand in the street, facing the building.

Google's `map_action=pano` opens the panorama nearest the viewpoint. A
building's own coordinates sit inside its lot, where the nearest panorama
can be a photo inside a shop (Ben, 2026-10-06: 225 W 14th St opened inside
a restaurant). So the viewpoint moves to the nearest point of the building's
own street (from its address) on the rent map's street centrelines, and the
heading turns the camera back to the building. Without a map, a known street
nearby or coordinates, the link falls back to the building's own point, then
to a Maps search for the address.
"""

from __future__ import annotations

import itertools
import math
import re
from urllib.parse import urlencode

# Farthest a building's own street may be before the nearest street of any
# name is used instead (metres): an address on a corner or a long lot.
OWN_STREET_M = 120.0
ORDINAL = re.compile(r"^(\d+)(?:st|nd|rd|th)$")
WORDS = {
    "west": "W",
    "east": "E",
    "street": "ST",
    "avenue": "AVE",
    "place": "PL",
    "south": "S",
    "lane": "LN",
    "road": "RD",
}
NUMBERS = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
    "eleventh": "11",
    "twelfth": "12",
}
AMERICAS = "AVE OF THE AMERICAS"
ALIASES = {"6 AVE": AMERICAS, "AVE OF AMERICAS": AMERICAS, "AMERICAS AVE": AMERICAS}


def street_key(address: str | None) -> str | None:
    """'225 West 14th Street' -> 'W 14 ST', as the street centrelines name it."""
    if not address:
        return None
    words = address.replace(",", " ").split()
    if words and re.fullmatch(r"\d+[A-Za-z]?(-\d+[A-Za-z]?)?", words[0]):
        words = words[1:]
    # "1/2 Jane Street", "Rear Perry Street"
    while words and words[0].lower() in ("1/2", "rear"):
        words = words[1:]
    out = []
    for w in words:
        lw = w.lower().rstrip(".")
        m = ORDINAL.match(lw)
        out.append(m.group(1) if m else NUMBERS.get(lw) or WORDS.get(lw) or w.upper())
    key = " ".join(out)
    return ALIASES.get(key, key) or None


def _fit_inverse(buildings: list[dict]):
    """The map's grid (x, y) -> (lon, lat): the projection is affine, so a
    least-squares fit on the buildings recovers it exactly."""
    pts = [b for b in buildings if b.get("lat") is not None and "x" in b]
    if len(pts) < 3:
        return None

    def solve(target):
        # Normal equations for target = a*x + b*y + c.
        s = [[0.0] * 3 for _ in range(3)]
        r = [0.0] * 3
        for p in pts:
            v = (p["x"], p["y"], 1.0)
            for i in range(3):
                r[i] += v[i] * p[target]
                for j in range(3):
                    s[i][j] += v[i] * v[j]
        # Gaussian elimination.
        for i in range(3):
            k = max(range(i, 3), key=lambda k: abs(s[k][i]))
            s[i], s[k], r[i], r[k] = s[k], s[i], r[k], r[i]
            if abs(s[i][i]) < 1e-12:
                return None
            for k in range(i + 1, 3):
                f = s[k][i] / s[i][i]
                for j in range(i, 3):
                    s[k][j] -= f * s[i][j]
                r[k] -= f * r[i]
        c = [0.0] * 3
        for i in (2, 1, 0):
            c[i] = (r[i] - sum(s[i][j] * c[j] for j in range(i + 1, 3))) / s[i][i]
        return c

    lon, lat = solve("lon"), solve("lat")
    if lon is None or lat is None:
        return None
    return lambda x, y: (
        lon[0] * x + lon[1] * y + lon[2],
        lat[0] * x + lat[1] * y + lat[2],
    )


def _nearest(px, py, streets):
    """The nearest point to (px, py) on any of the streets' segments, and its
    distance."""
    best = (math.inf, None)
    for s in streets:
        pts = s["points"]
        for (ax, ay), (bx, by) in itertools.pairwise(pts):
            dx, dy = bx - ax, by - ay
            seg = dx * dx + dy * dy
            t = (
                0.0
                if not seg
                else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg))
            )
            qx, qy = ax + t * dx, ay + t * dy
            d = math.hypot(px - qx, py - qy)
            if d < best[0]:
                best = (d, (qx, qy))
    return best


def viewpoint(data: dict | None, building_id: str, address: str | None):
    """(lat, lon, heading) in the street in front of the building, or None."""
    if not data:
        return None
    index = data.get("_index", {}).get(building_id)
    if index is None:
        return None
    b = data["buildings"][index]
    if b.get("lat") is None or "x" not in b:
        return None
    cache = data.setdefault("_streetview", {})
    if "prepared" not in cache:
        streets = (data.get("basemap") or {}).get("streets") or []
        by_name: dict[str, list] = {}
        for s in streets:
            by_name.setdefault(s.get("name"), []).append(s)
        cache["prepared"] = (_fit_inverse(data["buildings"]), streets, by_name)
    inverse, streets, by_name = cache["prepared"]
    if inverse is None or not streets:
        return None
    d, q = _nearest(b["x"], b["y"], by_name.get(street_key(address), []))
    if q is None or d > OWN_STREET_M:
        d, q = _nearest(b["x"], b["y"], streets)
    if q is None:
        return None
    lon, lat = inverse(*q)
    # Compass bearing from the viewpoint to the building.
    east = (b["lon"] - lon) * math.cos(math.radians(lat))
    north = b["lat"] - lat
    heading = math.degrees(math.atan2(east, north)) % 360
    return lat, lon, heading


def link(data, building_id, latitude, longitude, address) -> str | None:
    """A Street View link facing the building from its street; its own point
    without a map; a Maps search for the address without coordinates."""
    view = viewpoint(data, building_id, address) if building_id else None
    if view:
        lat, lon, heading = view
        return "https://www.google.com/maps/@?" + urlencode(
            {
                "api": 1,
                "map_action": "pano",
                "viewpoint": f"{lat:.6f},{lon:.6f}",
                "heading": f"{heading:.0f}",
            }
        )
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        return "https://www.google.com/maps/@?" + urlencode(
            {
                "api": 1,
                "map_action": "pano",
                "viewpoint": f"{latitude:.6f},{longitude:.6f}",
            }
        )
    if isinstance(address, str) and address:
        return "https://www.google.com/maps/search/?" + urlencode(
            {"api": 1, "query": f"{address}, New York, NY"}
        )
    return None
