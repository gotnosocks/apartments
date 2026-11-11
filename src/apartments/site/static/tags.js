// Compact inline tagger for table rows carrying `.tag-slot[data-listing]`.
// Loads current tags and vocabulary in one `/tags/for` request, then renders
// each slot's tag chip and `<details>` form (`select`, `note`, `Save`, `Clear`)
// posting with `fetch` so rows can be labeled without leaving the page.
(function () {
  "use strict";

  var BATCH = 300;
  var DIGITS = /^[0-9]{1,32}$/;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function postTag(listingId, code, note) {
    var body = new URLSearchParams();
    body.set("listing_id", listingId);
    body.set("tag", code);
    body.set("note", note || "");
    return fetch("/tags", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
      },
      body: body.toString()
    }).then(function (resp) {
      return resp.json().then(function (data) {
        if (!resp.ok) throw new Error((data && data.error) || "Save failed.");
        return data;
      });
    });
  }

  function renderSlot(slot, listingId, current, groups, byGroup, meanings, syncAll) {
    slot.replaceChildren();
    var wrap = el("div", "tag-widget is-compact");
    var hasActive = Boolean(current && current.tag && current.tag !== "clear");

    if (hasActive) {
      var active = el("div", "tag-active");
      var chip = el(
        "span",
        "chip tag-chip tag-" + (current.group || "unmodeled"),
        current.label || current.tag
      );
      chip.title = current.note || meanings[current.tag] || "";
      active.appendChild(chip);

      var clearBtn = el("button", "tag-clear", "Clear");
      clearBtn.type = "button";
      clearBtn.addEventListener("click", function () {
        clearBtn.disabled = true;
        postTag(listingId, "clear", "").then(
          function () { syncAll(listingId, null); },
          function () { clearBtn.disabled = false; }
        );
      });
      active.appendChild(clearBtn);
      wrap.appendChild(active);
    }

    var details = el("details", "tag-compact");
    details.appendChild(el("summary", "tag-summary", hasActive ? "Edit" : "Tag"));

    var form = el("form", "tag-form");
    form.method = "post";
    form.action = "/tags";

    var select = el("select");
    select.name = "tag";
    select.required = true;
    select.setAttribute("aria-label", "Tag");
    var blank = el("option", null, "Choose tag...");
    blank.value = "";
    select.appendChild(blank);

    groups.forEach(function (g) {
      var items = byGroup[g.code] || [];
      if (!items.length) return;
      var groupEl = document.createElement("optgroup");
      groupEl.label = g.label;
      items.forEach(function (item) {
        var opt = el("option", null, item.label);
        opt.value = item.code;
        opt.title = item.meaning || "";
        if (hasActive && current.tag === item.code) opt.selected = true;
        groupEl.appendChild(opt);
      });
      select.appendChild(groupEl);
    });
    form.appendChild(select);

    var noteInput = el("input");
    noteInput.type = "text";
    noteInput.name = "note";
    noteInput.maxLength = 500;
    noteInput.placeholder = "Optional note";
    noteInput.setAttribute("aria-label", "Note");
    noteInput.value = (hasActive && current.note) || "";
    form.appendChild(noteInput);

    var saveBtn = el("button", null, "Save");
    saveBtn.type = "submit";
    form.appendChild(saveBtn);

    var status = el("span", "tag-status muted");
    status.hidden = true;
    form.appendChild(status);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!select.value) return;
      saveBtn.disabled = true;
      status.hidden = true;
      postTag(listingId, select.value, noteInput.value).then(
        function (saved) {
          syncAll(listingId, saved.tag === "clear" ? null : saved);
        },
        function (err) {
          saveBtn.disabled = false;
          status.textContent = err.message || "Could not save.";
          status.hidden = false;
        }
      );
    });

    details.appendChild(form);
    wrap.appendChild(details);
    slot.appendChild(wrap);
  }

  function init() {
    var nodes = Array.prototype.slice.call(
      document.querySelectorAll(".tag-slot[data-listing]")
    );
    var byId = Object.create(null);
    var ids = [];
    nodes.forEach(function (slot) {
      var id = (slot.getAttribute("data-listing") || "").trim();
      if (!DIGITS.test(id)) return;
      if (!byId[id]) {
        byId[id] = [];
        ids.push(id);
      }
      byId[id].push(slot);
    });
    if (!ids.length) return;

    var chunks = [];
    for (var i = 0; i < ids.length; i += BATCH) {
      chunks.push(ids.slice(i, i + BATCH));
    }

    Promise.all(
      chunks.map(function (chunk) {
        return fetch("/tags/for?ids=" + encodeURIComponent(chunk.join(",")), {
          credentials: "same-origin",
          headers: { "Accept": "application/json" }
        }).then(function (resp) {
          if (!resp.ok) throw new Error("Failed to load tags");
          return resp.json();
        });
      })
    ).then(function (parts) {
      var mergedTags = Object.create(null);
      var vocabulary = [];
      var groups = [];
      parts.forEach(function (part) {
        if (part.vocabulary && !vocabulary.length) vocabulary = part.vocabulary;
        if (part.groups && !groups.length) groups = part.groups;
        var map = part.tags || {};
        Object.keys(map).forEach(function (k) { mergedTags[k] = map[k]; });
      });

      var byGroup = Object.create(null);
      var meanings = Object.create(null);
      vocabulary.forEach(function (item) {
        if (!byGroup[item.group]) byGroup[item.group] = [];
        byGroup[item.group].push(item);
        meanings[item.code] = item.meaning || "";
      });

      function syncAll(listingId, updated) {
        (byId[listingId] || []).forEach(function (slot) {
          renderSlot(slot, listingId, updated, groups, byGroup, meanings, syncAll);
        });
      }

      ids.forEach(function (id) {
        syncAll(id, mergedTags[id] || null);
      });
    }).catch(function () {
      // Leave the server-rendered fallback form intact when fetch fails.
    });
  }

  init();
})();
