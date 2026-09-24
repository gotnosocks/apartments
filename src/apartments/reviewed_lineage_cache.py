"""Per-process reuse of verified reviewed-source lineage.

Kept separate from ``reviewed_source_lineage`` so archived fit audits of that
loader remain exact. Verification semantics are unchanged; only repeated
reconstruction of an identical, hash-checked bundle is skipped.
"""
from copy import deepcopy
import hashlib
import json

from . import reviewed_source_lineage as L

_VERIFIED = {}


def verified_bundle_lineage(manifest, files):
    """Verify a hash-checked dataset bundle's lineage once per process.

    ``files`` holds raw artifact bytes. Each used file is re-checked against the
    manifest, so an identical manifest hash implies identical verified inputs
    and the reconstructed ancestor can be reused by later readers.
    """
    sidecars = {'quarantined': L.reviewed_cohort_quarantine.SIDECAR, 'elevator_changes': L.elevator_corrections.SIDECAR,
                'floor_label_changes': L.floor_label_projection.SIDECAR, 'expanded_floor_changes': L.expanded_floor_projection.SIDECAR,
                'residual_scope_changes': L.residual_scope_projection.SIDECAR, 'direct_floor_changes': L.direct_floor_projection.SIDECAR}
    for name in ('observations.jsonl', *[s for s in sidecars.values() if s in files]):
        if hashlib.sha256(files[name]).hexdigest() != manifest.get('files', {}).get(name):
            raise ValueError(f'Lineage input differs from its manifest: {name}')
    key = L.manifest_hash(manifest)
    if key not in _VERIFIED:
        # Only LF separates JSONL; source literals may contain Unicode separators.
        records = lambda name: [json.loads(line) for line in files[name].decode().split('\n') if line.strip()]
        _VERIFIED.clear()  # One selected dataset at a time; bounds memory.
        _VERIFIED[key] = L.source_lineage(manifest, records('observations.jsonl'),
            **{arg: records(name) for arg, name in sidecars.items() if name in files})
    return deepcopy(_VERIFIED[key])
