"""Dated university calendars near the neighbourhoods: per school and academic
year (named by its fall), the day fall classes begin, the first day of spring
final exams, commencement and, where published, residence-hall move-in. Read
from copies of NYU's published calendars saved under CAPTURES, which
sources.tsv lists (file, school, parser, URL, when it was fetched): the
registrar's calendar archive page (fall 2005 to summer 2021) as the Wayback
Machine captured it, then the events.nyu.edu Academic Calendar group's JSON
feed by half-year (2018 on; earlier half-years are empty):

    python -m rentfrontier.unical

writes EXTERNAL_ROOT/unical/<date>-<commit>/calendar.csv (school, year, event,
date) and provenance.json, which names the capture each date came from.
Refuses a dirty tree. The dates are announced months ahead, so a listing may
read its own year's.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from rentfrontier.listing_extras import EXTERNAL_ROOT, _git

CAPTURES = EXTERNAL_ROOT / "unical" / "captures"
EVENTS = ("movein", "fall_start", "spring_exams", "commencement")
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        "january february march april may june july august september october"
        " november december".split()
    )
}
# Event: (label pattern, months it may fall in).
LABELS = {
    "movein": (r"(?i)^(?!.*early).*move.?in", (8, 9)),
    "fall_start": (r"(?i)^(fall (\d{4} )?classes begin|first day of fall)", (8, 9)),
    "spring_exams": (r"(?i)^(spring semester (final )?exam|final exam period)", (4, 5)),
    "commencement": (r"(?i)^(university )?commencement", (5,)),
}
YEAR_HEAD = re.compile(r"Fall (\d{4}) - Summer \d{4}")
DATE = re.compile(
    r"^(?:[A-Z][a-z]+day,?\s+)?([A-Z][a-z]+)\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?\s*(-?)\s*$"
)


def lines(page: str) -> list[str]:
    """A page's visible text, one non-empty line per tag-delimited run."""
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    return [s.strip() for s in text.splitlines() if s.strip()]


def _date(line: str, fall: int) -> tuple[dt.date, bool] | None:
    """A line that is just a date, and whether it opens a range ("... -"). A
    date without a year is in the fall year from August, else the next."""
    m = DATE.match(line)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    month = MONTHS[m.group(1).lower()]
    year = int(m.group(3)) if m.group(3) else fall + (month < 8)
    return dt.date(year, month, int(m.group(2))), bool(m.group(4))


def archive_events(page: str) -> list[tuple[int, str, dt.date]]:
    """(fall year, label, first date) for each event on NYU's registrar
    calendar archive page: blocks headed "Fall YYYY - Summer YYYY", each event
    a label line followed by its date line(s)."""
    text, out, year = lines(page), [], None
    for i, line in enumerate(text):
        head = YEAR_HEAD.fullmatch(line)
        if head:
            # The page's index lists the headings back to back; skip those.
            nxt = text[i + 1] if i + 1 < len(text) else ""
            year = None if YEAR_HEAD.fullmatch(nxt) else int(head.group(1))
            continue
        if year is None or _date(line, year):
            continue
        for j in range(i + 1, min(i + 20, len(text))):
            if YEAR_HEAD.fullmatch(text[j]):
                break
            got = _date(text[j], year)
            if got:
                out.append((year, line, got[0]))
                break
    return out


def feed_events(items: list[dict]) -> list[tuple[int, str, dt.date]]:
    """(fall year, title, date) for each item of NYU's academic-calendar JSON
    feed (events.nyu.edu, a list or {"data": list}); the date is local
    (date_iso), else UTC's; the fall year of a date before August is the
    year before."""
    out = []
    for item in items["data"] if isinstance(items, dict) else items:
        day = dt.date.fromisoformat((item.get("date_iso") or item["date_utc"])[:10])
        out.append((day.year - (day.month < 8), item["title"].strip(), day))
    return out


def key_dates(events: list[tuple[int, str, dt.date]]) -> dict[tuple[int, str], dt.date]:
    """{(fall year, event): the earliest date of a matching label}."""
    out: dict[tuple[int, str], dt.date] = {}
    for year, label, day in events:
        for event, (pattern, months) in LABELS.items():
            if re.search(pattern, label) and day.month in months:
                key = (year, event)
                out[key] = min(out.get(key, day), day)
    return out


PARSERS = {"nyu-archive": archive_events, "nyu-feed": feed_events}


def build(captures: Path = CAPTURES) -> tuple[pd.DataFrame, list[dict]]:
    """The calendar (school, year, event, date) and, per date, its source.
    Sources are read in sources.tsv's order and the first to give a date
    keeps it; a later source that disagrees is recorded as a conflict."""
    sources = pd.read_csv(captures / "sources.tsv", sep="\t")
    found: dict[tuple[str, int, str], dict] = {}
    for src in sources.itertuples():
        raw = (captures / src.file).read_text(errors="ignore")
        parsed = PARSERS[src.parser](
            json.loads(raw) if src.file.endswith(".json") else raw
        )
        for (year, event), day in key_dates(parsed).items():
            key = (src.school, year, event)
            if key not in found:
                found[key] = {
                    "date": day.isoformat(),
                    "source": src.url,
                    "conflicts": [],
                }
            elif found[key]["date"] != day.isoformat():
                found[key]["conflicts"].append(
                    {"date": day.isoformat(), "source": src.url}
                )
    table = pd.DataFrame(
        [(s, y, e, v["date"]) for (s, y, e), v in sorted(found.items())],
        columns=["school", "year", "event", "date"],
    )
    provenance = [
        {"school": s, "year": y, "event": e, **v}
        for (s, y, e), v in sorted(found.items())
    ]
    return table, provenance


# Main campuses (Bobst Library on Washington Square; The New School's
# University Center at 63 Fifth Avenue), latitude and longitude.
CAMPUSES = {"NYU": (40.7295, -73.9973), "The New School": (40.7355, -73.9937)}
NEAR_M = 800.0
# Days from residence-hall move-in to the first day of fall classes where NYU
# published move-in (2013, 2015-2021: 9, 4, 9, 9, 9, 9, 2, 6); the median
# stands in for the years it did not.
MOVEIN_GAP = dt.timedelta(days=9)
WINDOWS = {
    "6 weeks before NYU move-in": ("movein", -42, 0),
    "NYU move-in to first day of classes": ("movein", 0, None),
    "2 weeks either side of NYU spring finals": ("spring_exams", -14, 14),
}


def windows(at: pd.Series, calendar: pd.DataFrame, school: str = "NYU") -> pd.DataFrame:
    """Per listing date `at` (naive days), whether it falls in each of
    `WINDOWS` of `school`'s calendar: [anchor + start, anchor + end) days,
    an end of None meaning the first day of fall classes. Move-in is the
    published day, else `MOVEIN_GAP` before classes. Raises if a listing's
    season needs a year the calendar lacks."""
    cal = calendar[calendar.school.eq(school)].pivot(
        index="year", columns="event", values="date"
    )
    cal = cal.apply(pd.to_datetime)
    if "movein" not in cal:
        cal["movein"] = pd.NaT
    cal["movein"] = cal.movein.fillna(cal.fall_start - MOVEIN_GAP)
    days = pd.to_datetime(at).dt.normalize()
    # Fall windows read the listing year's calendar; spring ones the year before.
    need = {"movein": days.dt.year, "spring_exams": days.dt.year - 1}
    out = {}
    for name, (anchor, start, end) in WINDOWS.items():
        year = need[anchor]
        when = cal[anchor].reindex(year).to_numpy()
        stop = (
            cal.fall_start.reindex(year).to_numpy()
            if end is None
            else when + pd.Timedelta(days=end)
        )
        lo = when + pd.Timedelta(days=start)
        missing = pd.isna(when) | pd.isna(stop)
        if missing.any():
            raise ValueError(
                f"no {school} {anchor} for years {sorted(set(year[missing]))}"
            )
        out[name] = (days.to_numpy() >= lo) & (days.to_numpy() < stop)
    return pd.DataFrame(out, index=at.index)


def near_campus(latitude, longitude) -> np.ndarray:
    """Whether each point is within `NEAR_M` metres (great circle) of one of
    `CAMPUSES`; a point without coordinates is not."""
    lat, lon = (
        np.radians(np.asarray(latitude, float)),
        np.radians(np.asarray(longitude, float)),
    )
    near = np.zeros(lat.shape, bool)
    for clat, clon in CAMPUSES.values():
        clat, clon = np.radians(clat), np.radians(clon)
        h = (
            np.sin((lat - clat) / 2) ** 2
            + np.cos(lat) * np.cos(clat) * np.sin((lon - clon) / 2) ** 2
        )
        near |= 2 * 6_371_000.0 * np.arcsin(np.sqrt(h)) <= NEAR_M
    return near


def main():
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("refusing a dirty tree")
    commit = _git("rev-parse", "HEAD")
    started = dt.datetime.now(dt.UTC)
    table, dates = build()
    out_dir = EXTERNAL_ROOT / "unical" / f"{started:%Y%m%d}-{commit[:7]}"
    out_dir.mkdir(parents=True, exist_ok=False)
    path = out_dir / "calendar.csv"
    table.to_csv(path, index=False)
    sources = CAPTURES / "sources.tsv"
    (out_dir / "provenance.json").write_text(
        json.dumps(
            {
                "captures": str(CAPTURES),
                "sources_sha256": hashlib.sha256(sources.read_bytes()).hexdigest(),
                "built_at": started.isoformat(),
                "commit": commit,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "dates": dates,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {path}: {len(table)} dates")
    print(
        table.pivot_table(
            index="year", columns=["school", "event"], values="date", aggfunc="first"
        ).to_string()
    )


if __name__ == "__main__":
    main()
