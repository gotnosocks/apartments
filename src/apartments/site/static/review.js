// Review cards: keyboard shortcuts on a laptop, a full-screen photo viewer, and one
// submit per tap. The pages work without this script.
(function () {
  "use strict";
  var form = document.querySelector(".rv-answer");

  // One answer per tap: a second tap while the page loads would answer the next card.
  if (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.sent) {
        event.preventDefault();
        return;
      }
      form.dataset.sent = "1";
      var button = event.submitter;
      if (button) button.setAttribute("aria-busy", "true");
    });
  }

  function typing(target) {
    var tag = target && target.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (target && target.isContentEditable);
  }

  // Photo viewer: tap a thumbnail to see it full screen; swipe or arrow keys move along
  // the ad's strip; tap outside, Escape or the close button shut it.
  var box = null, strip = [], at = 0, startX = null;
  function build() {
    box = document.createElement("div");
    box.className = "rv-lightbox";
    box.hidden = true;
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", "Photo");
    var img = document.createElement("img");
    img.alt = "";
    var close = document.createElement("button");
    close.className = "rv-lb-close"; close.type = "button"; close.textContent = "×";
    close.setAttribute("aria-label", "Close");
    var prev = document.createElement("button");
    prev.className = "rv-lb-prev"; prev.type = "button"; prev.textContent = "‹";
    prev.setAttribute("aria-label", "Previous photo");
    var next = document.createElement("button");
    next.className = "rv-lb-next"; next.type = "button"; next.textContent = "›";
    next.setAttribute("aria-label", "Next photo");
    box.append(img, close, prev, next);
    document.body.appendChild(box);
    close.addEventListener("click", hide);
    prev.addEventListener("click", function (e) { e.stopPropagation(); show(at - 1); });
    next.addEventListener("click", function (e) { e.stopPropagation(); show(at + 1); });
    box.addEventListener("click", function (e) { if (e.target === box) hide(); });
    box.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; }, { passive: true });
    box.addEventListener("touchend", function (e) {
      if (startX === null) return;
      var dx = e.changedTouches[0].clientX - startX;
      startX = null;
      if (Math.abs(dx) > 40) show(at + (dx < 0 ? 1 : -1));
    });
  }
  function show(i) {
    if (!strip.length) return;
    at = (i + strip.length) % strip.length;
    box.querySelector("img").src = strip[at].href;
    box.hidden = false;
  }
  function hide() { if (box) { box.hidden = true; box.querySelector("img").removeAttribute("src"); } }

  // "Something else wrong?" at the top opens the panel it points to.
  document.addEventListener("click", function (event) {
    var jump = event.target.closest && event.target.closest('a[href="#rv-problem"]');
    if (jump) {
      var panel = document.getElementById("rv-problem");
      if (panel) panel.open = true;
    }
  });

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a.rv-photo");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    if (!box) build();
    strip = Array.prototype.slice.call(link.parentNode.querySelectorAll("a.rv-photo"));
    show(strip.indexOf(link));
  });

  document.addEventListener("keydown", function (event) {
    if (box && !box.hidden) {
      if (event.key === "Escape") hide();
      else if (event.key === "ArrowRight") show(at + 1);
      else if (event.key === "ArrowLeft") show(at - 1);
      else return;
      event.preventDefault();
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey || typing(event.target)) return;
    if (event.key === "z") {
      var undo = document.querySelector(".rv-toast .rv-undo");
      if (undo) { event.preventDefault(); undo.click(); }
      return;
    }
    if (!form) return;
    var button = form.querySelector('[data-key="' + event.key.toLowerCase() + '"]');
    if (button) {
      event.preventDefault();
      button.click();
    }
  });
})();
