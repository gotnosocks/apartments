"""Offline, fail-closed parser for the observed Chelsea rental search template.

A closed pagination chain is evidence of visited pages, never a market census.
No network or archive mutation. Source roles and DOM placements remain separate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from streeteasy_archive.crawler import is_challenge
from streeteasy_archive.extract import _selector, _scripts, canonical_url, flight_text
from streeteasy_archive.flight import decode_records

VERSION = 'chelsea-rental-search-v2'
AREAS = {'/for-rent/chelsea': 'Chelsea', '/for-rent/west-chelsea': 'West Chelsea'}
ROLES = {'FeaturedRentalEdge': 'featured', 'SponsoredRentalEdge': 'infeed', 'OrganicRentalEdge': 'regular'}
FIELDS = ('id', 'urlPath', 'street', 'unit', 'displayUnit', 'price', 'totalMonthlyPrice',
          'netEffectivePrice', 'monthsFree', 'leaseTermMonths', 'areaName', 'status',
          'bedroomCount', 'fullBathroomCount', 'halfBathroomCount', 'furnished',
          'sourceType', 'sourceGroupLabel', 'tier', 'isPremiumHdpEnabled')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _route(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    if (parts.scheme != 'https' or parts.netloc != 'streeteasy.com' or parts.fragment
            or parts.path not in AREAS or set(query) - {'page'}):
        raise ValueError('Unsupported rental search URL or filters')
    raw_page = query.get('page', ['1'])
    if len(raw_page) != 1 or not re.fullmatch(r'[1-9][0-9]*', raw_page[0]):
        raise ValueError('Invalid page query')
    return parts.path, int(raw_page[0])


# These routes name collections, media, or actions rather than individual units.
_RESERVED_UNIT_PATHS = frozenset({'rental', 'sale', 'sales', 'rentals', 'past-sales',
    'past-rentals', 'sold', 'rented', 'for-sale', 'for-rent', 'units', 'history',
    'documents', 'floorplans', 'photos', 'media_gallery', 'export_owner_list',
    'contact', 'messages', 'edit', 'manage'})


def _detail_identity(url, listing_id):
    """Validate a supported detail route without inventing aliases or unit IDs."""
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.netloc != 'streeteasy.com'
            or parts.query or parts.fragment):
        raise ValueError('Unsupported rental detail URL')
    rental = re.fullmatch(r'(?:/building/([A-Za-z0-9_-]+))?/rental/([1-9][0-9]*)', parts.path)
    if rental:
        if rental[2] != listing_id:
            raise ValueError('Rental URL advertisement ID disagrees with source ID')
        return {'kind': 'rental_advertisement', 'advertisement_id': rental[2],
                'building_path': '/building/' + rental[1] if rental[1] else None,
                'canonical_unit_url': None}
    unit = re.fullmatch(r'/building/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)', parts.path)
    if unit and unit[2].lower() not in _RESERVED_UNIT_PATHS:
        return {'kind': 'building_unit', 'advertisement_id': None,
                'building_path': '/building/' + unit[1], 'canonical_unit_url': url}
    raise ValueError('Unsupported rental detail URL or missing unit path')


def _identity_findings(occurrences):
    conflicts, aliases = {}, {}
    for listing_id, observations in sorted(occurrences.items()):
        urls = sorted({o['canonical_url'] for o in observations})
        identities = [_detail_identity(url, listing_id) for url in urls]
        units = sorted({i['canonical_unit_url'] for i in identities if i['canonical_unit_url']})
        buildings = sorted({i['building_path'] for i in identities if i['building_path']})
        evidence = {'canonical_urls': urls, 'canonical_unit_urls': units,
                    'building_paths': buildings, 'occurrences': observations}
        if len(units) > 1 or len(buildings) > 1:
            conflicts[listing_id] = {**evidence, 'reasons':
                (['multiple_canonical_unit_urls'] if len(units) > 1 else []) +
                (['multiple_building_paths'] if len(buildings) > 1 else [])}
        elif len(urls) > 1:
            aliases[listing_id] = {**evidence,
                'interpretation': 'Compatible source-bound advertisement URL forms. '
                'No inferred physical-unit merge or canonical URL replacement.'}
    return conflicts, aliases


def _walk(value, path):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            yield from _walk(item, path + '/' + str(key).replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, path + '/' + str(index))


def parse_page(body: bytes, url: str, *, source_clock=None):
    """Return source-bound page/card observations or raise without partial success.

    Requires the observed ordered Flight listings edges as an independent check
    on primary DOM cards. Unknown future templates need review, not a fallback.
    ``source_clock`` is supplied provenance, not an inferred listing update time.
    """
    path, page_number = _route(url)
    if is_challenge(body):
        raise ValueError('Challenge body')
    selector = _selector(body)
    mains = selector.css('main')
    if len(mains) != 1:
        raise ValueError('Missing or ambiguous main container')
    main = mains[0]
    lists = main.css('ul[class*="ListingCardsList_listContainer"]')
    headings = main.css('h1')
    pagination = main.css('ul[class*="Pagination_paginationList"]')
    if len(lists) != 1 or len(headings) != 1 or len(pagination) != 1:
        raise ValueError('Missing or ambiguous primary search structure')
    h1 = headings[0].xpath('normalize-space(string(.))').get()
    match = re.fullmatch(r'([\d,]+) ' + re.escape(AREAS[path]) +
                        r', Manhattan NY Apartments for Rent(?: - Page ([1-9]\d*))?', h1)
    if not match or int(match[2] or 1) != page_number:
        raise ValueError('H1 and source route disagree')
    total = int(match[1].replace(',', ''))
    current = pagination.css('[class*="Pagination_currentPage"]::text').getall()
    if current != [str(page_number)]:
        raise ValueError('Pagination current page disagrees')
    dom_cards = lists[0].css('[data-testid="listing-card"]')
    if not dom_cards or total <= 0:
        raise ValueError('Empty-result template not established')

    scripts = _scripts(selector)
    records = decode_records(flight_text(scripts))
    roots = [(f'/flight_records/{key}', value) for key, value in records.items()]
    roots += [(f'/scripts/{index}/json', item['json']) for index, item in enumerate(scripts) if 'json' in item]
    candidates = [(p, obj) for root_path, root in roots for p, obj in _walk(root, root_path)
                  if obj.get('listingType') == 'rentals' and isinstance(obj.get('listings'), list)
                  and isinstance(obj.get('searchMetadata'), dict)]
    if len(candidates) != 1:
        raise ValueError('Missing or ambiguous ordered rental edge container')
    source_path, container = candidates[0]
    if container['searchMetadata'].get('totalResults') != total:
        raise ValueError('Structured total and H1 disagree')
    edges = container['listings']
    if len(edges) != len(dom_cards):
        raise ValueError('Ordered source edges and DOM card counts disagree')
    cards = []
    for index, (dom, edge) in enumerate(zip(dom_cards, edges)):
        anchors = dom.css('a[class*="addressTextAction"]')
        if len(anchors) != 1 or not anchors[0].attrib.get('href'):
            raise ValueError('Missing or ambiguous card address link')
        href = anchors[0].attrib['href']
        query = parse_qs(urlsplit(href).query, keep_blank_values=True)
        if set(query) - {'featured', 'infeed'} or any(value != ['1'] for value in query.values()) or len(query) > 1:
            raise ValueError('Unknown or conflicting placement query')
        placement = 'featured' if 'featured' in query else 'infeed' if 'infeed' in query else 'regular'
        role = edge.get('__typename') if isinstance(edge, dict) else None
        node = edge.get('node') if isinstance(edge, dict) else None
        if ROLES.get(role) != placement or not isinstance(node, dict):
            raise ValueError('Source role and DOM placement disagree or unresolved node')
        canonical = canonical_url(href, url)
        if not canonical or canonical != canonical_url(node.get('urlPath', ''), url):
            raise ValueError('Ordered source and DOM card URLs disagree')
        listing_id = node.get('id')
        if (not isinstance(listing_id, str) or not re.fullmatch(r'[1-9]\d*', listing_id)
                or any(not isinstance(node.get(k), str) or not node[k] or node[k].startswith('$')
                       for k in ('street', 'areaName', 'status'))
                or isinstance(node.get('price'), bool) or not isinstance(node.get('price'), (int, float))
                or not 0 < node['price'] < float('inf')):
            raise ValueError('Missing or invalid source identity/address/price/area')
        identity = _detail_identity(canonical, listing_id)
        edge_path = f'{source_path}/listings/{index}'
        cards.append({'position': index + 1, 'href': href, 'href_query': query,
                      'canonical_url': canonical, 'detail_url_identity': identity, 'address_text': anchors[0].xpath('normalize-space(string(.))').get(),
                      'placement': placement, 'source_role': role, 'source_listing_id': listing_id,
                      'in_chelsea_scope': node['areaName'] in AREAS.values(),
                      'source_fields': {key: node[key] for key in FIELDS if key in node},
                      'source_reference': {'edge_path': edge_path, 'edge_sha256': fingerprint(edge),
                                           'node_path': edge_path + '/node', 'node_sha256': fingerprint(node),
                                           'dom_card_index': index}})
    links = []
    for anchor in pagination.css('a'):
        href = anchor.attrib.get('href', '')
        target = urljoin(url, href)
        target_path, number = _route(target)
        if target_path != path:
            raise ValueError('Pagination leaves source route')
        label = anchor.xpath('normalize-space(string(.))').get()
        relation = anchor.attrib.get('aria-labelledby')
        if relation not in (None, 'next-arrow-label', 'previous-arrow-label'):
            raise ValueError('Unknown pagination relation')
        if relation is None and (not label.isdigit() or int(label) != number):
            raise ValueError('Numeric pagination label disagrees')
        links.append({'href': href, 'url': target, 'page': number, 'text': label, 'relation': relation})
    next_links = [link for link in links if link['relation'] == 'next-arrow-label']
    previous = [link for link in links if link['relation'] == 'previous-arrow-label']
    if (len(next_links) > 1 or len(previous) != int(page_number > 1)
            or (next_links and next_links[0]['page'] != page_number + 1)
            or (previous and previous[0]['page'] != page_number - 1)):
        raise ValueError('Invalid next/previous sequence')
    max_displayed = max([page_number] + [link['page'] for link in links])
    if not next_links and max_displayed > page_number:
        raise ValueError('Next missing before displayed later page')
    return {'version': VERSION, 'source_url': url, 'source_clock': source_clock,
            'body_sha256': hashlib.sha256(body).hexdigest(), 'seed_path': path, 'page': page_number,
            'h1': h1, 'displayed_total': total, 'cards': cards,
            'pagination': {'links': links, 'next_url': next_links[0]['url'] if next_links else None,
                           'max_displayed_page': max_displayed, 'terminal_observed': not next_links},
            'ordered_page_signature': fingerprint([(c['source_listing_id'], c['canonical_url'], c['placement']) for c in cards]),
            'ordered_regular_signature': fingerprint([(c['source_listing_id'], c['canonical_url']) for c in cards if c['placement'] == 'regular']),
            'search_source_reference': {'path': source_path, 'searchMetadata': container['searchMetadata'],
                                        'experiments': container.get('experiments'),
                                        'sort_controls': [{'text': e.xpath('normalize-space(string(.))').get(),
                                                           'attributes': dict(e.attrib)}
                                                          for e in main.css('[data-testid="sort-by-trigger-id"]')],
                                        'ordering_context': [{'path': p + '/' + key, 'value': value}
                                                             for p, obj in _walk(container, source_path)
                                                             for key, value in obj.items()
                                                             if key in ('sorting', 'sort_option_txt', 'isPerEnhancedListingInsightsEnabled')],
                                        'edge_container_sha256': fingerprint(edges)}}


def coverage(pages):
    """Summarize observed pages; never equate row sums with inventory coverage."""
    pages = list(pages)
    groups = defaultdict(list)
    for page in pages:
        if page.get('version') != VERSION:
            raise ValueError('Unsupported page parser version')
        groups[page['seed_path']].append(page)
    identity_occurrences = defaultdict(list)
    for page in sorted(pages, key=lambda p: (p['seed_path'], p['page'])):
        for card in page['cards']:
            identity_occurrences[card['source_listing_id']].append({
                'seed_path': page['seed_path'], 'page': page['page'], 'position': card['position'],
                'placement': card['placement'], 'canonical_url': card['canonical_url'],
                'source_url': page['source_url'], 'body_sha256': page['body_sha256'],
                'source_clock': page['source_clock'], 'source_reference': card['source_reference']})
    conflicts, aliases = _identity_findings(identity_occurrences)
    result = {}
    seed_ids = {}
    for seed, group in sorted(groups.items()):
        group = sorted(group, key=lambda p: p['page'])
        if len({p['page'] for p in group}) != len(group):
            raise ValueError('Choose one capture per seed/page explicitly')
        occurrences = defaultdict(list)
        all_occurrences = defaultdict(list)
        for page in group:
            for card in page['cards']:
                where = {'page': page['page'], 'position': card['position'], 'placement': card['placement']}
                all_occurrences[card['source_listing_id']].append(where)
                if card['placement'] == 'regular':
                    occurrences[card['source_listing_id']].append(where)
        numbers = [p['page'] for p in group]
        chain = bool(numbers and numbers == list(range(1, numbers[-1] + 1))
                     and group[-1]['pagination']['terminal_observed']
                     and all(p['pagination']['next_url'] and _route(p['pagination']['next_url'])[1] == p['page'] + 1
                             for p in group[:-1]))
        seed_ids[seed] = set(occurrences)
        result[seed] = {'pages': numbers, 'pagination_chain_closed': chain,
                        'market_census_established': False, 'displayed_totals': sorted({p['displayed_total'] for p in group}),
                        'regular_occurrences': sum(map(len, occurrences.values())), 'regular_unique_ids': len(occurrences),
                        'listing_identity_conflicts': {key: val for key, val in conflicts.items() if key in all_occurrences},
                        'compatible_advertisement_url_aliases': {key: val for key, val in aliases.items() if key in all_occurrences},
                        'regular_duplicates': {key: val for key, val in sorted(occurrences.items()) if len(val) > 1 and key not in conflicts},
                        'all_placement_duplicates': {key: val for key, val in sorted(all_occurrences.items()) if len(val) > 1 and key not in conflicts},
                        'placement_counts': dict(Counter(c['placement'] for p in group for c in p['cards'])),
                        'out_of_scope_cards': [{'page': p['page'], 'card': c} for p in group for c in p['cards'] if not c['in_chelsea_scope']],
                        'page_signatures': [{'page': p['page'], 'body_sha256': p['body_sha256'],
                                             'ordered_page_signature': p['ordered_page_signature'],
                                             'ordered_regular_signature': p['ordered_regular_signature']} for p in group]}
    return {'version': VERSION, 'seeds': result,
            'listing_identity_conflicts': conflicts, 'compatible_advertisement_url_aliases': aliases,
            'regular_union_ids': sorted(set().union(*seed_ids.values())) if seed_ids else [],
            'cross_seed_regular_overlap_ids': sorted(set.intersection(*seed_ids.values())) if len(seed_ids) > 1 else [],
            'interpretation': 'Visited-page evidence only. Repeated organic listings and changing ordering can leave unique inventory coverage unresolved even when counts match.'}
