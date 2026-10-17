"""Canonical-URL unit memberships of rental listings, from their captures.

The data pipeline's identity rule (`pipeline/models/ads/identity.sql`) follows
`memberships`, and its tests compare the two. Join memberships by listing_id to
read a unit's full history.
"""

from collections import defaultdict

from .unit_canonical import ASSOCIATION_RULE, canonical_unit_id, common_unit_page


def memberships(captures):
    """No labels, latest-listing pointers, attributes, or event data are required."""
    listings = defaultdict(list)
    for capture in captures:
        if capture["listing_id"]:
            listings[capture["listing_id"]].append(capture)
    pages = {
        lid: common_unit_page(c["canonical_unit_url"] for c in rows)
        for lid, rows in listings.items()
    }
    # Don't split an inconsistent listing between two units or implicitly bridge
    # their otherwise-consistent members. Keep the affected URLs unresolved.
    ambiguous_pages = {
        c["canonical_unit_url"]
        for lid, rows in listings.items()
        if pages[lid] is None
        for c in rows
        if c["canonical_unit_url"]
    }
    result = []
    for lid, rows in sorted(listings.items()):
        page = pages[lid]
        reason = (
            "Missing or conflicting canonical unit URLs across captures"
            if not page
            else "Canonical unit URL is also used by a listing with conflicting captures"
            if page in ambiguous_pages
            else None
        )
        result.append(
            {
                "listing_id": lid,
                "unit_id": canonical_unit_id(page) if not reason else None,
                "canonical_unit_url": page,
                "capture_count": len(rows),
                "status": "unresolved" if reason else "associated",
                "reason": reason,
                "rule": ASSOCIATION_RULE,
            }
        )
    return result
