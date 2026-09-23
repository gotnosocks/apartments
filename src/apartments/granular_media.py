"""Parse archived media galleries without requiring or interpreting price history."""

from urllib.parse import urlsplit
import re

from streeteasy_archive.extract import is_gallery_url, kind_for, _scripts, _selector
from .granular_parse import _listing_candidates, _json
from .unit_canonical import canonical_fields


def page_type(item):
    """Derived page type; the archive's original kind remains unchanged."""
    return (
        "media_gallery"
        if is_gallery_url(item["url"])
        else item.get("kind") or kind_for(item["url"])
    )


def parse_media_gallery(body, url):
    if not is_gallery_url(url):
        raise ValueError("Not a media-gallery URL")
    match = re.search(r"/(rental|sale)/(\d+)(?:/|$)", urlsplit(url).path)
    requested_type, requested_id = match.groups() if match else (None, None)
    candidates = _listing_candidates(_scripts(_selector(body)))
    matching = [
        c
        for c in candidates
        if requested_id is None or str(c.get("id")) == requested_id
    ]
    # Only objects carrying gallery payloads qualify. Do not borrow a related
    # listing or choose silently between conflicting gallery objects.
    galleries = [c for c in matching if "media" in c or "signatureMediaGallery" in c]
    gallery = galleries[0] if len(galleries) == 1 else None
    error = (
        None
        if gallery is not None
        else (
            "Conflicting media-gallery objects"
            if galleries
            else "Media-gallery object missing or unresolved"
        )
    )
    if gallery is not None and any(
        gallery.get(k) is not None and not isinstance(gallery[k], (dict, list))
        for k in ("media", "signatureMediaGallery")
    ):
        error = "Gallery media payload missing or unresolved"
    return {
        **canonical_fields(body, url),
        "url": url,
        "page_type": "media_gallery",
        "listing_id": str(gallery["id"])
        if gallery and gallery.get("id") is not None
        else requested_id,
        "listing_type": requested_type,
        "building_id": str(gallery["buildingId"])
        if gallery and gallery.get("buildingId") is not None
        else None,
        "property_details_json": _json(gallery.get("propertyDetails"))
        if gallery
        else None,
        "media_json": _json(gallery.get("media")) if gallery else None,
        "signature_media_gallery_json": _json(gallery.get("signatureMediaGallery"))
        if gallery
        else None,
        "raw_gallery_json": _json(gallery),
        "parse_status": ("partial" if error else "ok")
        if gallery is not None
        else "failed",
        "error": error,
    }
