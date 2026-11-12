"""Write a reading dossier per target ad: python dossier.py TARGETS HIST RAW OUTDIR"""

import sys, json, os, pandas as pd, numpy as np

T = pd.read_parquet(sys.argv[1])
H = pd.read_parquet(sys.argv[2])
out = sys.argv[4]
os.makedirs(out, exist_ok=True)
Hall = pd.read_parquet("/data1/apartments/site/diagnostics/history.parquet")
raw = {}
for l in open(sys.argv[3]):
    x = json.loads(l)
    k = x["listing_id"]
    if k not in raw or (x["collected_at"], x["snapshot_id"]) >= (raw[k][0], raw[k][1]):
        raw[k] = (x["collected_at"], x["snapshot_id"], x["raw_listing_json"])


def rec(lid):
    r = raw.get(str(lid))
    return json.loads(r[2]) if r else None


def money(v):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"${v:,.0f}"


for _, t in T.iterrows():
    lid = str(t.listing_id)
    d = rec(lid) or {}
    L = [
        f"# Ad {lid} ({t['tail']} the model)",
        "",
        f"- Building {t.building}, {t.address}, unit label {t.unit!r} (unit_id {t.unit_id}), {t.neighbourhood}",
        f"- Day {t.day}, status {t.status or 'off market'}; bedrooms {t.bedrooms:g}, full baths {t.full_baths}, half {t.half_baths}, square feet {t.square_feet}, floor {t.floor}, building floors {t.building_floors}",
        f"- Ask {money(t.ask)}; model median {money(t.model_median)}, 80% range {money(t.model_lo80)} to {money(t.model_hi80)}; gap (log) {t.gap:+.3f}, miss {t.miss:+.2f} sd",
        f"- Model basis {t.basis}: unit's training ads {t.unit_ads}, building's training ads {t.building_ads}",
        f"- Previous ad for this apartment: {money(t.prev_ask)} on {t.prev_day} with {t.prev_bedrooms} bedrooms",
        f"- months_free {t.months_free}, first ask {money(t.first_ask)}, days on market {t.days_on_market}, lease_term {t.lease_term}, penthouse {t.penthouse}, top_floor {t.top_floor}, private_outdoor {t.private_outdoor}, view {t.view}, lister {t.broker_group} ({t.lister_kind}, {t.source_type}), building {t.building_elevator} elevator / doorman {t.building_doorman} / {t.tenure} / built {t.year_built}, class {t.building_class}",
        f"- Detector flags: {list(t['flags']) if t['flags'] is not None else []}",
        "",
    ]
    if d:
        p = d.get("pricing") or {}
        pd_ = d.get("propertyDetails") or {}
        L += [
            "## The ad's record (last capture)",
            "",
            f"- Record status {d.get('status')}, on market {d.get('onMarketAt')}, off market {d.get('offMarketAt')}, lister {((d.get('legacy') or {}).get('sourceGroupLabel'))}",
            f"- Price {money(p.get('price'))}; net effective {money(p.get('netEffectiveRent'))}; months free {p.get('monthsFree')}; lease months {p.get('leaseTermMonths')}; furnished rent {money(p.get('furnishedRent'))}; rented price {money(p.get('rentedPrice'))}",
            f"- Price changes: "
            + ", ".join(
                f"{c['changedAt'][:10]} {money(c['price'])}"
                for c in (p.get("priceChanges") or [])
            ),
            f"- Fees: monthly {p.get('monthlyFees')}, move-in {p.get('moveInFees')}, additional {p.get('additionalFees')}",
            f"- Coded: bedrooms {pd_.get('bedroomCount')}, full baths {pd_.get('fullBathroomCount')}, half {pd_.get('halfBathroomCount')}, rooms {pd_.get('roomCount')}, living area {pd_.get('livingAreaSize')}",
            f"- Features {(pd_.get('features') or {})}",
            f"- Amenities {(pd_.get('amenities') or {}).get('list')}",
            f"- Address on record: {(pd_.get('address') or {})}",
        ]
        m = d.get("media") or {}
        fps = [
            f"https://photos.zillowstatic.com/fp/{x['key']}-p_e.webp"
            for x in (m.get("floorPlans") or [])
        ]
        ph = [
            f"https://photos.zillowstatic.com/fp/{x['key']}-p_e.webp"
            for x in (m.get("photos") or [])
        ][:6]
        L += [f"- Floor plans: {fps or 'none'}", f"- First photos: {ph or 'none'}", ""]
        ph_ = d.get("propertyHistory") or []
        if ph_:
            L += ["## StreetEasy's history of the unit (propertyHistory)", ""]
            for e in ph_[:12]:
                ev = "; ".join(
                    f"{x.get('date')} {x.get('status')} {money(x.get('price'))}"
                    for x in (e.get("rentalEventsOfInterest") or [])[:8]
                )
                L.append(
                    f"- listing {e.get('listingId')} ({e.get('sourceGroupLabel')}): {ev}"
                )
            L.append("")
        L += [
            "## Description of this ad",
            "",
            (d.get("description") or "(none)").strip(),
            "",
        ]
    else:
        L += ["(no raw record found)", ""]
    hh = H[
        (H.building + "|" + H.unit_id.str.replace(r"~\d+$", "", regex=True)) == t.apt
    ].sort_values("day")
    L += [
        "## All ads for this apartment in the fit data",
        "",
        "| listing | day | ask | beds | full baths | held out |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in hh.iterrows():
        L.append(
            f"| {r.listing_id} | {r.day} | {money(r.ask)} | {r.bedrooms:g} | {r.full_baths} | {r.heldout} |"
        )
    L.append("")
    for _, r in hh[hh.listing_id.astype(str) != lid].tail(3).iterrows():
        o = rec(r.listing_id)
        if o and o.get("description"):
            pdo = o.get("propertyDetails") or {}
            L += [
                f"### Earlier ad {r.listing_id} ({r.day}, {money(r.ask)}, coded {pdo.get('bedroomCount')} bed, {pdo.get('livingAreaSize')} sq ft)",
                "",
                o["description"].strip()[:1500],
                "",
            ]
    b = Hall[
        (Hall.building == t.building)
        & (Hall.bedrooms == t.bedrooms)
        & (Hall.listing_id.astype(str) != lid)
    ].copy()
    b["dd"] = (pd.to_datetime(b.day) - pd.to_datetime(t.day)).abs()
    b = b.sort_values("dd").head(15).sort_values("day")
    L += [
        f"## Other ads in the building with {t.bedrooms:g} bedrooms (nearest in time, up to 15)",
        "",
        "| unit | day | ask | full baths |",
        "|---|---|---|---|",
    ]
    for _, r in b.iterrows():
        L.append(f"| {r.unit} | {r.day} | {money(r.ask)} | {r.full_baths} |")
    open(f"{out}/{lid}.md", "w").write("\n".join(L) + "\n")
print(len(T))
