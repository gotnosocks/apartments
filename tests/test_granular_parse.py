import json

from apartments.granular_parse import parse_listing


def test_parse_listing_keeps_rental_and_sale_occurrences():
    listing = {
        "id": 42,
        "createdAt": "2020-01-01",
        "propertyDetails": {"address": {"displayUnit": "#4A", "url": "/building/demo"},
                             "bedroomCount": 2, "fullBathroomCount": 1, "livingAreaSize": 900, "roomCount": 4,
                             "features": {"list": ["Doorman"]}, "amenities": {"list": ["Laundry"]}},
        "propertyHistory": [{"listingId": 42,
                              "rentalEventsOfInterest": [{"date": "2024-01-01", "price": 3000, "status": "ACTIVE"}],
                              "saleEventsOfInterest": [{"date": "2023-01-01", "price": 700000, "status": "SOLD"}]}],
    }
    payload = json.dumps(listing).replace('"', '\\"')
    body = f'<html><script>self.__next_f.push([1,"a:{payload}\\n"])</script></html>'.encode()
    row, events = parse_listing(body, "https://streeteasy.com/building/demo/rental/42")
    assert row["listing_id"] == "42"
    assert row["unit_label"] == "#4A"
    assert row["parse_status"] == "ok"
    assert [event["event_category"] for event in events] == ["rental", "sale"]
    assert all(event["event_key"] for event in events)


def test_parse_listing_marks_missing_history_partial():
    body = b'<html><script type="application/json">{"listing":{"id":7,"propertyDetails":{"address":{}}}}</script></html>'
    row, events = parse_listing(body, "https://streeteasy.com/rental/7")
    assert row["parse_status"] == "partial"
    assert events == []


def test_history_bearing_object_wins_and_source_fields_are_preserved():
    compact = {"id": 9, "propertyDetails": {"address": {}}}
    full = {"id": 9, "pricing": {"rent": 4100, "source": "api"},
            "propertyDetails": {"address": {"displayUnit": "#9C"}},
            "propertyHistory": [{"listingId": 9, "rentalEventsOfInterest":
                                  [{"date": "2025-01-01", "price": 4100, "status": "ACTIVE"}]}]}
    def flight(obj):
        return json.dumps(obj).replace('"', '\\"')
    body = ('<html><a data-testid="addressLink" href="/building/source-building">x</a>'
            f'<script type="application/json">{json.dumps({"listing": compact})}</script>'
            f'<script>self.__next_f.push([1,"a:{flight(full)}\\n"])</script></html>').encode()
    row, events = parse_listing(body, "https://streeteasy.com/building/source-building/rental/9")
    assert row["parse_status"] == "ok"
    assert row["building_slug"] == "source-building"
    assert json.loads(row["pricing_json"])["source"] == "api"
    assert events[0]["event_listing_id"] == "9"


def test_event_key_is_stable_across_capture_listing_and_position():
    def body(listing_id, episode_index=0):
        listing = {"id": listing_id, "propertyDetails": {"address": {"displayUnit": "#1"}},
                   "propertyHistory": [{"listingId": "77", "rentalEventsOfInterest":
                                         [{"date": "2024-01-01", "price": 3000, "status": "ACTIVE"}]}]}
        payload = json.dumps(listing).replace('"', '\\"')
        return f'<script>self.__next_f.push([1,"a:{payload}\\n"])</script>'.encode()
    _, first = parse_listing(body(10), "https://streeteasy.com/rental/10")
    _, second = parse_listing(body(11), "https://streeteasy.com/rental/11")
    assert first[0]["event_key"] == second[0]["event_key"]
    assert first[0]["occurrence_key"] == second[0]["occurrence_key"]
