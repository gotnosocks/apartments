"""Read-only cloud census of captured building identities, capacity, and inventory labels."""

import modal, json, re, sqlite3, time
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[1]
app = modal.App("chelsea-building-census")
v = modal.Volume.from_name("chelsea-archive")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("parsel==1.10.0")
    .env({"PYTHONPATH": "/root/src"})
    .add_local_dir(
        ROOT / "src/streeteasy_archive",
        "/root/src/streeteasy_archive",
        ignore=["__pycache__"],
    )
)


@app.function(
    image=image,
    cpu=(2, 2),
    memory=(4096, 4096),
    timeout=1800,
    volumes={"/archive": v},
    retries=0,
)
def audit():
    from streeteasy_archive.scope import objects
    from streeteasy_archive.extract import flight_text
    from parsel import Selector

    c = sqlite3.connect(
        "file:/archive/crawls/chelsea-resume/archive.sqlite3?mode=ro",
        uri=True,
        timeout=15,
    )
    g = c.execute("select max(id) from generations").fetchone()[0]
    queue = c.execute(
        "select f.kind,f.state,count(*) from frontier f join scope_urls s using(generation,url) where f.generation=? group by f.kind,f.state",
        (g,),
    ).fetchall()
    roots = {
        r[0]
        for r in c.execute(
            "select url from scope_buildings where generation=?", (g,)
        ).fetchall()
    }
    snaps = {
        u: i
        for u, i in c.execute(
            "select url,max(id) from snapshots where generation=? group by url", (g,)
        ).fetchall()
    }
    records = []
    unparsed = []
    inventories = []
    building_urls = [
        u for u in snaps if re.fullmatch(r"https://streeteasy.com/building/[^/?#]+", u)
    ]
    print(
        "Start",
        len(roots),
        "scope roots;",
        len(building_urls),
        "captured root URLs",
        flush=True,
    )
    for n, u in enumerate(building_urls):
        row = c.execute(
            "select extracted,observed from snapshots where id=?", (snaps[u],)
        ).fetchone()
        data = json.loads(row[0])
        slug = u.rsplit("/", 1)[1]
        primary = next(
            (
                o
                for o in objects(data)
                if o.get("slug") == slug and "residentialUnitCount" in o
            ),
            None,
        )
        if not primary:
            unparsed.append(u)
            continue
        stream = flight_text(data.get("scripts", []))
        refs = {}
        for m in re.finditer(r"(?<![A-Za-z0-9_])([0-9a-f]+):(?=[{\[])", stream):
            try:
                refs[m[1]] = json.JSONDecoder().raw_decode(stream[m.end() :])[0]
            except ValueError:
                pass

        def resolve(value):
            return (
                refs.get(value[1:], value)
                if isinstance(value, str) and value.startswith("$")
                else value
            )

        keys = [
            "id",
            "slug",
            "name",
            "type",
            "residentialUnitCount",
            "latitude",
            "longitude",
            "buildingAddress",
            "sameNeighborhoodSrpUrl",
            "complexId",
            "yearBuilt",
        ]
        rec = {k: primary.get(k) for k in keys}
        rec.update(
            url=u,
            scoped=u in roots,
            observed=row[1],
            area=resolve(primary.get("area")),
            nyc=resolve(primary.get("nyc")),
        )
        records.append(rec)
        if n % 200 == 0:
            print("Buildings", n, flush=True)
    for u, i in snaps.items():
        if "archive_view=unavailable-" not in u:
            continue
        raw = c.execute(
            "select json_extract(extracted,'$.inventory') from snapshots where id=?",
            (i,),
        ).fetchone()[0]
        inv = json.loads(raw) if raw else {}
        labels = []
        for row in inv.get("rows") or []:
            sel = Selector(text=row)
            anchor = sel.css('a[href*="/rental/"],a[href*="/sale/"]')
            label = " ".join(anchor.xpath("string(.)").getall()).strip()
            if label:
                labels.append(label)
        inventories.append(
            {
                "url": u,
                "records": len(inv.get("records") or inv.get("links") or []),
                "count": inv.get("count"),
                "unique_labels": len(set(labels)),
                "labels": sorted(set(labels)),
            }
        )
    c.close()
    return {
        "at": time.time(),
        "generation": g,
        "queue": queue,
        "scope_roots": len(roots),
        "captured_building_urls": len(building_urls),
        "buildings": records,
        "unparsed_building_urls": unparsed,
        "inventories": inventories,
    }


@app.local_entrypoint()
def main():
    Path("/tmp/chelsea-building-census.json").write_text(
        json.dumps(audit.remote(), indent=2)
    )
    print("Saved /tmp/chelsea-building-census.json")
