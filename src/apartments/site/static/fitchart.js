// Zoomable fit charts (accuracy against fit time), drawn with Chart.js and
// its zoom plugin (VENDOR.md). The server's SVG is what shows without
// JavaScript; here a canvas replaces it, built from the figure's chart-spec
// block (every fit in data units). A mouse drag draws a zoom box, and Ctrl
// with the wheel zooms; the box goes into the URL (the figure's prefix + x0,
// x1, y0, y1), so a shared link opens zoomed, as it does for the server's
// chart. On a phone a touch keeps scrolling the page, and the "Set the range
// by hand" form zooms. The hover card is the site's own (.chart-tip): beside
// the point, or under the plot on a narrow screen. With the figure focused,
// the arrow keys step through the fits, Enter opens one and Escape closes the
// card. site.js leaves the figures marked data-enhanced alone.
(function () {
  "use strict";
  if (!window.Chart || !window.ChartZoom) return;
  var KEYS = ["x0", "x1", "y0", "y1"];
  var ORDER = ["subset", "failing", "other", "frontier", "served"];
  var dark = window.matchMedia("(prefers-color-scheme: dark)");

  function palette() {
    var style = getComputedStyle(document.documentElement);
    var c = {};
    ["ink", "ink-2", "muted", "grid", "axis", "s1", "s2", "warn", "accent"].forEach(function (name) {
      c[name] = style.getPropertyValue("--" + name).trim();
    });
    return c;
  }

  function rgba(color, a) {
    var m = /^#([0-9a-f]{6})$/i.exec(color);
    if (!m) return color;
    var n = parseInt(m[1], 16);
    return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
  }

  function signed(v) {
    if (!v) return "0";
    return (v > 0 ? "+" : "−") + Math.abs(Math.round(v)).toLocaleString("en-US");
  }

  function number(v) {
    return Number(v.toPrecision(6)).toLocaleString("en-US");
  }

  // A fit's mark, as the server draws it: filled for served and frontier
  // fits, hollow for failing and subset fits, a diamond for an exploration fit.
  function look(p, c) {
    var fade = p.faded ? 0.4 : 1;
    var radius = p.kind === "served" ? 5.5 : 4;
    var mark = {
      style: p.tier === "exploration" ? "rectRot" : "circle",
      radius: p.tier === "exploration" ? radius * 1.25 : radius,
      fill: "transparent",
      stroke: "transparent",
      width: 0
    };
    if (p.kind === "served") mark.fill = rgba(c.s2, fade);
    else if (p.kind === "frontier") mark.fill = rgba(c.s1, fade);
    else if (p.kind === "other") mark.fill = rgba(c.muted, 0.55 * fade);
    else {
      mark.stroke = rgba(p.kind === "failing" ? c.muted : c.s1, (p.kind === "failing" ? 1 : 0.7) * fade);
      mark.width = 1.5;
    }
    return mark;
  }

  function readout(tip, point) {
    tip.replaceChildren();
    var title = document.createElement("div");
    title.className = "tip-title";
    title.textContent = point.title;
    tip.appendChild(title);
    point.rows.forEach(function (row) {
      var line = document.createElement("div");
      line.className = "tip-row";
      var label = document.createElement("span");
      label.textContent = row[0];
      var value = document.createElement("strong");
      value.textContent = row[1];
      line.appendChild(label);
      line.appendChild(value);
      tip.appendChild(line);
    });
  }

  function setup(figure) {
    var block = figure.querySelector("script.chart-spec");
    var svg = figure.querySelector("svg");
    var tip = figure.querySelector(".chart-tip");
    if (!block || !svg || !tip) return;
    var spec;
    try {
      spec = JSON.parse(block.textContent);
    } catch (error) {
      return;
    }
    var prefix = spec.zoom;
    var floor = spec.floor;
    var c = palette();
    // Fits below the floor are drawn at it, as on the server's chart.
    var fits = spec.points.map(function (p) {
      var low = floor !== null && p.y < floor;
      return {
        x: p.x,
        y: low ? floor : p.y,
        p: p,
        rows: low ? p.rows.concat([["Note", "below the chart's range, drawn at its floor"]]) : p.rows
      };
    });
    fits.sort(function (a, b) {
      return (a.p.faded === b.p.faded ? 0 : a.p.faded ? -1 : 1) || ORDER.indexOf(a.p.kind) - ORDER.indexOf(b.p.kind);
    });
    var byX = fits.slice().sort(function (a, b) { return a.x - b.x; });

    var datasets = [];
    // One design at several draw counts: joined in draw order, under the marks.
    var groups = {};
    fits.forEach(function (f) {
      if (f.p.group !== null && f.p.group !== undefined) (groups[f.p.group] = groups[f.p.group] || []).push(f);
    });
    Object.keys(groups).forEach(function (k) {
      var g = groups[k];
      if (g.length < 2) return;
      g = g.slice().sort(function (a, b) { return (a.p.draws || 0) - (b.p.draws || 0); });
      datasets.push({
        type: "line", kind: "measured", order: 3,
        data: g.map(function (f) { return { x: f.x, y: f.y }; }),
        borderWidth: 1.5, pointRadius: 0, pointHitRadius: 0, pointHoverRadius: 0
      });
    });
    var line = byX.filter(function (f) { return f.p.on_line; });
    if (spec.line && line.length > 1) {
      datasets.push({
        type: "line", kind: "frontier", order: 2,
        data: line.map(function (f) { return { x: f.x, y: f.y }; }),
        borderWidth: 1.5, borderDash: spec.line === "dashed" ? [5, 4] : [],
        pointRadius: 0, pointHitRadius: 0, pointHoverRadius: 0
      });
    }
    var fitIndex = datasets.length;
    datasets.push({
      type: "scatter", kind: "fits", order: 1,
      data: fits,
      pointStyle: function (ctx) { return ctx.raw ? look(ctx.raw.p, c).style : "circle"; },
      pointRadius: function (ctx) { return ctx.raw ? look(ctx.raw.p, c).radius : 4; },
      pointHoverRadius: function (ctx) { return ctx.raw ? look(ctx.raw.p, c).radius + 2 : 6; },
      pointHitRadius: 6,
      backgroundColor: function (ctx) { return ctx.raw ? look(ctx.raw.p, c).fill : c.muted; },
      borderColor: function (ctx) { return ctx.raw ? look(ctx.raw.p, c).stroke : c.muted; },
      borderWidth: function (ctx) { return ctx.raw ? look(ctx.raw.p, c).width : 0; },
      hoverBorderColor: function () { return c.ink; },
      hoverBorderWidth: 2
    });

    function recolour() {
      datasets.forEach(function (d) {
        if (d.kind === "measured") d.borderColor = c.axis;
        if (d.kind === "frontier") d.borderColor = rgba(c.ink, 0.7);
      });
    }
    recolour();

    // The reference line (the 2-hour limit) where the axis reaches it.
    var reference = {
      id: "reference",
      afterDatasetsDraw: function (chart) {
        if (!spec.x_line) return;
        var x = chart.scales.x, area = chart.chartArea;
        var at = x.getPixelForValue(spec.x_line[0]);
        if (at < area.left || at > area.right) return;
        var ctx = chart.ctx;
        ctx.save();
        ctx.strokeStyle = c.warn;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(at, area.top);
        ctx.lineTo(at, area.bottom);
        ctx.stroke();
        // The label runs up the line, clear of the fits beside it.
        ctx.fillStyle = c["ink-2"];
        ctx.font = "11px " + Chart.defaults.font.family;
        ctx.translate(at - 5, area.bottom - 6);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(spec.x_line[1], 0, 0);
        ctx.restore();
      }
    };

    var holder = document.createElement("div");
    holder.className = "fit-canvas";
    var canvas = document.createElement("canvas");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", spec.label);
    holder.appendChild(canvas);
    svg.after(holder);

    var current = null;
    var zoomedAt = 0;

    // An axis end that is not a round tick (the floor, or a zoom box's
    // edge) gets no label: "+20,077" next to "+20,500" reads as noise.
    function bound(v, i, ticks) {
      if (i !== 0 && i !== ticks.length - 1) return false;
      if (ticks.length < 3) return false;
      var step = Math.abs(ticks[2].value - ticks[1].value);
      var r = Math.abs(v / step - Math.round(v / step));
      return r > 1e-6;
    }

    function axis(title) {
      return {
        title: { display: true, text: title, color: c["ink-2"], font: { size: 12 } },
        grid: { color: c.grid },
        border: { color: c.axis },
        ticks: { color: c.muted, font: { size: 11 } }
      };
    }
    var x = axis(spec.x_title);
    x.type = "linear";
    x.beginAtZero = true;
    x.ticks.callback = function (v, i, ticks) { return bound(v, i, ticks) ? "" : number(v); };
    var y = axis(spec.y_title);
    y.grace = "5%";
    if (floor !== null) y.min = floor;
    y.ticks.callback = function (v, i, ticks) {
      if (bound(v, i, ticks)) return "";
      return spec.y_signed ? signed(v) : number(v);
    };

    var chart;
    try {
      chart = new Chart(canvas, {
        data: { datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          clip: 8,
          interaction: { mode: "nearest", intersect: true },
          scales: { x: x, y: y },
          plugins: {
            legend: { display: false },
            tooltip: { enabled: false },
            zoom: {
              limits: { x: { min: 0 } },
              zoom: {
                mode: "xy",
                drag: {
                  enabled: true,
                  threshold: 6,
                  backgroundColor: rgba(c.accent, 0.12),
                  borderColor: c.accent,
                  borderWidth: 1
                },
                wheel: { enabled: true, modifierKey: "ctrl" },
                onZoomComplete: function () { zoomedAt = Date.now(); save(); }
              }
            }
          },
          onHover: function (event, elements) {
            var hit = elements.filter(function (e) { return e.datasetIndex === fitIndex; })[0];
            if (hit) show(fits[hit.index], false); else hide();
          },
          onClick: function (event, elements) {
            if (Date.now() - zoomedAt < 400) return; // the end of a drag
            var hit = elements.filter(function (e) { return e.datasetIndex === fitIndex; })[0];
            if (hit && fits[hit.index].p.href) window.location.href = fits[hit.index].p.href;
          }
        },
        plugins: [reference]
      });
    } catch (error) {
      holder.remove();
      return;
    }
    svg.remove();
    figure.setAttribute("data-enhanced", "");
    // The server's note for a box with no fits in it: the chart here shows
    // the box and a way back out.
    var empty = figure.previousElementSibling;
    if (empty && empty.classList.contains("empty-zoom")) empty.remove();

    function show(f, highlight) {
      current = f;
      if (highlight) {
        var active = [{ datasetIndex: fitIndex, index: fits.indexOf(f) }];
        chart.setActiveElements(active);
        chart.update("none");
      }
      readout(tip, { title: f.p.title, rows: f.rows });
      tip.hidden = false;
      var below = figure.clientWidth < 480;
      tip.classList.toggle("below", below);
      canvas.style.cursor = f.p.href ? "pointer" : "";
      if (below) {
        tip.style.left = "";
        tip.style.top = "";
        return;
      }
      var box = canvas.getBoundingClientRect(), frame = figure.getBoundingClientRect();
      var px = box.left - frame.left + chart.scales.x.getPixelForValue(f.x);
      var py = box.top - frame.top + chart.scales.y.getPixelForValue(f.y);
      var left = px + 14;
      if (left + tip.offsetWidth > figure.clientWidth) left = px - tip.offsetWidth - 14;
      var top = py - 10;
      if (top + tip.offsetHeight > box.bottom - frame.top) top = py - tip.offsetHeight - 10;
      tip.style.left = Math.max(0, left) + "px";
      tip.style.top = Math.max(0, top) + "px";
    }

    function hide() {
      current = null;
      tip.hidden = true;
      canvas.style.cursor = "";
      if (chart.getActiveElements().length) {
        chart.setActiveElements([]);
        chart.update("none");
      }
    }
    canvas.addEventListener("mouseleave", hide);
    figure.addEventListener("blur", hide);
    figure.addEventListener("keydown", function (event) {
      var index = current ? byX.indexOf(current) : -1;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        var step = event.key === "ArrowRight" ? 1 : -1;
        index = index < 0 ? (step > 0 ? 0 : byX.length - 1) : Math.min(byX.length - 1, Math.max(0, index + step));
        show(byX[index], true);
      } else if (event.key === "Enter" && current && current.p.href) {
        window.location.href = current.p.href;
      } else if (event.key === "Escape") {
        hide();
      }
    });

    // The zoom note above the chart and the range form below it follow the
    // zoom, and the URL keeps it.
    var section = figure.closest("section");
    var note = figure.previousElementSibling;
    if (!note || !note.classList.contains("zoom-note")) note = null;
    var frontierLink = note && Array.prototype.filter.call(note.querySelectorAll("a"), function (a) {
      return a.textContent.indexOf("Zoom to the frontier") === 0;
    })[0];
    var form = section && section.querySelector("details.zoom-form form");

    function inside() {
      var sx = chart.scales.x, sy = chart.scales.y;
      return fits.filter(function (f) {
        return f.x >= sx.min && f.x <= sx.max && f.y >= sy.min && f.y <= sy.max;
      }).length;
    }

    function describe(zoomed) {
      if (!note) return;
      note.replaceChildren();
      if (zoomed) {
        note.append("Zoomed in: " + inside() + " of " + fits.length + " fits are inside the range. ");
        var reset = document.createElement("button");
        reset.type = "button";
        reset.className = "link-button";
        reset.textContent = "Reset zoom";
        reset.addEventListener("click", function () { chart.resetZoom("none"); });
        note.append(reset);
      } else {
        note.append("Drag across the chart, or hold Ctrl and scroll, to zoom in on an area.");
      }
      if (frontierLink) note.append(" · ", frontierLink);
    }

    function save() {
      var params = new URLSearchParams(window.location.search);
      var zoomed = chart.isZoomedOrPanned();
      var box = {
        x0: chart.scales.x.min, x1: chart.scales.x.max,
        y0: chart.scales.y.min, y1: chart.scales.y.max
      };
      KEYS.forEach(function (k) {
        if (zoomed) params.set(prefix + k, String(Number(box[k].toPrecision(6))));
        else params.delete(prefix + k);
        var input = form && form.querySelector('[name="' + prefix + k + '"]');
        if (input) input.value = zoomed ? String(Number(box[k].toPrecision(6))) : "";
      });
      var query = params.toString();
      window.history.replaceState(null, "", window.location.pathname + (query ? "?" + query : "") + window.location.hash);
      describe(zoomed);
    }

    // A box in the URL: open zoomed to it, so Reset zoom shows every fit.
    var range = spec.range;
    if (range[0] !== null) chart.zoomScale("x", { min: range[0], max: range[1] }, "none");
    if (range[2] !== null) chart.zoomScale("y", { min: range[2], max: range[3] }, "none");
    describe(chart.isZoomedOrPanned());

    dark.addEventListener("change", function () {
      c = palette();
      recolour();
      [chart.options.scales.x, chart.options.scales.y].forEach(function (s) {
        s.title.color = c["ink-2"];
        s.grid.color = c.grid;
        s.border.color = c.axis;
        s.ticks.color = c.muted;
      });
      chart.update("none");
    });
  }

  if (Chart.defaults && document.body) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  }
  document.querySelectorAll("figure.chart").forEach(setup);
})();
