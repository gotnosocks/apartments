// Chart hover layer for the listings site. Charts are server-rendered SVG;
// each <figure class="chart"> carries its hover data (positions in viewBox
// units, a title and label/value rows) in a JSON block. Line charts snap a
// crosshair to the nearest x; point charts pick the nearest point. The same
// readout follows the keyboard (arrow keys) when the figure has focus, and
// every value is also in the page's tables, so nothing depends on this.
// The zoomable fit charts are drawn by fitchart.js (Chart.js) instead.
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
    // Drawn by fitchart.js (Chart.js) instead.
    if (figure.hasAttribute("data-enhanced")) return;
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
      var point = nearest(event);
      if (point) show(point); else hide();
    });
    svg.addEventListener("pointerleave", hide);
    svg.addEventListener("click", function (event) {
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

// The story's animated figures play when scrolled into view, with a replay
// button. Without script they play once on load (static/site.css); with it,
// a figure on screen at load plays at once and one further down stays whole
// until it nears view.
(function () {
  var figures = document.querySelectorAll(".story-figure[data-play]");
  if (!figures.length || !("IntersectionObserver" in window)) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  // Play once the figure's top reaches the upper two thirds of the screen. A
  // share-of-the-figure threshold never fires for a figure taller than the
  // screen, which then stays blank.
  var seen = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("play");
      seen.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -35% 0px", threshold: 0 });
  // A figure stays whole until it comes within a quarter screen of view, so
  // print, find-in-page and full-page screenshots never catch it blank.
  var near = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.remove("whole");
      entry.target.classList.add("armed");
      near.unobserve(entry.target);
      seen.observe(entry.target);
    });
  }, { rootMargin: "0px 0px 25% 0px", threshold: 0 });
  figures.forEach(function (figure) {
    // Play the ones on screen at load now, and arm those just below it,
    // before the first paint.
    var box = figure.getBoundingClientRect();
    if (box.bottom > 0 && box.top < window.innerHeight) {
      figure.classList.add("armed", "play");
    } else if (box.bottom > 0 && box.top < window.innerHeight * 1.25) {
      figure.classList.add("armed");
      seen.observe(figure);
    } else {
      figure.classList.add("whole");
      near.observe(figure);
    }
    var button = document.createElement("button");
    button.type = "button";
    button.className = "replay";
    button.textContent = "Replay";
    button.addEventListener("click", function () {
      figure.classList.add("reset");
      void figure.offsetWidth; // restart the CSS animations
      figure.classList.remove("reset", "whole");
      figure.classList.add("armed", "play");
    });
    figure.appendChild(button);
  });
})();
