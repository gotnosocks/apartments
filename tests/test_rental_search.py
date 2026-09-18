import json
from copy import deepcopy

import pytest

from apartments.rental_search import coverage, parse_page

URL = 'https://streeteasy.com/for-rent/chelsea'


def fixture(*, page=1, last=2, ids=('123', '124'), roles=None, total=2, area='Chelsea'):
    roles = roles or ['OrganicRentalEdge'] * len(ids)
    edges, cards = [], []
    for ident, role in zip(ids, roles):
        node = {'id': ident, 'urlPath': '/building/example/' + ident, 'street': '1 Main Street',
                'unit': '#' + ident, 'areaName': area, 'status': 'ACTIVE', 'price': 5000}
        edge = {'node': node, '__typename': role}
        edges.append(edge)
        suffix = {'FeaturedRentalEdge': '?featured=1', 'SponsoredRentalEdge': '?infeed=1'}.get(role, '')
        cards.append(f'<li data-testid="listing-card"><a class="addressTextAction" href="{node["urlPath"]}{suffix}">1 Main #{ident}</a></li>')
    data = {'listingType': 'rentals', 'listings': edges, 'searchMetadata': {'totalResults': total}}
    heading = f'{total} Chelsea, Manhattan NY Apartments for Rent' + (f' - Page {page}' if page > 1 else '')
    links = f'<span class="Pagination_currentPage">{page}</span>'
    if page > 1:
        links += f'<a aria-labelledby="previous-arrow-label" href="/for-rent/chelsea?page={page - 1}">Previous Page</a>'
    if page < last:
        links += f'<a href="/for-rent/chelsea?page={last}">{last}</a><a aria-labelledby="next-arrow-label" href="/for-rent/chelsea?page={page + 1}">Next Page</a>'
    body = f'<main><h1>{heading}</h1><ul class="ListingCardsList_listContainer">{"".join(cards)}</ul><ul class="Pagination_paginationList">{links}</ul></main>'
    return body, data


def encode(body, data):
    stream = 'a:' + json.dumps(data) + '\n'
    return (body + '<script>self.__next_f.push(' + json.dumps([1, stream]) + ')</script>').encode()


def test_roles_source_fields_and_global_recommendation_exclusion():
    html, data = fixture(ids=('123', '124', '125'), roles=['FeaturedRentalEdge', 'SponsoredRentalEdge', 'OrganicRentalEdge'])
    data['listings'][1]['node']['areaName'] = 'Hudson Yards'
    html = '<nav><a href="/building/unrelated/1">Recommendation</a></nav>' + html
    page = parse_page(encode(html, data), URL, source_clock={'started_at': '2026-09-18T00:00:00Z'})
    assert [c['placement'] for c in page['cards']] == ['featured', 'infeed', 'regular']
    assert page['cards'][0]['href_query'] == {'featured': ['1']}
    assert '?' not in page['cards'][0]['canonical_url']
    assert page['cards'][1]['in_chelsea_scope'] is False
    assert page['cards'][2]['source_reference']['node_path'] == '/flight_records/a/listings/2/node'
    assert page['cards'][2]['source_fields']['price'] == 5000
    assert page == parse_page(encode(html, data), URL, source_clock={'started_at': '2026-09-18T00:00:00Z'})


def test_duplicate_organic_ids_prevent_count_based_census_claim():
    p1 = parse_page(encode(*fixture(ids=('123', '124'), total=4)), URL)
    p2 = parse_page(encode(*fixture(page=2, ids=('124', '125'), total=4)), URL + '?page=2')
    result = coverage([p2, p1])['seeds']['/for-rent/chelsea']
    assert result['pagination_chain_closed'] is True
    assert result['regular_occurrences'] == 4
    assert result['regular_unique_ids'] == 3
    assert result['market_census_established'] is False
    assert list(result['regular_duplicates']) == ['124']
    assert len(result['page_signatures']) == 2
    with pytest.raises(ValueError, match='one capture'):
        coverage([p1, p1])
    assert coverage([p2])['seeds']['/for-rent/chelsea']['pagination_chain_closed'] is False


@pytest.mark.parametrize('mutation,match', [
    (lambda h,d: (h.replace('<main>', '<main></main><main>'),d), 'main container'),
    (lambda h,d: (h.replace('ListingCardsList_listContainer', 'unknown'),d), 'primary search structure'),
    (lambda h,d: (h.replace('<h1>', '<h1>999 '),d), 'H1'),
    (lambda h,d: (h.replace('Pagination_currentPage">1', 'Pagination_currentPage">2'),d), 'current page'),
    (lambda h,d: (h.replace('next-arrow-label', 'mystery-arrow'),d), 'relation'),
    (lambda h,d: (h.replace('href="/building/example/123"', 'href="/building/example/123?featured=1"'),d), 'role'),
    (lambda h,d: (h.replace('href="/building/example/123"', 'href="/building/example/123?featured=1&infeed=1"'),d), 'placement'),
    (lambda h,d: (h.replace('/building/example/123', '/building/different/123'),d), 'URLs disagree'),
    (lambda h,d: ('<title>Access Denied</title>'+h,d), 'Challenge'),
])
def test_rejects_ambiguous_or_mismatched_sources(mutation, match):
    h,d = mutation(*fixture())
    with pytest.raises(ValueError, match=match):
        parse_page(encode(h,d), URL)


@pytest.mark.parametrize('mutation,match', [
    (lambda d: d['searchMetadata'].update(totalResults=3), 'total'),
    (lambda d: d['listings'].pop(), 'counts disagree'),
    (lambda d: d['listings'][0]['node'].update(price=float('nan')), 'identity'),
    (lambda d: d['listings'][0]['node'].update(areaName='$abc'), 'identity'),
    (lambda d: d['listings'][0].update(__typename='EnhancedRentalEdge'), 'role'),
    (lambda d: d.update(other=deepcopy(d)), 'ambiguous ordered'),
])
def test_rejects_structured_ambiguity(mutation, match):
    h,d = fixture(); mutation(d)
    with pytest.raises(ValueError, match=match):
        parse_page(encode(h,d), URL)


def test_missing_next_is_not_terminal_when_later_page_visible():
    h,d = fixture()
    h = h.replace('<a aria-labelledby="next-arrow-label" href="/for-rent/chelsea?page=2">Next Page</a>', '')
    with pytest.raises(ValueError, match='Next missing'):
        parse_page(encode(h,d), URL)


@pytest.mark.parametrize('url', [URL+'?page=0', URL+'?page=2&page=3', URL+'?sort_by=price', URL.replace('https:', 'http:'), URL.replace('chelsea', 'tribeca')])
def test_unknown_route_contract_rejected(url):
    with pytest.raises(ValueError):
        parse_page(encode(*fixture()), url)


def replace_card_url(html, data, index, target):
    old = data['listings'][index]['node']['urlPath']
    # A test fixture may intentionally repeat one URL; edit this occurrence only.
    marker = 'href="' + old
    start = -1
    for _ in range(sum(e['node']['urlPath'] == old for e in data['listings'][:index]) + 1):
        start = html.index(marker, start + 1)
    html = html[:start] + html[start:].replace(marker, 'href="' + target, 1)
    data['listings'][index]['node']['urlPath'] = target
    return html, data


@pytest.mark.parametrize('target', ['/', '/sale/123', '/sale/999', '/building/example',
    '/rental/999', '/building/example/rental/999', '/building/example/sale/123',
    '/building/example/rentals', '/building/example/history', '/building/example/media_gallery',
    '/building/example/sale', '/building/example/rental', '/building/example/123/photos',
    '/rental/123-arbitrary', '/building/example/123?foo=bar'])
def test_matching_dom_and_source_url_is_insufficient(target):
    h,d = replace_card_url(*fixture(), 0, target)
    with pytest.raises(ValueError):
        parse_page(encode(h,d), URL)


@pytest.mark.parametrize('target,kind', [('/rental/123', 'rental_advertisement'),
    ('/building/example/rental/123', 'rental_advertisement'),
    ('/building/example/1d', 'building_unit')])
def test_supported_detail_shapes(target, kind):
    h,d = replace_card_url(*fixture(), 0, target)
    card = parse_page(encode(h,d), URL)['cards'][0]
    assert card['detail_url_identity']['kind'] == kind
    assert card['canonical_url'] == 'https://streeteasy.com' + target


@pytest.mark.parametrize('same_page', [True, False])
def test_conflicting_unit_urls_are_not_ordinary_duplicates(same_page):
    if same_page:
        h,d = fixture(ids=('123', '123'))
        h,d = replace_card_url(h,d,1,'/building/example/other-unit')
        pages = [parse_page(encode(h,d), URL)]
    else:
        p1 = parse_page(encode(*fixture()), URL)
        h,d = replace_card_url(*fixture(page=2),0,'/building/example/other-unit')
        pages = [p1,parse_page(encode(h,d),URL+'?page=2')]
    result = coverage(pages)
    conflict = result['listing_identity_conflicts']['123']
    assert conflict['reasons'] == ['multiple_canonical_unit_urls']
    assert len(conflict['canonical_unit_urls']) == 2
    assert len(conflict['occurrences']) == 2
    assert all(o['body_sha256'] and o['source_reference']['node_path'] for o in conflict['occurrences'])
    seed = result['seeds']['/for-rent/chelsea']
    assert '123' not in seed['regular_duplicates']
    assert '123' not in seed['all_placement_duplicates']
    assert seed['listing_identity_conflicts']['123'] == conflict


def test_cross_seed_identity_conflicts_keep_both_source_bindings():
    p1 = parse_page(encode(*fixture()), URL)
    h,d = replace_card_url(*fixture(),0,'/building/other/123')
    h = h.replace('2 Chelsea, Manhattan', '2 West Chelsea, Manhattan').replace('/for-rent/chelsea', '/for-rent/west-chelsea')
    p2 = parse_page(encode(h,d), URL.replace('chelsea','west-chelsea'))
    result = coverage([p1,p2])
    conflict = result['listing_identity_conflicts']['123']
    assert set(conflict['reasons']) == {'multiple_canonical_unit_urls','multiple_building_paths'}
    assert {o['seed_path'] for o in conflict['occurrences']} == {'/for-rent/chelsea','/for-rent/west-chelsea'}
    assert all('123' in seed['listing_identity_conflicts'] for seed in result['seeds'].values())


@pytest.mark.parametrize('rental_url', ['/rental/123', '/building/example/rental/123'])
def test_source_bound_advertisement_alias_is_compatible_not_unit_conflict(rental_url):
    p1 = parse_page(encode(*fixture()), URL)
    h,d = replace_card_url(*fixture(page=2),0,rental_url)
    p2 = parse_page(encode(h,d),URL+'?page=2')
    result = coverage([p1,p2])
    assert result['listing_identity_conflicts'] == {}
    alias = result['compatible_advertisement_url_aliases']['123']
    assert alias['canonical_unit_urls'] == ['https://streeteasy.com/building/example/123']
    assert len(alias['occurrences']) == 2
    assert p2['cards'][0]['canonical_url'] == 'https://streeteasy.com' + rental_url
    assert '123' in result['seeds']['/for-rent/chelsea']['regular_duplicates']


def test_matching_rental_id_does_not_erase_conflicting_building_scope():
    p1 = parse_page(encode(*fixture()), URL)
    h,d = replace_card_url(*fixture(page=2),0,'/building/other/rental/123')
    result = coverage([p1,parse_page(encode(h,d),URL+'?page=2')])
    assert result['listing_identity_conflicts']['123']['reasons'] == ['multiple_building_paths']
    assert result['compatible_advertisement_url_aliases'] == {}
