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
      var scale = svg.getBoundingClientRect().width / view.width;
      var left = point.x * scale + 14;
      var top = point.y * scale - 10;
      if (left + tip.offsetWidth > figure.clientWidth) {
        left = point.x * scale - tip.offsetWidth - 14;
      }
      tip.style.left = Math.max(0, left) + "px";
      tip.style.top = Math.max(0, top) + "px";
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
