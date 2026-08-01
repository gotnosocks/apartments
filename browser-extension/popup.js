const nodes = {
  chooseDirectory: document.getElementById("chooseDirectory"),
  directory: document.getElementById("directory"),
  collect: document.getElementById("collect"),
  export: document.getElementById("export"),
  next: document.getElementById("next"),
  markPending: document.getElementById("markPending"),
  clear: document.getElementById("clear"),
  restoreBad: document.getElementById("restoreBad"),
  status: document.getElementById("status"),
  summary: document.getElementById("summary"),
  queue: document.getElementById("queue")
};

let activeTab;
let activePage;
let queue;
let captureDirectory;

const HANDLE_DB = "streeteasy-capture-settings";

function openHandleDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(HANDLE_DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("settings");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function storeDirectoryHandle(handle) {
  const database = await openHandleDatabase();
  await new Promise((resolve, reject) => {
    const transaction = database.transaction("settings", "readwrite");
    transaction.objectStore("settings").put(handle, "captureDirectory");
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

async function loadDirectoryHandle() {
  const database = await openHandleDatabase();
  const handle = await new Promise((resolve, reject) => {
    const request = database.transaction("settings").objectStore("settings").get("captureDirectory");
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
  database.close();
  return handle;
}

async function canWrite(handle, request = false) {
  if (!handle) return false;
  if ((await handle.queryPermission({mode: "readwrite"})) === "granted") return true;
  return request && (await handle.requestPermission({mode: "readwrite"})) === "granted";
}

async function childDirectory(root, names) {
  let current = root;
  for (const name of names) current = await current.getDirectoryHandle(name, {create: true});
  return current;
}

async function writeFile(directory, name, contents) {
  const handle = await directory.getFileHandle(name, {create: true});
  const writer = await handle.createWritable();
  await writer.write(contents);
  await writer.close();
}

async function sha256(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function assetExtension(url, contentType) {
  const match = new URL(url).pathname.match(/\.([a-z0-9]{2,5})$/i);
  if (match) return match[1].toLowerCase();
  const types = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"};
  return types[(contentType || "").split(";")[0]] || "bin";
}

async function writeCaptureBundle(bundle, onProgress = () => {}) {
  if (!(await canWrite(captureDirectory, true))) throw new Error("Capture-directory permission was not granted.");
  const data = bundle.structured;
  const timestamp = data.captured_at.replace(/[:.]/g, "-");
  const unit = data.unit.replace(/[^a-z0-9_-]/gi, "-");
  const directory = await childDirectory(captureDirectory, ["streeteasy", data.building_slug, unit, timestamp]);
  await writeFile(directory, "structured.json", JSON.stringify(data, null, 2));
  await writeFile(directory, "page.html", bundle.page_html);

  const assetDirectory = await directory.getDirectoryHandle("assets", {create: true});
  const counters = {};
  const plans = bundle.assets.map((asset) => {
    const category = asset.category || "other";
    counters[category] = (counters[category] || 0) + 1;
    return {asset, category, number: counters[category]};
  });
  const assets = new Array(plans.length);
  let nextAsset = 0;
  let completedAssets = 0;
  onProgress(0, plans.length);
  const worker = async () => {
    while (true) {
      const index = nextAsset++;
      if (index >= plans.length) return;
      const {asset, category, number} = plans[index];
      const record = {...asset};
      try {
        const response = await fetch(asset.url, {credentials: "omit"});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const bytes = await response.arrayBuffer();
        const extension = assetExtension(asset.url, response.headers.get("content-type"));
        const filename = `${category}-${String(number).padStart(3, "0")}.${extension}`;
        await writeFile(assetDirectory, filename, bytes);
        record.local_file = `assets/${filename}`;
        record.bytes = bytes.byteLength;
        record.sha256 = await sha256(bytes);
      } catch (error) {
        record.error = error.message || String(error);
      }
      assets[index] = record;
      completedAssets += 1;
      onProgress(completedAssets, plans.length);
    }
  };
  await Promise.all(Array.from({length: Math.min(4, plans.length)}, worker));
  await writeFile(directory, "assets.json", JSON.stringify(assets, null, 2));
  const manifest = {
    capture_schema_version: 1,
    extension_version: chrome.runtime.getManifest().version,
    captured_at: data.captured_at,
    source: "streeteasy",
    source_url: data.canonical_url,
    source_listing_id: data.source_listing_id,
    files: ["structured.json", "page.html", "assets.json"],
    asset_count: assets.length,
    asset_errors: assets.filter((asset) => asset.error).length
  };
  await writeFile(directory, "manifest.json", JSON.stringify(manifest, null, 2));
  return {relativePath: `streeteasy/${data.building_slug}/${unit}/${timestamp}`, manifest};
}

function setStatus(message, kind = "") {
  nodes.status.textContent = message;
  nodes.status.className = kind;
}

function pageIdentity(url) {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    const isStreetEasy = parsed.hostname === "streeteasy.com" || parsed.hostname.endsWith(".streeteasy.com");
    const isBuilding = isStreetEasy && parts[0] === "building" && parts.length >= 2;
    const isRentalListing = isStreetEasy && parts[0] === "rental" && parts.length === 2;
    return {
      isStreetEasy,
      isBuilding,
      isRentalListing,
      isUnit: (isBuilding && parts.length === 3) || isRentalListing,
      buildingSlug: isBuilding ? parts[1] : null,
      unit: isBuilding && parts.length === 3 ? decodeURIComponent(parts[2]).toUpperCase() : null,
      sourceId: isBuilding && parts.length === 3 ? `${parts[1]}/${decodeURIComponent(parts[2]).toLowerCase()}` : null
    };
  } catch (_) {
    return {isStreetEasy: false, isBuilding: false, isUnit: false};
  }
}

async function loadQueue() {
  const stored = await chrome.storage.local.get("unitQueue");
  return stored.unitQueue || null;
}

async function saveQueue(value) {
  queue = value;
  await chrome.storage.local.set({unitQueue: value});
  renderQueue();
}

function sortedUnits() {
  return [...(queue?.units || [])].sort((a, b) =>
    a.unit.localeCompare(b.unit, undefined, {numeric: true, sensitivity: "base"})
  );
}

function nextPending(excludingSourceId = null) {
  return sortedUnits().find((item) => item.status !== "done" && item.source_id !== excludingSourceId);
}

async function openUnit(item) {
  if (!item) {
    setStatus("No pending units remain.", "success");
    return;
  }
  await chrome.tabs.update(activeTab.id, {url: item.url});
  setStatus(`Opening unit ${item.unit}…`);
}

async function markUnitBad(item) {
  if (!queue) return;
  const ignored = new Set(queue.ignored_units || []);
  ignored.add(item.source_id);
  await saveQueue({
    ...queue,
    ignored_units: [...ignored],
    units: queue.units.filter((candidate) => candidate.source_id !== item.source_id),
    updated_at: new Date().toISOString()
  });
  setStatus(`Removed unit ${item.unit} and marked it bad.`, "success");
}

function renderQueue() {
  nodes.queue.replaceChildren();
  const units = sortedUnits();
  const completed = units.filter((item) => item.status === "done").length;
  const ignored = queue?.ignored_units?.length || 0;
  nodes.summary.textContent = queue
    ? `${queue.building_slug}: ${completed}/${units.length} complete${ignored ? ` · ${ignored} bad` : ""}`
    : "No queue";
  nodes.next.disabled = !nextPending();
  nodes.clear.disabled = !queue;
  nodes.restoreBad.disabled = !ignored;

  if (!units.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No units collected yet.";
    nodes.queue.append(empty);
    return;
  }

  for (const item of units) {
    const row = document.createElement("div");
    row.className = `unit ${item.status === "done" ? "done" : ""}`;
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = item.status === "done" ? "✓" : item.status === "capturing" ? "…" : item.status === "error" ? "!" : "○";
    const label = document.createElement("span");
    const stateLabel = item.status === "capturing" ? " · capturing" : item.status === "error" ? " · capture failed" : "";
    label.textContent = `Unit ${item.unit}${item.history_rows != null ? ` · ${item.history_rows} events` : ""}${stateLabel}`;
    const actions = document.createElement("div");
    actions.className = "unitActions";
    const open = document.createElement("button");
    open.textContent = "Open";
    open.addEventListener("click", () => openUnit(item));
    const bad = document.createElement("button");
    bad.className = "bad";
    bad.textContent = "Bad";
    bad.title = "Remove this non-unit or invalid unit from the queue";
    bad.addEventListener("click", () => markUnitBad(item));
    actions.append(open, bad);
    row.append(mark, label, actions);
    nodes.queue.append(row);
  }
}

async function collectUnitsFromPage() {
  const parts = location.pathname.split("/").filter(Boolean);
  if (location.hostname !== "streeteasy.com" && !location.hostname.endsWith(".streeteasy.com")) {
    throw new Error("Open a StreetEasy building page first.");
  }
  if (parts[0] !== "building" || !parts[1]) {
    throw new Error("This is not a StreetEasy building page.");
  }
  const buildingSlug = parts[1];
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();

  // StreetEasy normally reveals unavailable units in-place. Open that view
  // before scanning so collection remains one user-initiated extension action.
  const unavailableTrigger = [...document.querySelectorAll("a, button")].find((element) =>
    /^(?:view|show).*unavailable units/i.test(clean(element.textContent))
  );
  let openedUnavailableView = false;
  if (unavailableTrigger) {
    const rowsBefore = document.querySelectorAll("tr").length;
    unavailableTrigger.click();
    openedUnavailableView = true;
    const deadline = Date.now() + 3500;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 150));
      const triggerGone = !document.contains(unavailableTrigger) || unavailableTrigger.getAttribute("aria-expanded") === "true";
      const rowsAdded = document.querySelectorAll("tr").length > rowsBefore;
      if (triggerGone || rowsAdded || document.querySelector('[role="dialog"], [aria-modal="true"]')) break;
    }
  }

  const reserved = new Set([
    "available", "unavailable", "units", "rentals", "sales", "documents",
    "floorplans", "for-rent", "for-sale", "past-listings", "media_gallery",
    "media-gallery", "photos", "map"
  ]);
  const found = new Map();
  const ignoredGeneric = new Set();
  const isGenericLayout = (value) => {
    const compact = clean(value).replace(/^#\s*/, "").replace(/[ _]/g, "-").toUpperCase();
    return /^\d+(?:BD|BR|BED|BEDROOM)S?[-/]?\d+(?:BA|BATH|BATHROOM)S?$/.test(compact)
      || /^\d+-?(?:BD|BR|BED|BEDROOM)S?$/.test(compact);
  };
  const validUnit = (value) => {
    const unit = clean(value).replace(/^#\s*/, "").toUpperCase();
    if (isGenericLayout(unit)) {
      ignoredGeneric.add(unit);
      return null;
    }
    const isNumberedUnit = /\d/.test(unit) && /^[0-9A-Z][0-9A-Z-]{0,9}$/.test(unit);
    const isPenthouse = /^PH[A-Z0-9-]*$/.test(unit);
    return (isNumberedUnit || isPenthouse) && !reserved.has(unit.toLowerCase()) ? unit : null;
  };
  const addUnit = (candidate, linkText = null, explicitUrl = null, discoveredFrom = "label") => {
    let unit = validUnit(candidate);
    if (!unit) return;
    // Treat 3-K and 3K as the same displayed unit while preserving the source URL.
    unit = unit.replace(/^(\d+)-([A-Z]+)$/, "$1$2");
    const segment = unit.toLowerCase();
    const sourceId = `${buildingSlug}/${segment}`;
    const previous = found.get(sourceId);
    found.set(sourceId, {
      source_id: sourceId,
      unit,
      url: explicitUrl || previous?.url || `${location.origin}/building/${buildingSlug}/${encodeURIComponent(segment)}`,
      link_text: clean(linkText) || previous?.link_text || null,
      discovered_from: explicitUrl ? discoveredFrom : previous?.discovered_from || discoveredFrom,
      has_actual_link: Boolean(explicitUrl || previous?.has_actual_link)
    });
  };

  // Available units generally have canonical anchors.
  for (const anchor of document.querySelectorAll("a[href]")) {
    let url;
    try { url = new URL(anchor.href, location.href); } catch (_) { continue; }
    if (url.hostname !== location.hostname) continue;
    const path = url.pathname.split("/").filter(Boolean);
    let segment = null;
    if (path[0] === "building" && path[1] === buildingSlug) {
      segment = path.length === 3 ? decodeURIComponent(path[2]) : null;
      if (path.length === 4 && ["unit", "units"].includes(path[2].toLowerCase())) {
        segment = decodeURIComponent(path[3]);
      }
    }
    if (segment && !reserved.has(segment.toLowerCase())) {
      addUnit(segment, anchor.textContent, url.href, "link");
      continue;
    }
    // Unavailable rows may link to /rental/<id> rather than a canonical unit page.
    const label = clean(anchor.textContent).replace(/^#\s*/, "");
    if (/^(?:\d+[A-Z]+|PH[A-Z0-9-]*)$/i.test(label)) addUnit(label, anchor.textContent, url.href, "row-link");
  }

  // The unavailable-unit dialog renders labels rather than links. Capture
  // explicit “#3B”, “Unit 3B”, and “Apartment 3B” text anywhere in the view.
  const pageText = clean(document.body.innerText);
  for (const pattern of [/#\s*((?:[0-9]+|PH)[A-Z0-9-]*)\b/gi, /\b(?:unit|apartment)\s+#?\s*((?:[0-9]+|PH)[A-Z0-9-]*)\b/gi]) {
    for (const match of pageText.matchAll(pattern)) addUnit(match[1], match[0], null, "text");
  }

  // Also inspect the first cell of unavailable-unit tables. This supports
  // numeric-only unit names, which are unsafe to infer from general page text.
  for (const row of document.querySelectorAll("tr")) {
    const firstCell = row.querySelector("th, td");
    const value = clean(firstCell?.textContent);
    const anchor = firstCell?.querySelector("a[href]") || row.querySelector("a[href]");
    let actualUrl = null;
    try {
      const parsed = anchor ? new URL(anchor.href, location.href) : null;
      if (parsed && parsed.hostname === location.hostname) actualUrl = parsed.href;
    } catch (_) { /* Keep the constructed fallback. */ }
    if (/^#?\s*(?:[0-9]+[A-Z0-9-]*|PH[A-Z0-9-]*)$/i.test(value)) {
      addUnit(value, row.textContent, actualUrl, actualUrl ? "table-link" : "table");
    }
  }

  // Some modal implementations expose the unit only through accessibility or
  // data attributes. Restrict these candidates to attributes mentioning unit.
  for (const element of document.querySelectorAll("[aria-label], [data-unit], [data-unit-number], [data-testid]")) {
    for (const attribute of element.attributes) {
      if (/^data-unit(?:-number)?$/i.test(attribute.name)) {
        addUnit(attribute.value, attribute.value, null, "attribute");
        continue;
      }
      if (!/\b(?:unit|apartment)\b/i.test(attribute.value)) continue;
      const match = attribute.value.match(/(?:unit|apartment)[^0-9A-Z#]*#?\s*((?:[0-9]+|PH)[A-Z0-9-]*)\b/i);
      if (match) addUnit(match[1], attribute.value, null, "attribute");
    }
  }

  return {
    building_slug: buildingSlug,
    building_url: `${location.origin}/building/${buildingSlug}`,
    page_url: location.href,
    opened_unavailable_view: openedUnavailableView,
    ignored_generic_layouts: [...ignoredGeneric],
    units: [...found.values()]
  };
}

async function collectStreetEasyListing() {
  if (location.hostname !== "streeteasy.com" && !location.hostname.endsWith(".streeteasy.com")) {
    throw new Error("Open a StreetEasy unit page first.");
  }
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();
  const text = (selector, root = document) => clean(root.querySelector(selector)?.textContent);
  const money = (value) => {
    const match = clean(value).match(/\$([\d,]+)/);
    return match ? Number(match[1].replaceAll(",", "")) : null;
  };
  const numberFrom = (value, expression) => {
    const match = clean(value).match(expression);
    return match ? Number(match[1].replaceAll(",", "")) : null;
  };

  const canonicalUrl = document.querySelector('link[rel="canonical"]')?.href || location.href.split("?")[0];
  const canonicalPath = new URL(canonicalUrl).pathname.split("/").filter(Boolean);
  const buildingHref = document.querySelector('[data-testid="addressLink"]')?.href
    || document.querySelector('a[href^="/building/"]')?.href;
  let buildingPath = [];
  try { buildingPath = new URL(buildingHref, location.href).pathname.split("/").filter(Boolean); } catch (_) { /* handled below */ }
  const buildingSlug = canonicalPath[0] === "building" && canonicalPath[1]
    ? canonicalPath[1]
    : buildingPath[0] === "building" ? buildingPath[1] : null;
  if (!buildingSlug) throw new Error("Could not identify the building for this listing page.");
  const rentalPath = location.pathname.split("/").filter(Boolean);
  const streetEasyRentalId = canonicalPath[0] === "rental" ? canonicalPath[1]
    : rentalPath[0] === "rental" ? rentalPath[1] : null;
  const historyBox = document.querySelector('[data-testid="priceHistoryTable"]');
  if (!historyBox) throw new Error("No price-history table was found on this unit page.");

  const initialRows = historyBox.querySelectorAll("tbody tr").length;
  const showMore = [...historyBox.querySelectorAll("button")]
    .find((button) => /^show more$/i.test(clean(button.textContent)));
  if (showMore) {
    showMore.click();
    const deadline = Date.now() + 3000;
    while (Date.now() < deadline && historyBox.querySelectorAll("tbody tr").length <= initialRows) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }

  const history = [...historyBox.querySelectorAll("tbody tr")].map((row) => {
    const cells = [...row.querySelectorAll("td")];
    const link = cells[2]?.querySelector("a[href]");
    return {
      date: clean(cells[0]?.textContent),
      base_rent: money(cells[1]?.textContent),
      event: clean(cells[2]?.textContent),
      listing_url: link?.href || null
    };
  }).filter((row) => row.date || row.event);

  const addressWithUnit = text('[data-testid="address"]');
  const unitMatch = addressWithUnit.match(/#\s*(.+)$/);
  const fallbackUnit = canonicalPath[0] === "building" && canonicalPath[2]
    ? decodeURIComponent(canonicalPath[2]).toUpperCase()
    : null;
  const fullUnit = unitMatch ? clean(unitMatch[1]) : fallbackUnit;
  if (!fullUnit) throw new Error("Could not identify the unit on this listing page.");
  const compactUnit = fullUnit.replace(/[ _]/g, "-").toUpperCase();
  const isGenericLayout = /^\d+(?:BD|BR|BED|BEDROOM)S?[-/]?\d+(?:BA|BATH|BATHROOM)S?$/.test(compactUnit)
    || /^\d+-?(?:BD|BR|BED|BEDROOM)S?$/.test(compactUnit);
  const penthouseParts = isGenericLayout ? null : fullUnit.match(/^PH([A-Z0-9-]*)$/i);
  const floorLetterParts = isGenericLayout ? null : fullUnit.match(/^(\d{1,2})\s*[- ]?\s*([A-Z]+)$/i);
  const numericParts = isGenericLayout ? null : fullUnit.match(/^(\d)(\d*)$/);
  const floor = floorLetterParts
    ? Number(floorLetterParts[1])
    : numericParts ? Number(numericParts[1]) : null;
  const penthouseSuffix = penthouseParts?.[1] ? clean(penthouseParts[1]).toUpperCase() : null;
  const unitLetter = floorLetterParts
    ? clean(floorLetterParts[2]).toUpperCase()
    : penthouseSuffix && /^[A-Z]+$/.test(penthouseSuffix) ? penthouseSuffix : null;
  const unitSuffix = floorLetterParts ? unitLetter : penthouseParts ? penthouseSuffix : numericParts?.[2] || null;
  const unitFormat = penthouseParts ? "penthouse" : floorLetterParts ? "floor-letter" : numericParts ? "numeric" : "other";
  const floorInference = floorLetterParts
    ? "parsed-floor-letter"
    : numericParts ? "heuristic-first-digit" : null;
  const address = clean(addressWithUnit.replace(/\s*#\s*.+$/, ""));
  const details = [...document.querySelectorAll('[data-testid="propertyDetails"] p')]
    .map((node) => clean(node.textContent));
  const detailText = details.join(" | ");
  const bedrooms = /\bStudio\b/i.test(detailText) ? 0 : numberFrom(detailText, /([\d.]+)\s*(?:bed|bedroom)/i);
  const specs = {};
  document.querySelectorAll('[data-testid^="rentalListingSpec-"]').forEach((node) => {
    const values = [...node.querySelectorAll("p")].map((part) => clean(part.textContent));
    if (values.length >= 2) specs[values[0].toLowerCase()] = values.slice(1).join(" ");
  });
  const listItems = (selector) => [...document.querySelectorAll(`${selector} li`)]
    .map((node) => clean(node.textContent)).filter(Boolean);
  const buildingAddress = text('[data-testid="about-building-section"] p');
  const zipMatch = buildingAddress.match(/\b(\d{5})(?:-\d{4})?\b/);

  // Trigger lazy content before preserving the rendered DOM.
  const originalScrollY = window.scrollY;
  for (const section of document.querySelectorAll('[data-testid="media-section"], [data-testid="property-history-section"]')) {
    section.scrollIntoView({block: "center"});
    await new Promise((resolve) => setTimeout(resolve, 75));
  }
  const floorPlanUrls = new Set();
  const floorPlanButton = document.querySelector('[data-testid="floorplan-sticky-button"]');
  if (floorPlanButton) {
    floorPlanButton.click();
    await new Promise((resolve) => setTimeout(resolve, 600));
    for (const image of document.querySelectorAll('[role="dialog"] img, [aria-modal="true"] img, .swiper-slide-active img')) {
      if (image.currentSrc || image.src) floorPlanUrls.add(image.currentSrc || image.src);
    }
  }
  window.scrollTo(0, originalScrollY);

  const structured = {
    schema_version: 3,
    source: "streeteasy",
    captured_at: new Date().toISOString(),
    canonical_url: canonicalUrl,
    source_listing_id: `${buildingSlug}/${fullUnit.replace(/^(\d+)-([A-Z]+)$/i, "$1$2").toLowerCase()}`,
    street_easy_rental_id: streetEasyRentalId,
    building_slug: buildingSlug,
    unit: fullUnit,
    floor,
    unit_letter: unitLetter,
    unit_suffix: unitSuffix,
    unit_format: unitFormat,
    floor_inference: floorInference,
    unit_kind: isGenericLayout ? "generic-layout" : "physical-unit",
    unit_is_specific: !isGenericLayout,
    address,
    building_address: buildingAddress || null,
    zipcode: zipMatch ? zipMatch[1] : null,
    asking_rent: money(text('[data-testid="priceInfo"]')),
    status: text('[data-testid="priceInfo"] h6') || null,
    days_on_market: numberFrom(specs["days on market"], /(\d+)/),
    availability: specs.available || null,
    last_price_change: specs["last price change"] || null,
    attributes: {
      square_feet: numberFrom(detailText, /([\d,]+)\s*ft²/i),
      bedrooms,
      bathrooms: numberFrom(detailText, /([\d.]+)\s*bath/i),
      rooms: numberFrom(detailText, /([\d.]+)\s*room/i),
      displayed_details: details
    },
    policies: (() => {
      const section = [...document.querySelectorAll("section")]
        .find((candidate) => text("h2", candidate) === "Policies");
      return section ? [...section.querySelectorAll("li")].map((node) => clean(node.textContent)).filter(Boolean) : [];
    })(),
    home_features: listItems('[data-testid="home-features-section"]'),
    building_amenities: listItems('[data-testid="building-amenities-section"]'),
    description: text('[data-testid="about-section"]'),
    price_history: history
  };

  const bestImageUrl = (image) => {
    const candidates = (image.getAttribute("srcset") || "").split(",").map((candidate) => {
      const parts = candidate.trim().split(/\s+/);
      return {url: parts[0], size: Number((parts[1] || "0").replace(/[^0-9.]/g, "")) || 0};
    }).filter((candidate) => candidate.url);
    candidates.sort((a, b) => b.size - a.size);
    const value = candidates[0]?.url || image.currentSrc || image.src;
    try { return value ? new URL(value, location.href).href : null; } catch (_) { return null; }
  };
  const assetsByUrl = new Map();
  const addAsset = (url, category, metadata = {}) => {
    if (!url || /^data:/.test(url) || /maps\.googleapis\.com/.test(url)) return;
    const previous = assetsByUrl.get(url);
    const priority = {"floor-plan": 3, "past-listing-photo": 2, "listing-photo": 1};
    if (!previous || (priority[category] || 0) > (priority[previous.category] || 0)) {
      assetsByUrl.set(url, {url, category, ...metadata});
    }
  };
  for (const image of document.querySelectorAll("img")) {
    const url = bestImageUrl(image);
    const alt = clean(image.alt);
    const isFloorPlan = floorPlanUrls.has(image.currentSrc || image.src)
      || floorPlanUrls.has(url)
      || /floor\s*plan/i.test(alt);
    const isPast = Boolean(image.closest('[data-testid="property-history-media"]'));
    const isListingMedia = Boolean(image.closest('[data-testid="media-section"]'));
    if (isFloorPlan) addAsset(url, "floor-plan", {alt, width: image.naturalWidth || null, height: image.naturalHeight || null});
    else if (isPast) addAsset(url, "past-listing-photo", {alt, width: image.naturalWidth || null, height: image.naturalHeight || null});
    else if (isListingMedia) addAsset(url, "listing-photo", {alt, width: image.naturalWidth || null, height: image.naturalHeight || null});
  }
  for (const meta of document.querySelectorAll('meta[property="og:image"]')) {
    addAsset(meta.content, "listing-photo", {discovered_from: "og:image"});
  }
  structured.assets = [...assetsByUrl.values()];
  return {
    structured,
    assets: [...assetsByUrl.values()],
    page_html: `<!doctype html>\n${document.documentElement.outerHTML}`
  };
}

async function inject(func) {
  const results = await chrome.scripting.executeScript({target: {tabId: activeTab.id}, func});
  if (!results?.[0]) throw new Error("The page did not return any data.");
  return results[0].result;
}

nodes.collect.addEventListener("click", async () => {
  nodes.collect.disabled = true;
  setStatus("Collecting visible unit links…");
  try {
    const result = await inject(collectUnitsFromPage);
    if (queue && queue.building_slug !== result.building_slug) {
      queue = null;
    }
    const invalidRoutes = new Set(["MEDIA_GALLERY", "MEDIA-GALLERY", "PHOTOS", "MAP"]);
    const genericPattern = /^(?:\d+(?:BD|BR|BED|BEDROOM)S?[-/]?\d+(?:BA|BATH|BATHROOM)S?|\d+-?(?:BD|BR|BED|BEDROOM)S?)$/i;
    const ignoredUnits = new Set(queue?.ignored_units || []);
    const existing = new Map(
      (queue?.units || [])
        .filter((item) => !invalidRoutes.has(item.unit) && !genericPattern.test(item.unit.replace(/[ _]/g, "-")))
        .map((item) => [item.source_id, item])
    );
    for (const item of result.units) {
      if (!ignoredUnits.has(item.source_id)) {
        const previous = existing.get(item.source_id);
        existing.set(
          item.source_id,
          item.has_actual_link ? {...previous, ...item} : {...item, ...previous}
        );
      }
    }
    await saveQueue({
      building_slug: result.building_slug,
      building_url: result.building_url,
      updated_at: new Date().toISOString(),
      ignored_units: [...ignoredUnits],
      units: [...existing.values()]
    });
    const opened = result.opened_unavailable_view ? "Opened unavailable units. " : "";
    const ignored = result.ignored_generic_layouts.length
      ? ` Ignored generic layout: ${result.ignored_generic_layouts.join(", ")}.`
      : "";
    setStatus(`${opened}Found ${result.units.length} units; queue now has ${existing.size}.${ignored}`, "success");
  } catch (error) {
    setStatus(error.message || String(error), "error");
  } finally {
    nodes.collect.disabled = !activePage.isBuilding;
  }
});

nodes.chooseDirectory.addEventListener("click", async () => {
  try {
    if (!window.showDirectoryPicker) throw new Error("Directory selection requires a recent Edge or Chrome browser.");
    const handle = await window.showDirectoryPicker({id: "streeteasy-captures", mode: "readwrite"});
    if (!(await canWrite(handle, true))) throw new Error("Write permission was not granted.");
    captureDirectory = handle;
    await storeDirectoryHandle(handle);
    nodes.directory.textContent = `Capture directory: ${handle.name}`;
    setStatus("Capture directory configured.", "success");
  } catch (error) {
    if (error.name !== "AbortError") setStatus(error.message || String(error), "error");
  }
});

nodes.export.addEventListener("click", async () => {
  nodes.export.disabled = true;
  setStatus("Expanding history and preparing the capture…");
  let capturingSourceId = null;
  try {
    if (captureDirectory && !(await canWrite(captureDirectory, true))) {
      throw new Error("Capture-directory permission was not granted. Choose the directory again.");
    }
    const bundle = await inject(collectStreetEasyListing);
    const data = bundle.structured;
    capturingSourceId = data.source_listing_id;

    const currentQueue = queue?.building_slug === data.building_slug
      ? queue
      : {building_slug: data.building_slug, building_url: `https://streeteasy.com/building/${data.building_slug}`, units: []};
    const units = new Map(currentQueue.units.map((item) => [item.source_id, item]));
    units.set(data.source_listing_id, {
      ...(units.get(data.source_listing_id) || {}),
      source_id: data.source_listing_id,
      unit: data.unit,
      url: data.canonical_url,
      status: "capturing",
      captured_at: data.captured_at,
      history_rows: data.price_history.length
    });
    await saveQueue({...currentQueue, updated_at: new Date().toISOString(), units: [...units.values()]});

    let savedMessage;
    if (captureDirectory) {
      const saved = await writeCaptureBundle(bundle, (complete, total) => {
        setStatus(`Saving assets for ${data.unit}: ${complete}/${total}…`);
      });
      savedMessage = saved.relativePath;
    } else {
      const json = JSON.stringify(data, null, 2);
      const filename = `streeteasy_${data.building_slug}_${data.unit.replace(/[^a-z0-9_-]/gi, "-")}.json`;
      const url = `data:application/json;charset=utf-8,${encodeURIComponent(json)}`;
      await chrome.downloads.download({url, filename, saveAs: false});
      savedMessage = filename;
    }

    const completed = queue.units.find((item) => item.source_id === data.source_listing_id);
    completed.status = "done";
    delete completed.error;
    await saveQueue({...queue, updated_at: new Date().toISOString()});
    const following = nextPending(data.source_listing_id);
    setStatus(`Saved ${data.price_history.length} events for ${data.unit}: ${savedMessage}`, "success");
    if (following) await openUnit(following);
  } catch (error) {
    if (capturingSourceId && queue) {
      const failed = queue.units.find((item) => item.source_id === capturingSourceId);
      if (failed) {
        failed.status = "error";
        failed.error = error.message || String(error);
        await saveQueue({...queue, updated_at: new Date().toISOString()});
      }
    }
    setStatus(error.message || String(error), "error");
    nodes.export.disabled = false;
  }
});

nodes.next.addEventListener("click", () => openUnit(nextPending()));
nodes.markPending.addEventListener("click", async () => {
  if (!queue || !activePage.sourceId) return;
  const item = queue.units.find((candidate) => candidate.source_id === activePage.sourceId);
  if (item) {
    item.status = "pending";
    delete item.captured_at;
    delete item.history_rows;
    await saveQueue({...queue, updated_at: new Date().toISOString()});
    setStatus(`Marked unit ${item.unit} pending.`);
  }
});
nodes.restoreBad.addEventListener("click", async () => {
  if (!queue) return;
  const count = queue.ignored_units?.length || 0;
  await saveQueue({...queue, ignored_units: [], updated_at: new Date().toISOString()});
  setStatus(`Restored ${count} bad-unit identifiers. Collect the building again to add valid links.`);
});
nodes.clear.addEventListener("click", async () => {
  await chrome.storage.local.remove("unitQueue");
  queue = null;
  renderQueue();
  setStatus("Queue cleared.");
});

async function refreshActivePage(updateStatus = true) {
  [activeTab] = await chrome.tabs.query({active: true, currentWindow: true});
  activePage = pageIdentity(activeTab?.url || "");
  if (!activePage.sourceId && queue && activeTab?.url) {
    const currentUrl = activeTab.url.split("?", 1)[0];
    const queued = queue.units.find((item) => item.url?.split("?", 1)[0] === currentUrl);
    if (queued) {
      activePage.sourceId = queued.source_id;
      activePage.unit = queued.unit;
    }
  }
  nodes.collect.disabled = !activePage.isBuilding;
  nodes.export.disabled = !activePage.isUnit;
  nodes.markPending.disabled = !activePage.isUnit || !queue;
  if (!updateStatus) return;
  if (activePage.isRentalListing) setStatus(`Ready to export linked listing${activePage.unit ? ` for ${activePage.unit}` : ""}.`);
  else if (activePage.isUnit) setStatus(`Ready to export unit ${activePage.unit}.`);
  else if (activePage.isBuilding) setStatus("Ready to collect visible unit links.");
  else setStatus("Open a StreetEasy building or unit page.");
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (activeTab && tabId === activeTab.id && (changeInfo.status === "complete" || changeInfo.url)) {
    refreshActivePage(true).catch((error) => setStatus(error.message || String(error), "error"));
  }
});
chrome.tabs.onActivated.addListener(() => {
  refreshActivePage(true).catch((error) => setStatus(error.message || String(error), "error"));
});

(async function initialize() {
  queue = await loadQueue();
  captureDirectory = await loadDirectoryHandle();
  if (captureDirectory) {
    const writable = await canWrite(captureDirectory, false);
    nodes.directory.textContent = `Capture directory: ${captureDirectory.name}${writable ? "" : " (permission will be requested on capture)"}`;
  }
  renderQueue();
  await refreshActivePage(true);
})().catch((error) => setStatus(error.message || String(error), "error"));
