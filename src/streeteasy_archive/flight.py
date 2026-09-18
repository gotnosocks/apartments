"""Decode inert JSON and byte-framed text records from an HTML Flight stream.

Callers concatenate JSON-decoded ``self.__next_f.push([1, text])`` chunks
first. JavaScript is never evaluated. This is a data-record decoder, not a React
runtime: module, hint and other tagged newline-delimited rows are ignored.
"""
from __future__ import annotations

import json
import re

VERSION = 'flight-records-v1'
_HEADER = re.compile(rb'([0-9a-f]*):')
_TEXT_SIZE = re.compile(rb'T([0-9a-f]{1,16}),')


class FlightText(str):
    """Literal T-record text, which must not be followed as another reference."""


def decode_records(stream: str, *, max_stream_bytes: int = 32 * 1024 * 1024,
                   max_record_bytes: int = 8 * 1024 * 1024) -> dict:
    """Return JSON model values and literal T strings keyed by hexadecimal ID.

    T lengths count UTF-8 bytes, and their next record need not start on a new
    line. Text may contain newlines or fake record headers; neither is framing.
    Malformed/truncated T frames, invalid UTF-8, size-limit violations and
    conflicting duplicate IDs raise ValueError rather than yield partial data.
    Identical duplicate records are harmless. Invalid JSON model rows are
    ignored, preserving previous behavior for unsupported Flight row types.
    """
    if max_stream_bytes <= 0 or max_record_bytes <= 0:
        raise ValueError('Flight size limits must be positive')
    if len(stream) > max_stream_bytes:
        raise ValueError('Flight stream exceeds size limit')
    try:
        # Independently decoded JS chunks can bisect a UTF-16 surrogate pair.
        # Rejoin valid pairs before applying the protocol's UTF-8 byte lengths.
        if re.search(r'[\ud800-\udfff]', stream):
            stream = stream.encode('utf-16-le', errors='surrogatepass').decode('utf-16-le')
        data = stream.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('Flight stream contains invalid Unicode') from exc
    if len(data) > max_stream_bytes:
        raise ValueError('Flight stream exceeds size limit')
    records, fingerprints = {}, {}
    cursor = 0
    while cursor < len(data):
        if data[cursor:cursor + 1] == b'\n':
            cursor += 1
            continue
        header = _HEADER.match(data, cursor)
        if header is None:
            # Ignore unsupported non-record lines, never scan their contents
            # for plausible record headers.
            end = data.find(b'\n', cursor)
            cursor = len(data) if end < 0 else end + 1
            continue
        key = header.group(1).decode('ascii')
        start = header.end()
        is_text = data[start:start + 1] == b'T'
        if is_text:
            size = _TEXT_SIZE.match(data, start)
            if size is None:
                raise ValueError(f'Malformed Flight text length for record {key}')
            length = int(size.group(1), 16)
            if length > max_record_bytes:
                raise ValueError(f'Flight record {key} exceeds size limit')
            start = size.end()
            end = start + length
            if end > len(data):
                raise ValueError(f'Truncated Flight text record {key}')
            try:
                value = FlightText(data[start:end].decode('utf-8'))
            except UnicodeDecodeError as exc:
                raise ValueError(f'Invalid UTF-8 length boundary in Flight record {key}') from exc
            cursor = end
            # A declared short length must not permit arbitrary trailing text
            # to become a fresh record boundary.
            if cursor < len(data) and data[cursor:cursor + 1] != b'\n' and _HEADER.match(data, cursor) is None:
                raise ValueError(f'Invalid boundary after Flight text record {key}')
        else:
            end = data.find(b'\n', start)
            end = len(data) if end < 0 else end
            if end - start > max_record_bytes:
                raise ValueError(f'Flight record {key} exceeds size limit')
            cursor = end + 1
            # Modules/hints/debug/etc. are tagged, not JSON model data.
            try:
                value = json.loads(data[start:end])
            except (ValueError, UnicodeDecodeError):
                continue
        if not key:
            continue
        fingerprint = (is_text, json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')))
        if key in fingerprints and fingerprints[key] != fingerprint:
            raise ValueError(f'Conflicting Flight records for ID {key}')
        records[key] = value
        fingerprints[key] = fingerprint
    return records
