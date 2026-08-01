# StreetEasy Listing Exporter

This local extension builds a persistent unit to-do list from a StreetEasy building page and exports unit histories you deliberately open. It does not crawl links in the background, use a proxy, or send data anywhere.

## Recommended Windows setup: Edge or Chrome

1. Open `edge://extensions` or `chrome://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select this `browser-extension` directory.
5. Click the extension toolbar icon once to open its persistent browser side panel. The panel remains open while the active tab navigates between units and uses the available vertical space.
6. Create `data/captures` in the project if needed.
7. Click **Choose capture directory** and select the project’s `data/captures` directory. From Windows it is available under `\\wsl.localhost\\<distribution>\\home\\ben\\code\\apartments\\data\\captures`.
8. Open the StreetEasy building page. Collection opens **View unavailable units** automatically.
9. In the side panel, click **Open unavailable units and collect**. If StreetEasy paginates the units, repeat on each page; links are merged and deduplicated.
10. Use **Open next pending** or an individual unit's **Open** button.
11. On the unit page, click **Export this unit and open next**. The extension expands dynamic content, writes a capture bundle, marks the unit complete, and navigates to the next pending unit.

The queue persists across browser tabs and restarts. It preserves the actual link from an unavailable-unit row, including `/rental/<id>` links when no canonical unit route exists. **Bad** removes an invalid detected unit and prevents later collection from re-adding it. **Restore bad** clears that ignored list without losing completed work; collect the building again to restore valid rows. **Mark current pending** allows a unit to be recaptured. **Clear queue** resets both the queue and its ignored-unit list.

Each export preserves the full unit identifier and adds parsed fields. For example,
`3B` becomes `floor: 3`, `unit_letter: "B"`, and `unit_suffix: "B"`.
A legacy numeric identifier such as `3658` remains `unit: "3658"` and is recorded
as inferred `floor: 3`, `unit_suffix: "658"`, and `unit_format: "numeric"`.
Legacy-to-modern identity mappings are stored separately rather than overwriting
source unit numbers. Generic layout pages such as `1bd1ba` or `1bd/1ba` are
classified as non-specific `generic-layout` listings and omitted from the physical-unit queue. Penthouse identifiers such as `PH`, `PHA`, and `PHB` are valid physical units with `unit_format: "penthouse"`; their floor remains unset and they are not merged with top-floor numbered units.

## Firefox

This version uses the Chromium Side Panel API and is intended for current Edge or Chrome. Firefox uses a different sidebar API and is not supported by this build.

## Capture bundle

Each timestamped unit capture contains `manifest.json`, `structured.json`, rendered
`page.html`, `assets.json`, and downloaded photo/floor-plan assets with SHA-256 hashes.
Price-history extraction supports both StreetEasy's older three-column table and
newer two-column table where event text appears beneath the price.
If no directory is selected, the extension falls back to the previous JSON download.

## Import

Import every bundle into the local DuckDB database:

```bash
uv run apartments import-captures data/captures
```

A single old-style JSON download can still be imported with
`apartments import-streeteasy-json <path>`.

Review StreetEasy's current terms before expanding this beyond personal, manually initiated research.
