import json
import re
from pathlib import Path
from typing import Any

TARGETS_PATH = Path("config/targets.json")


def load_targets(path: Path = TARGETS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text())


def normalize_address(value: str | None) -> str:
    """Normalize enough NYC address variation for local scope matching."""
    if not value:
        return ""
    text = value.upper().strip().split(",", maxsplit=1)[0]
    text = re.sub(r"#", " UNIT ", text)
    text = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", text)
    replacements = {
        r"\bW\b": "WEST",
        r"\bE\b": "EAST",
        r"\bST\b": "STREET",
        r"\bAVE?\b": "AVENUE",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    # Unit text is not part of the building address.
    text = re.split(r"\b(?:APT|APARTMENT|UNIT|STE|SUITE)\b", text, maxsplit=1)[0]
    return re.sub(r"\s+", " ", text).strip()


def house_number_and_street(value: str | None) -> tuple[int | None, str]:
    normalized = normalize_address(value)
    match = re.match(r"^(\d+)[A-Z-]*\s+(.+?)$", normalized)
    if not match:
        return None, normalized
    return int(match.group(1)), match.group(2)


def in_scope(address: str | None, scope: str, targets: dict[str, Any]) -> bool:
    number, street = house_number_and_street(address)
    building = targets["building"]
    segment = targets["street"]
    if scope == "building":
        return normalize_address(address) == normalize_address(building["canonical_address"])
    if scope == "street":
        return (
            number is not None
            and segment["minimum_house_number"] <= number <= segment["maximum_house_number"]
            and street == normalize_address(segment["name"])
        )
    raise ValueError(f"Unknown scope: {scope}")
