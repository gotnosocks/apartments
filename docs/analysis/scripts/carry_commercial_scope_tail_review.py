"""Rebind unchanged reviewed tail cases to the cumulative scope fit residuals."""
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


def run():
    root = Path('data/model')
    inputs = root/'chelsea-commercial-scope-tail-review-inputs-20260920'
    previous = root/'chelsea-residual-scope-tail-review-inputs-20260919'
    review = root/'chelsea-residual-scope-tail-review-20260919'
    output = root/'chelsea-commercial-scope-tail-review-20260920'
    bindings = [(inputs, 'd20c4decb25e8f07d92c1aa661c45e547939d3b5fa284a92816df894d44a7265'),
                (previous, 'd9958d01af045de9e31802762d22e56df79b16b40942edb715e8be5c67e3f93c'),
                (review, '422d3603470c1cae0aa07246470cb3a8091ab659659a4b504bede2edcab2528f')]
    for path, sha in bindings:
        if digest(path/'complete.json') != sha:
            raise ValueError('Review input changed: '+str(path))
    manifest, files = _verified_bundle(inputs, retain={'cases.jsonl'})
    _, old_files = _verified_bundle(previous, retain={'cases.jsonl'})
    _, review_files = _verified_bundle(review, retain={'queue.jsonl', 'raw-witnesses.jsonl'})
    parse = lambda data: [json.loads(s) for s in data.decode().split('\n') if s]
    cases = parse(files['cases.jsonl'])
    old = {c['source_row']['source_listing_id']: c for c in parse(old_files['cases.jsonl'])}
    reviewed = {r['source_listing_id']: r for r in parse(review_files['queue.jsonl'])}
    result = []
    for case in cases:
        ad = case['source_row']['source_listing_id']
        assert case['source_row'] == old[ad]['source_row']
        assert case['captures'] == old[ad]['captures']
        assert case['source_row_sha256'] == old[ad]['source_row_sha256']
        prior = reviewed[ad]
        assert prior['source_row_sha256'] == case['source_row_sha256']
        result.append({**prior, 'rank': case['rank'], 'residual': case['residual'],
            'reused_review_manifest_sha256': digest(review/'complete.json')})
    assert len(result) == len(old) == len(reviewed) == 15
    publish_bundle(output, {
        'queue.jsonl': ''.join(canonical(r)+'\n' for r in result),
        'raw-witnesses.jsonl': review_files['raw-witnesses.jsonl'].decode(),
        Path(__file__).name: Path(__file__).read_text(),
    }, {'version': 'reviewed-commercial-scope-tail-v1', 'cases': 15,
        'exact_prior_reviews_reused': 15, 'new_full_description_reviews': 0,
        'input_manifest_sha256': digest(inputs/'complete.json'),
        'prior_input_manifest_sha256': digest(previous/'complete.json'),
        'prior_review_manifest_sha256': digest(review/'complete.json'),
        'fit_manifest_sha256': manifest['fit_manifest_sha256'],
        'source_manifest_sha256': manifest['dataset_manifest_sha256'],
        'source_or_model_changes': False,
        'limitation': 'Unresolved prior findings remain unresolved; unchanged source evidence does not establish correctness.'})
    _verified_bundle(output)
    print(canonical({'output': str(output), 'manifest_sha256': digest(output/'complete.json')}))


if __name__ == '__main__':
    run()
