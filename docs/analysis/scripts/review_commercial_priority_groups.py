"""Publish manual full-description dispositions for the first 37 groups."""
import argparse
from collections import Counter
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle

DISPOSITIONS = {
    'explicit_nonresidential_offer': '1543471 2391701 1466274 947730 806884'.split(),
    'ambiguous_offered_use': '3065554 3261015'.split(),
    'mixed_live_work_offer': '2693342 668834 790794 2312228 1578616 1540611 613436 815640 2440454 1337652 1469954'.split(),
    'incidental_commercial_reference': '4876582 2765422 1414412 4572560 3929876 3068068 3254041 4578090 4384960 1263776 2181306 2423303 3924894 4027283 3107904 2474875 2833554 1283664 4417021 4060052'.split(),
}


def run(groups, output):
    groups, output = Path(groups), Path(output)
    manifest, files = _verified_bundle(groups, retain={'groups.jsonl'})
    if (manifest['version'] != 'commercial-review-description-groups-v1'
            or manifest['screen_manifest_sha256'] != 'cd15f51866365e5f7ad68f4f517a031120e049c42bebc1edbe6da7b62c9c43d9'):
        raise ValueError('Manual review binds a different screen')
    selected = [json.loads(line) for line in files['groups.jsonl'].decode().split('\n') if line]
    selected = [g for g in selected if g['priority_hint']]
    by_ad = {ad: kind for kind, ads in DISPOSITIONS.items() for ad in ads}
    if (len(selected) != 37 or len(by_ad) != 38
            or {a['source_listing_id'] for g in selected for a in g['associations']} != set(by_ad)):
        raise ValueError('Review membership differs')
    queue = [{**g, 'dispositions': [{'association': a, 'disposition': by_ad[a['source_listing_id']],
        'applied_to_source_or_model': False} for a in g['associations']]} for g in selected]
    summary = {'full_descriptions_reviewed': 37, 'advertisements': 38,
        'advertisements_by_disposition': dict(Counter(by_ad.values())),
        'remaining_full_description_groups': 509,
        'scope': 'Manual product-language review only, not legal occupancy verification or historical attribute certification. Incidental references do not establish independently verified residential truth. No automatic source exclusions.'}
    publish_bundle(output, {'review.jsonl': ''.join(canonical(g)+'\n' for g in queue),
        'summary.json': canonical(summary)+'\n', Path(__file__).name: Path(__file__).read_text()},
        {'version': 'commercial-priority-full-description-review-v1',
         'groups_manifest_sha256': digest(groups/'complete.json'),
         'source_manifest_sha256': manifest['source_manifest_sha256'], 'source_or_model_changes': False})
    _verified_bundle(output)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--groups', required=True)
    p.add_argument('--output', required=True)
    print(canonical(run(**vars(p.parse_args()))))
