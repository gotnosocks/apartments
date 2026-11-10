"""Build the explainer page: put a data file into page.html.

python docs/notes/drift-2026-11-10/artifact/build.py DATA.json OUT.html
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main(data: str, out: str) -> None:
    payload = json.dumps(json.loads(Path(data).read_text()), separators=(",", ":"))
    page = (HERE / "page.html").read_text()
    Path(out).write_text(page.replace("__DATA__", payload.replace("</", "<\\/")))


if __name__ == "__main__":
    main(*sys.argv[1:3])
