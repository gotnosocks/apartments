"""Tests of analysis.history_pairs."""

import duckdb
import pytest


@pytest.mark.parametrize("ads", [500, 1000, 2000, 3000, 4000])
def test_history_pairs_plan(tmp_path, render_context, ads):
    """Put `ads` ads two to a page unit and two to a history, list each history's ads in its
    events four times, and read DuckDB's plan for the model. Every join in the plan is a hash
    join on the history or an ad's ID.

    At 500, 2,000 and 4,000 ads, DuckDB 1.5.5 plans a nested loop join for a query holding both
    copies of ads.placed in one join, on their unequal page units, which pairs every ad with
    every other."""
    db = duckdb.connect(str(tmp_path / "pipeline.duckdb"))
    db.execute("CREATE SCHEMA ads")
    db.execute(
        f"""CREATE TABLE ads.placed AS SELECT i::VARCHAR AS listing_id,
        (i // 2)::VARCHAR AS page_unit FROM range({ads}) t(i)"""
    )
    db.execute(
        f"""CREATE TABLE ads.answers AS SELECT i AS listing_id,
        hash(i // 2)::UHUGEINT AS history FROM range({ads}) t(i)"""
    )
    db.execute(
        f"""CREATE TABLE ads.history_events AS SELECT hash(i % {ads // 2})::UHUGEINT AS history,
        i % {ads} AS listing_id FROM range({4 * ads}) t(i)"""
    )
    query = render_context.render("analysis.history_pairs").sql(dialect="duckdb")
    plan = "\n".join(row[1] for row in db.sql(f"EXPLAIN {query}").fetchall())
    assert "HASH_JOIN" in plan
    for operator in ("NESTED_LOOP_JOIN", "PIECEWISE_MERGE_JOIN", "CROSS_PRODUCT"):
        assert operator not in plan
