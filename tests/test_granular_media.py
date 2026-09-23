import json

import pytest

from apartments.granular_media import page_type, parse_media_gallery
from apartments.granular_parse import parse_listing


def gallery_body(*objects):
    return (
        '<html><head><link rel="canonical" href="/sale/42"></head><body>'
        '<script type="application/json">'
        + json.dumps({"galleries": objects})
        + "</script>"
    ).encode()


def gallery(listing_id=42):
    return {
        "id": listing_id,
        "buildingId": 7,
        "propertyDetails": {"address": {"displayUnit": "#4A"}},
        "media": {
            "photos": [
                {"url": "https://example.com/photo.jpg", "caption": "Living room"}
            ],
            "floorPlans": [],
        },
        "signatureMediaGallery": {"images": []},
    }


@pytest.mark.parametrize(
    "path",
    [
        "/building/demo/media_gallery",
        "/building/demo/4a/media_gallery",
        "/building/demo/rental/42/media_gallery",
        "/rental/42/media_gallery/",
        "/sale/42/media_gallery?image=2",
    ],
)
def test_gallery_page_type_overrides_legacy_kind(path):
    assert (
        page_type({"url": "https://streeteasy.com" + path, "kind": "listing"})
        == "media_gallery"
    )
    assert (
        page_type({"url": "https://streeteasy.com" + path, "kind": None})
        == "media_gallery"
    )
    assert (
        page_type(
            {"url": "https://streeteasy.com/rental/42?next=media_gallery", "kind": None}
        )
        == "listing"
    )


def test_gallery_preserves_media_without_requiring_or_parsing_history():
    body = gallery_body(gallery())
    url = "https://streeteasy.com/sale/42/media_gallery"
    row = parse_media_gallery(body, url)
    assert row["parse_status"] == "ok" and row["error"] is None
    assert row["page_type"] == "media_gallery" and row["listing_type"] == "sale"
    assert row["listing_id"] == "42" and row["building_id"] == "7"
    assert json.loads(row["media_json"]) == gallery()["media"]
    assert (
        json.loads(row["signature_media_gallery_json"])
        == gallery()["signatureMediaGallery"]
    )
    assert json.loads(row["raw_gallery_json"]) == gallery()
    assert row["canonical_unit_url"] is None  # A gallery need not declare a unit URL.
    with pytest.raises(ValueError, match="parse_media_gallery"):
        parse_listing(body, url)


def test_gallery_missing_wrong_ambiguous_and_unresolved_objects_are_real_errors():
    url = "https://streeteasy.com/sale/42/media_gallery"
    assert (
        parse_media_gallery(gallery_body(gallery(99)), url)["parse_status"] == "failed"
    )
    changed = gallery()
    changed["media"] = {"photos": ["different"]}
    assert (
        parse_media_gallery(gallery_body(gallery(), changed), url)["error"]
        == "Conflicting media-gallery objects"
    )
    unresolved = gallery()
    unresolved["media"] = "$missing"
    row = parse_media_gallery(gallery_body(unresolved), url)
    assert row["parse_status"] == "partial" and "unresolved" in row["error"]
    assert json.loads(row["raw_gallery_json"]) == unresolved
    with pytest.raises(ValueError, match="Not a media-gallery"):
        parse_media_gallery(gallery_body(gallery()), "https://streeteasy.com/sale/42")
