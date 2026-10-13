"""Close an unfinished generation's queue so a new generation can start.

store.new_generation refuses to start while any generation still has pending or in-flight
pages. A restart with new crawl code (a fresh scope, rental histories read again) needs the
old queue out of the way first. This marks those rows `abandoned`, records how many and why
under `closed_queue:<generation>` in metadata, and leaves every observation, snapshot and
body alone. The next `update` copies the abandoned URLs into the new generation, where scope
rules decide again whether to fetch them.
"""

import json
import time

ABANDONED = "abandoned"


def close_queue(store, generation, reason):
    if not reason or not reason.strip():
        raise ValueError("close-queue needs a --reason")
    row = store.db.execute(
        "SELECT status FROM generations WHERE id=?", (generation,)
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown generation {generation}")
    with store._tx():
        counts = dict(
            store.db.execute(
                """SELECT kind, count(*) FROM frontier WHERE generation=?
                AND state IN ('pending','inflight') GROUP BY kind""",
                (generation,),
            ).fetchall()
        )
        store.db.execute(
            """UPDATE frontier SET state=? WHERE generation=?
            AND state IN ('pending','inflight')""",
            (ABANDONED, generation),
        )
        store.db.execute(
            "INSERT OR REPLACE INTO metadata VALUES(?,?)",
            (
                f"closed_queue:{generation}",
                json.dumps(
                    {"closed": time.time(), "reason": reason.strip(), "by_kind": counts}
                ),
            ),
        )
    return {
        "generation": generation,
        "abandoned": sum(counts.values()),
        "by_kind": counts,
    }
