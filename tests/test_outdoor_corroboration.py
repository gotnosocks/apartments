"""Finite phrase/scope development cases; not a population accuracy estimate."""
import copy

import pytest

from apartments.outdoor_corroboration import corroborate
from apartments.outdoor_evidence import extract


def capture(text, codes=('BALCONY',), capture_id=1):
    details = {'features': {'privateOutdoorSpaceTypes': list(codes)}}
    return {'capture_id': capture_id, 'audit_id': 'ad-observation', 'source_listing_id': '123',
            'unit_id': 'unit:1', 'body_sha256': 'body-hash', 'raw_listing_sha256': 'raw-hash',
            'description': text, 'property_details': details,
            'extraction': extract({'propertyDetails': details, 'description': text})}


@pytest.mark.parametrize('text,code,phrase', [
    ('This apartment has a private balcony.', 'BALCONY', 'private balcony'),
    ('Enjoy a private south-facing terrace.', 'TERRACE', 'private south-facing terrace'),
    ('Step into your own garden.', 'GARDEN', 'your own garden'),
    ('A private 300-square-foot patio.', 'PATIO', 'private 300-square-foot patio'),
    ('A private landscaped 250 sq ft terrace.', 'TERRACE', 'private landscaped 250 sq ft terrace'),
    ('Features a private rooftop deck.', 'PRIVATE_ROOF_DECK', 'private rooftop deck'),
    ('No fee! Your own sunny balcony.', 'BALCONY', 'Your own sunny balcony'),
    ('Building amenities: roof deck. This apartment has a private balcony.', 'BALCONY', 'private balcony'),
    ('Some units have patios. This unit has a private balcony.', 'BALCONY', 'private balcony'),
    ('Some units have balconies, but this apartment has a private terrace.', 'TERRACE', 'private terrace'),
])
def test_same_capture_literal_corroboration_and_exact_offsets(text, code, phrase):
    source = capture(text, [code])
    original = copy.deepcopy(source)
    result = corroborate([source])
    assert result['private_types'] == [code]
    match = result['evidence'][0]
    assert match['match'] == phrase == text[match['start']:match['end']]
    assert match['body_sha256'] == 'body-hash'
    assert match['raw_listing_sha256'] == 'raw-hash'
    assert match['capture_id'] == 1
    assert source == original


@pytest.mark.parametrize('text,code', [
    ('Views of a private garden.', 'GARDEN'),
    ('Windows overlooking the private garden.', 'GARDEN'),
    ('Private stairs to the patio.', 'PATIO'),
    ('Semi-private terrace.', 'TERRACE'),
    ('Semi private balcony.', 'BALCONY'),
    ('Private deck.', 'PRIVATE_ROOF_DECK'),
    ('A private full floor with a terrace.', 'TERRACE'),
    ('Private outdoor space.', 'TERRACE'),
    ('The building has a private roof deck for residents.', 'PRIVATE_ROOF_DECK'),
    ('Building amenities:\nPrivate roof deck.', 'PRIVATE_ROOF_DECK'),
    ('Community amenities: private garden.', 'GARDEN'),
    ('Some apartments have private balconies.', 'BALCONY'),
    ('One- and two-bedroom units with private patios.', 'PATIO'),
    ('This apartment is among units with private terraces.', 'TERRACE'),
    ('A future private balcony.', 'BALCONY'),
    ('The apartment will have a private patio.', 'PATIO'),
    ('Potential for a private roof deck.', 'PRIVATE_ROOF_DECK'),
    ('No private balcony.', 'BALCONY'),
    ('This unit does not have a private balcony.', 'BALCONY'),
    ('Private balcony is not included.', 'BALCONY'),
    ('Private balcony shared with another apartment.', 'BALCONY'),
    ('Two roof decks and 12,000 square feet of private outdoor space.', 'PRIVATE_ROOF_DECK'),
])
def test_scope_and_unsupported_phrases_stay_unknown(text, code):
    result = corroborate([capture(text, [code])])
    assert result['private_types'] == []
    assert not result['evidence']
    assert result['rejected_evidence'] or result['ambiguous_evidence']


def test_no_cross_capture_join_and_no_new_type_from_text():
    result = corroborate([capture('Private garden.', ['BALCONY']),
                          capture('Outdoor access.', ['GARDEN'], 2)])
    assert result['private_types'] == []
    assert any('no_same_capture_structured_type' in e['reasons'] for e in result['ambiguous_evidence'])
    assert corroborate([capture('Private garden and private balcony.', ['BALCONY'])])['private_types'] == ['BALCONY']


@pytest.mark.parametrize('contrary', ['No balcony.', 'Shared balcony.', 'This unit has a shared balcony.',
                                     'The balcony is not private.', 'Semi-private balcony.'])
def test_contradictory_same_type_blocks_across_captures(contrary):
    result = corroborate([capture('Private balcony and private patio.', ['BALCONY', 'PATIO']),
                          capture(contrary, ['BALCONY'], 2)])
    assert result['private_types'] == ['PATIO']
    assert any(e['reasons'] == ['contradictory_type_evidence'] for e in result['rejected_evidence'])


def test_source_assertions_candidates_and_version_must_reproduce():
    source = capture('Private balcony.')
    for mutate in [lambda s: s['extraction']['assertions'].clear(),
                   lambda s: s['extraction']['description_candidates'].clear(),
                   lambda s: s['extraction'].update(version='invented'),
                   lambda s: s.update(description='A different source description')]:
        changed = copy.deepcopy(source)
        mutate(changed)
        with pytest.raises(ValueError, match='extraction mismatch'):
            corroborate([changed])


def test_nested_description_uses_original_source_path_and_offsets():
    source = capture('A different top level description.')
    source['property_details']['description'] = 'Private balcony.'
    source['extraction'] = extract({'propertyDetails': source['property_details'], 'description': source['description']})
    result = corroborate([source])
    assert result['private_types'] == ['BALCONY']
    assert result['evidence'][0]['source_path'] == '/propertyDetails/description'
    assert result['evidence'][0]['match'] == 'Private balcony'


def test_no_absence_inference_or_mixing_advertisements():
    assert corroborate([])['private_types'] == []
    assert corroborate([capture(None)])['private_types'] == []
    assert corroborate([capture('No outdoor space.', [])])['private_types'] == []
    one, two = capture('Private balcony.'), capture('Private balcony.', capture_id=2)
    two['source_listing_id'] = 'other'
    with pytest.raises(ValueError, match='one analytical advertisement'):
        corroborate([one, two])
    with pytest.raises(ValueError, match='Duplicate'):
        corroborate([one, one])
