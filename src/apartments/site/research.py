"""Research data for the site's Research section.

`rentfrontier.dashboard` (frontier environment, every 10 minutes under the
heavy-job lock) writes the board's data to the `site` build of
/data1/apartments/dashboard: entries, as-of snapshots, milestones and the
data-quality card. The site reads that file read-only and keeps the parsed
copy until the file behind the symlink changes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DEFAULT = Path(
    os.environ.get("RESEARCH_DATA", "/data1/apartments/dashboard/site/data.json")
)


class Research:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or DEFAULT)
        self._key = None
        self._data = None
        self._lock = threading.Lock()

    def load(self) -> dict | None:
        """The board data, or None when no build is readable."""
        try:
            real = self.path.resolve(strict=True)
            stat = real.stat()
        except OSError:
            return None
        key = (str(real), stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if key != self._key:
                try:
                    data = json.loads(real.read_text())
                except (OSError, ValueError):
                    return self._data  # a build mid-swap: keep the last good copy
                self._key, self._data = key, data
            return self._data


def entry_for_run(data: dict | None, run: str | None) -> dict | None:
    """The board entry whose row-split fit is `run`."""
    if not data or not run:
        return None
    for entry in data.get("entries", []):
        rows = (entry.get("splits") or {}).get("rows") or {}
        if rows.get("run") == run:
            return entry
    return None


def latest_milestones(data: dict | None, n: int = 6) -> list[dict]:
    if not data:
        return []
    milestones = sorted(
        data.get("milestones", []), key=lambda m: m.get("at", ""), reverse=True
    )
    return milestones[:n]
