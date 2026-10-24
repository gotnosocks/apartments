import importlib.util
import json
import sys
import types
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from steps import adtext

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "tests" / "fixture"
CHAIN = PROJECT.parent / "frontier" / "src" / "rentfrontier"

# Texts for each branch of the two readings, with the reading the chain gives them.
CASES = [
    ("Classic five-story walk-up on a quiet block.", False, None),
    ("A short walk up to Astor Place.", None, None),
    ("No stairs to walk up, a true walk-in.", None, None),
    ("Three flights up, with in-unit laundry.", False, None),
    ("Two flights up to the private roof deck.", None, None),
    ("No laundry or elevator in the building.", False, None),
    ("Non-elevator building.", False, None),
    ("Elevator building with a live-in super.", True, None),
    # A text saying both gives no reading.
    ("No elevator. Elevator access from the garage.", None, None),
    (
        "Sunny one bedroom. Pet\n fee $500 at signing.",
        None,
        "allowed_restrictions_unknown",
    ),
    ("A deposit per dog of $300.", None, "allowed_restrictions_unknown"),
    ("Cozy studio, no pet fees!", None, "allowed_restrictions_unknown"),
    ("No broker fee, no deposit for the gym.", None, None),
    ("No pets. Pet deposit required.", None, "not_allowed"),
    ("Cats only, no dogs. Pet fee $25 a month.", None, None),
    ("Pets on approval, pet fee $500.", None, "approval_required"),
    ("Pets welcome with landlord's approval.", None, "approval_required"),
    ("Small dogs only.", None, "allowed_restrictions_unknown"),
    ("No dogs over 25 lbs.", None, "allowed_restrictions_unknown"),
    ("Guarantors considered case by case.", None, None),
    ("Pets considered case by case.", None, "approval_required"),
    # Each of these texts holds one word of `ELEVATOR_WORDS` or `PET_WORDS` alone.
    ("Fourth floor walk up.", False, None),
    ("Fifth floor walkup.", False, None),
    ("Cats welcome.", None, "allowed_restrictions_unknown"),
    ("No animals.", None, "not_allowed"),
    ("Under 25 lbs, case by case.", None, "approval_required"),
    ("Up to 30 pounds, case by case.", None, "approval_required"),
    ("Cats are ok, dogs aren't allowed.", None, None),
    ("Pets: no dogs.", None, None),
    ("No board approval or pets.", None, None),
    ("No smoking or pets allowed.", None, None),
    ("Fast approvals, pets welcome.", None, "allowed_restrictions_unknown"),
    ("Pets welcome!", None, "allowed_restrictions_unknown"),
    ("No pets allowed. Pets welcome. Pet fee $500.", None, "not_allowed"),
    ("", None, None),
    (None, None, None),
]


@pytest.mark.parametrize("text, elevator, pets", CASES)
def test_cases(text, elevator, pets):
    assert adtext.elevator(text) is elevator
    assert adtext.pets(text) == pets


def chain_adfills(monkeypatch):
    """The chain's `rentfrontier.adfills`, loaded from its file with the real `petstext`. The
    modules it imports only for its command come in as empty stand-ins."""
    package = types.ModuleType("rentfrontier")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "rentfrontier", package)
    for name in ("data", "descriptions", "features", "listing_extras"):
        stand_in = types.ModuleType(f"rentfrontier.{name}")
        stand_in.EXTERNAL_ROOT = stand_in._git = None
        monkeypatch.setitem(sys.modules, stand_in.__name__, stand_in)
        setattr(package, name, stand_in)
    for name in ("petstext", "adfills"):
        spec = importlib.util.spec_from_file_location(
            f"rentfrontier.{name}", CHAIN / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        setattr(package, name, module)
    return package.adfills


# The patterns `adtext` copies from each of the chain's modules.
PETSTEXT = ("SIZE", "NO_PETS", "NO_DOGS", "CASE", "ALLOWED", "CLASSES")
ADFILLS = (
    "ELEVATOR_NO",
    "ELEVATOR_YES",
    "CASE_PETS",
    "PET_LIMIT",
    "PET_FEE",
    "DOGS_BANNED",
    "PET_APPROVAL",
    "NO_APPROVAL_OR_PETS",
    "NO_PET_KIND",
    "APPLICATION_APPROVAL",
)


def test_patterns_match_the_chain(monkeypatch):
    """Each pattern of `adtext` equals the chain's, so a branch no text of the cases or the
    fixture reaches still reads as the chain's does. `CODED` leaves out the chain's "no_dogs"
    level, which the fill's `keep` never reads."""
    chain = chain_adfills(monkeypatch)
    petstext = sys.modules["rentfrontier.petstext"]
    assert [n for n in PETSTEXT if getattr(adtext, n) != getattr(petstext, n)] == []
    assert [n for n in ADFILLS if getattr(adtext, n) != getattr(chain, n)] == []
    assert petstext.CODED == {**adtext.CODED, "no_dogs": "no_dogs"}


def test_readings_match_the_chain(monkeypatch):
    """`adtext` reads the cases and every description of the fixture's records as the chain's
    pandas functions read them."""
    descriptions = duckdb.sql(
        f"""SELECT DISTINCT json_extract_string(record, '$.description')
        FROM read_parquet('{FIXTURE / "export" / "ads" / "**" / "*.parquet"}')
        WHERE outcome = 'record'"""
    ).fetchall()
    texts = pd.Series([text for text, *_ in CASES] + [text for (text,) in descriptions])
    assert len(texts) > 200
    chain = chain_adfills(monkeypatch)
    elevator = chain.elevator(texts).elevator.map({"yes": True, "no": False})
    pets = chain.pets(texts).pets
    for i, text in texts.items():
        assert adtext.elevator(text) == elevator.get(i), json.dumps(text)
        assert adtext.pets(text) == pets.get(i), json.dumps(text)
    # The texts give each reading of each field.
    assert set(elevator) == {True, False}
    assert set(pets) == set(adtext.CODED.values())
