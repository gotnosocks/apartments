// Chart hover layer for the listings site. Charts are server-rendered SVG;
// each <figure class="chart"> carries its hover data (positions in viewBox
// units, a title and label/value rows) in a JSON block. Line charts snap a
// crosshair to the nearest x; point charts pick the nearest point. The same
// readout follows the keyboard (arrow keys) when the figure has focus, and
// every value is also in the page's tables, so nothing depends on this.
(function () {
  "use strict";
  var SVG = "http://www.w3.org/2000/svg";
  var HIT = 24; // viewBox units: the nearest point must be this close

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
    var svg = figure.querySelector("svg");
    var tip = figure.querySelector(".chart-tip");
    var block = figure.querySelector("script.chart-data");
    if (!svg || !tip || !block) return;
    var points;
    try {
      points = JSON.parse(block.textContent);
    } catch (error) {
      return;
    }
    if (!points.length) return;
    var kind = figure.getAttribute("data-chart");
    var order = points.slice().sort(function (a, b) { return a.x - b.x; });
    var view = svg.viewBox.baseVal;
    var marker;
    if (kind === "line") {
      marker = document.createElementNS(SVG, "line");
      marker.setAttribute("class", "crosshair");
      marker.setAttribute("y1", 0);
      marker.setAttribute("y2", view.height - 28);
    } else {
      marker = document.createElementNS(SVG, "circle");
      marker.setAttribute("class", "hover-ring");
      marker.setAttribute("r", 7);
    }
    marker.setAttribute("visibility", "hidden");
    svg.appendChild(marker);
    var current = null;

    function show(point) {
      current = point;
      if (kind === "line") {
        marker.setAttribute("x1", point.x);
        marker.setAttribute("x2", point.x);
      } else {
        marker.setAttribute("cx", point.x);
        marker.setAttribute("cy", point.y);
      }
      marker.setAttribute("visibility", "visible");
      readout(tip, point);
      tip.hidden = false;
      // Narrow screens: the card goes under the plot (CSS .below), so a tap
      // never hides the chart. Otherwise it sits beside the point, flipped
      // to the other side near the right or bottom edge, inside the figure.
      var below = figure.clientWidth < 480;
      tip.classList.toggle("below", below);
      if (below) {
        tip.style.left = "";
        tip.style.top = "";
      } else {
        var scale = svg.getBoundingClientRect().width / view.width;
        var px = point.x * scale, py = point.y * scale;
        var left = px + 14;
        if (left + tip.offsetWidth > figure.clientWidth) left = px - tip.offsetWidth - 14;
        var top = py - 10;
        var height = svg.getBoundingClientRect().height;
        if (top + tip.offsetHeight > height) top = py - tip.offsetHeight - 10;
        tip.style.left = Math.max(0, left) + "px";
        tip.style.top = Math.max(0, top) + "px";
      }
      figure.style.cursor = point.href ? "pointer" : "";
    }

    function hide() {
      current = null;
      marker.setAttribute("visibility", "hidden");
      tip.hidden = true;
      figure.style.cursor = "";
    }

    function nearest(event) {
      var matrix = svg.getScreenCTM();
      if (!matrix) return null;
      var p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      var best = null;
      var bestDistance = Infinity;
      points.forEach(function (point) {
        var d = kind === "line" ? Math.abs(point.x - p.x) : Math.hypot(point.x - p.x, point.y - p.y);
        if (d < bestDistance) {
          bestDistance = d;
          best = point;
        }
      });
      return kind === "line" || bestDistance <= HIT ? best : null;
    }

    svg.addEventListener("pointermove", function (event) {
      // No readout while a mouse button is down (dragging a zoom box).
      if (event.buttons && event.pointerType !== "touch") {
        hide();
        return;
      }
      var point = nearest(event);
      if (point) show(point); else hide();
    });
    svg.addEventListener("pointerleave", hide);
    var dragged = brush(figure, svg);
    svg.addEventListener("click", function (event) {
      if (dragged()) return;
      var point = nearest(event);
      if (point && point.href) window.location.href = point.href;
    });
    figure.addEventListener("keydown", function (event) {
      var index = current ? order.indexOf(current) : -1;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        var step = event.key === "ArrowRight" ? 1 : -1;
        index = index < 0 ? (step > 0 ? 0 : order.length - 1) : Math.min(order.length - 1, Math.max(0, index + step));
        show(order[index]);
      } else if (event.key === "Enter" && current && current.href) {
        window.location.href = current.href;
      } else if (event.key === "Escape") {
        hide();
      }
    });
    figure.addEventListener("blur", hide);
  }

  // Drag-to-zoom on a chart marked data-zoom (its query-parameter prefix):
  // a mouse or pen drag draws a box, and letting go loads the page with the
  // chart zoomed to it (prefix + x0, x1, y0, y1; the server draws the
  // zoomed chart). data-frame maps viewBox units to data values. Touch keeps
  // scrolling the page; the "Set the range" form works everywhere. Returns
  // a function that says whether the last press was a drag, so it is not
  // also taken as a click on a fit.
  function brush(figure, svg) {
    var prefix = figure.getAttribute("data-zoom");
    var frame;
    try {
      frame = JSON.parse(figure.getAttribute("data-frame") || "null");
    } catch (error) {
      frame = null;
    }
    var wasDrag = false;
    if (!prefix || !frame) return function () { return false; };
    var x0 = frame[0], x1 = frame[1], y0 = frame[2], y1 = frame[3];
    var left = frame[4], right = frame[5], top = frame[6], bottom = frame[7];
    var start = null;
    var box = null;

    function local(event) {
      var matrix = svg.getScreenCTM();
      if (!matrix) return null;
      var p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      return {
        x: Math.min(right, Math.max(left, p.x)),
        y: Math.min(bottom, Math.max(top, p.y))
      };
    }

    function value(p) {
      return {
        x: x0 + (p.x - left) / (right - left) * (x1 - x0),
        y: y1 - (p.y - top) / (bottom - top) * (y1 - y0)
      };
    }

    svg.addEventListener("pointerdown", function (event) {
      if (event.pointerType === "touch" || event.button !== 0) return;
      start = local(event);
      wasDrag = false;
      if (!start) return;
      svg.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    svg.addEventListener("pointermove", function (event) {
      if (!start) return;
      var p = local(event);
      if (!p) return;
      if (!box) {
        box = document.createElementNS(SVG, "rect");
        box.setAttribute("class", "brush");
        svg.appendChild(box);
      }
      box.setAttribute("x", Math.min(start.x, p.x));
      box.setAttribute("y", Math.min(start.y, p.y));
      box.setAttribute("width", Math.abs(p.x - start.x));
      box.setAttribute("height", Math.abs(p.y - start.y));
    });
    function finish(event) {
      if (!start) return;
      var p = event.type === "pointerup" ? local(event) : null;
      var from = start;
      start = null;
      if (box) {
        box.remove();
        box = null;
      }
      // Smaller than this (viewBox units) either way is a click, not a box.
      if (!p || Math.abs(p.x - from.x) < 6 || Math.abs(p.y - from.y) < 6) return;
      wasDrag = true;
      var a = value(from), b = value(p);
      var params = new URLSearchParams(window.location.search);
      var zoom = {
        x0: Math.max(0, Math.min(a.x, b.x)), x1: Math.max(a.x, b.x),
        y0: Math.min(a.y, b.y), y1: Math.max(a.y, b.y)
      };
      Object.keys(zoom).forEach(function (k) {
        params.set(prefix + k, String(Number(zoom[k].toPrecision(6))));
      });
      window.location.href = "?" + params.toString() + "#" + figure.closest("section").id;
    }
    svg.addEventListener("pointerup", finish);
    svg.addEventListener("pointercancel", finish);
    return function () {
      var was = wasDrag;
      wasDrag = false;
      return was;
    };
  }

  document.querySelectorAll("figure.chart").forEach(setup);
})();

// A submitted form says it is working: the estimate and the building search
// take a moment, and without this the button looks dead (playtest round 3).
// The page still works without it. Back/forward restores the button, and so
// does a timer: a resubmit to the same URL with a #fragment (the estimate
// form's) only scrolls, and no new page comes to replace this one.
(function () {
  "use strict";
  document.querySelectorAll("form[method=get]").forEach(function (form) {
    var button = form.querySelector("button[type=submit]");
    if (!button) return;
    var label = button.textContent;
    var timer;
    function restore() {
      clearTimeout(timer);
      button.textContent = label;
      button.removeAttribute("aria-busy");
      form.removeAttribute("aria-busy");
    }
    form.addEventListener("submit", function () {
      button.textContent = "Working…";
      button.setAttribute("aria-busy", "true");
      form.setAttribute("aria-busy", "true");
      timer = setTimeout(restore, 10000);
    });
    window.addEventListener("pageshow", restore);
  });
})();

// Building suggestions for a search box marked data-suggest (its value is the
// /buildings.json URL), shown as a native datalist so keyboards and screen
// readers get the browser's own list. With data-suggest-id, picking a
// suggestion also sets a hidden input of that name to the building's id, so
// a shared address still goes to the building chosen (two buildings with the
// same name or address get no id). Typing on works as before.
(function () {
  "use strict";
  document.querySelectorAll("input[data-suggest]").forEach(function (input) {
    var list = document.createElement("datalist");
    list.id = input.id + "-suggestions";
    input.after(list);
    input.setAttribute("list", list.id);
    // value -> building id; null when two buildings share the value, so the
    // text falls through to the server's list of matches.
    var ids = new Map();
    var hidden = null;
    var idName = input.getAttribute("data-suggest-id");
    if (idName) {
      hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = idName;
      hidden.disabled = true;
      input.after(hidden);
    }
    var timer = null;
    var asked = "";
    function pick() {
      if (!hidden) return;
      var id = ids.get(input.value);
      hidden.disabled = !id;
      hidden.value = id || "";
    }
    function fetchSuggestions() {
      var q = input.value.trim();
      if (q.length < 2 || q === asked) return;
      asked = q;
      fetch(input.getAttribute("data-suggest") + "?q=" + encodeURIComponent(q))
        .then(function (response) { return response.ok ? response.json() : []; })
        .then(function (rows) {
          if (q !== asked) return;
          list.replaceChildren();
          rows.forEach(function (row) {
            var known = ids.get(row.value);
            ids.set(row.value, known === undefined || known === row.id ? row.id : null);
            var option = document.createElement("option");
            option.value = row.value;
            option.label = row.label;
            list.appendChild(option);
          });
          pick();
        })
        .catch(function () {});
    }
    input.addEventListener("input", function () {
      pick();
      clearTimeout(timer);
      timer = setTimeout(fetchSuggestions, 150);
    });
  });
})();
