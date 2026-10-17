"""ads.changes: the answers a build reads anew.

In a full build the table holds every answer of `raw.ads`, with `incremental` false. In a top-up
build, which `ops/pipeline/build.py` asks for by setting the variable `incremental`, it holds
only the answers missing from the previous build's `ads.answers`, with `incremental` true. The
table may then be empty. The models of kind `merge` read these answers or the ads they change,
and `materializations/merge.py` merges their rows with the previous build's tables.

The model reads the previous answers through the prod view `ads.answers`. During a plan the view
still points to the previous build's table, so the model takes no dependency on it. Before a top-up
build reads only the new answers, the model checks that the previous answers still hold:

1. The prod view exists.
2. Each previous answer is in `raw.ads` with the same fetch time, outcome, record hash and
   region.
3. `raw.ads` holds as many answers as the previous answers and the new ones together, so an
   answer given twice still fails the audit of `ads.answers`.

When a check fails, the table holds every answer with `incremental` false, and the build is a
full one.

The model also reads the variable `merge_code`, the SHA-256 of `materializations/merge.py`. An
edit to that file then gives the model a new fingerprint, and the plan rebuilds it and every
model below it, the models of kind `merge` among them.
"""

from sqlglot import exp
from sqlmesh import ExecutionContext, model

COLUMNS = {"listing_id": "BIGINT", "response_id": "BIGINT", "incremental": "BOOLEAN"}


def previous_holds(cursor, ads):
    """Whether the previous build's answers are all in `ads`, with no new answer repeating one."""
    if not cursor.execute(
        """SELECT count(*) FROM information_schema.tables
        WHERE table_catalog = current_database() AND table_schema = 'ads'
            AND table_name = 'answers'"""
    ).fetchone()[0]:
        return False
    lost, counts = cursor.execute(
        f"""SELECT
            (SELECT count(*) FROM ads.answers p WHERE NOT EXISTS (
                SELECT 1 FROM {ads} r
                WHERE r.listing_id = p.listing_id AND r.response_id = p.response_id
                    AND r.fetched = p.fetched AND r.outcome = p.outcome
                    AND r.record_sha256 IS NOT DISTINCT FROM p.record_sha256
                    AND r.region IS NOT DISTINCT FROM p.region)),
            (SELECT count(*) FROM {ads})
                = (SELECT count(*) FROM ads.answers)
                + (SELECT count(*) FROM {ads} r ANTI JOIN ads.answers p
                    USING (listing_id, response_id))"""
    ).fetchone()
    return lost == 0 and counts


@model(
    "ads.changes",
    kind="FULL",
    columns=COLUMNS,
    grain=["listing_id", "response_id"],
    description="The answers this build reads anew: every answer in a full build, the new ones in a top-up build.",
)
def execute(context: ExecutionContext, start, end, execution_time, **kwargs):
    ads = context.resolve_table("raw.ads")
    cursor = context.engine_adapter.connection.cursor()
    # The variable only enters the model's fingerprint.
    context.var("merge_code")
    incremental = bool(context.var("incremental")) and previous_holds(cursor, ads)
    query = f"SELECT listing_id, response_id, {incremental} AS incremental FROM {ads} r"
    if incremental:
        query += " ANTI JOIN ads.answers p USING (listing_id, response_id)"
    # The query runs when the materialization writes the table, so an empty result still
    # replaces the rows of an earlier evaluation.
    yield exp.maybe_parse(query, dialect="duckdb")
