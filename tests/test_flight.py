import pytest

from streeteasy_archive.flight import FlightText, decode_records


def frame(key, text):
    return f"{key}:T{len(text.encode('utf-8')):x},{text}"


def test_text_byte_lengths_adjacent_frames_and_embedded_fake_json():
    text = 'North-facing café 🏠\nff:{"propertyDetails":{"fake":true}}'
    decoded = decode_records(
        frame("a", text) + frame("b", "yes") + 'c:{"description":"$a"}\n'
    )
    assert decoded == {"a": text, "b": "yes", "c": {"description": "$a"}}
    assert isinstance(decoded["a"], FlightText)
    assert "ff" not in decoded


def test_legacy_json_model_scalars_references_and_ignored_tags():
    assert decode_records(
        ':HL["style"]\n1:I["module"]\n2:{"id":42}\n3:["$2"]\n4:"$2"\n5:null\n'
    ) == {"2": {"id": 42}, "3": ["$2"], "4": "$2", "5": None}


@pytest.mark.parametrize(
    "stream, message",
    [
        ("a:Tff,short", "Truncated"),
        ("a:Txyz,foo", "Malformed"),
        ("a:T1,é", "UTF-8"),
        ("a:T1,long\nb:{}\n", "boundary"),
        ("a:T9999999999999999999999999,foo", "Malformed"),
        ("a:T-1,foo", "Malformed"),
        ("a:T,foo", "Malformed"),
        ("a:T1,\ud800", "Unicode"),
    ],
)
def test_invalid_text_frames_fail_closed(stream, message):
    with pytest.raises(ValueError, match=message):
        decode_records(stream)


def test_duplicate_ids_identical_ok_conflicting_rejected():
    assert decode_records('a:{"x":1}\na:{"x":1}\n') == {"a": {"x": 1}}
    assert decode_records(frame("a", "yes") + frame("a", "yes")) == {"a": "yes"}
    for stream in ('a:{"x":1}\na:{"x":2}\n', frame("a", "yes") + 'a:"yes"\n'):
        with pytest.raises(ValueError, match="Conflicting"):
            decode_records(stream)


def test_empty_text_and_size_bounds():
    assert decode_records("a:T0,b:{}\n") == {"a": "", "b": {}}
    with pytest.raises(ValueError, match="stream exceeds"):
        decode_records("a:T2,é", max_stream_bytes=6)
    with pytest.raises(ValueError, match="record a exceeds"):
        decode_records("a:T3,yes", max_record_bytes=2)
    with pytest.raises(ValueError, match="record a exceeds"):
        decode_records('a:{"key":1}', max_record_bytes=2)
    with pytest.raises(ValueError, match="positive"):
        decode_records("", max_record_bytes=0)


def test_rejoined_utf16_surrogate_pairs_use_utf8_length():
    assert decode_records("a:T4," + "\ud83c" + "\udfe0") == {"a": "🏠"}
