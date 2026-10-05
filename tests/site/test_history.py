"""History: readable accuracy steps, linked PRs, model switches only (playtest round 2)."""

from apartments.site import charts


def test_best_chart_axis_need_not_include_zero():
    times = ["2026-10-01T00:00:00", "2026-10-04T00:00:00"]
    values = [22000.0, 24000.0]
    assert charts.Frame(times, values, zero=True).y0 <= 0
    assert charts.Frame(times, values, zero=False).y0 >= 20000
    tight = charts.lines_over_time(
        [{"name": "b", "points": list(zip(times, values)), "step": True}],
        label="x",
        y_title="y",
        y_format=charts.signed,
        zero=False,
    )
    assert "<path" in str(tight)


def test_changes_link_prs_and_filter_switches(client):
    html = client.get("/research/history").get_data(as_text=True)
    assert 'href="https://github.com/gotnosocks/apartments/pull/' in html
    switches = client.get("/research/history?changes=switches").get_data(as_text=True)
    assert "Showing model switches only" in switches
    assert "PR #" not in switches.split('id="changes"')[1]
    home = client.get("/").get_data(as_text=True)
    assert "model switches only" in home
