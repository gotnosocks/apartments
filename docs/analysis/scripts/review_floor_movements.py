"""Publish manually read findings for the accepted floor-fit movement cases."""
import argparse
import hashlib
import json
from pathlib import Path

from apartments.corrections import canonical
from apartments.research_pipeline import _verified_bundle, digest, publish_bundle


# Each entry follows a reading of every distinct full own-capture description.
# Quotes below are checked against those descriptions, never another unit's ad.
REVIEWS = {
    '4601585': ('label_only_luxury_views', '31B supports the declared label proxy. Prose confirms size and room composition, but not a separate numeric floor. River views, corner exposures and newly finished interiors can contribute to this luxury outlier.', ['Step into Residence 31B', 'northern and western exposures'], ['unit_view_and_finish_features']),
    '1192015': ('penthouse_floor_unknown', 'PHC supplies no numeric floor. The common building template starts residences at 26; that is not the floor of this penthouse. Its fitted-price decrease accompanies the lower building contribution.', ['apartments starting on the 26th floor.'], ['penthouse_floor_evidence', 'conditional_floor_missingness']),
    '1177674': ('penthouse_floor_unknown_alias_lead', 'PHB supplies no numeric floor. Its canonical URL ends ph-b, while ad1893537 ends phb with the same displayed label. This is an identity-review lead, not sufficient evidence to merge units or copy bathroom counts across time.', ['apartments starting on the 26th floor.'], ['penthouse_floor_evidence', 'unit_url_alias_review']),
    '1177683': ('penthouse_floor_unknown_alias_lead', 'PHA supplies no numeric floor. Its canonical URL ends ph-a, while ad2894491 ends pha with the same displayed label. Review identity before pooling their unit effects; do not merge solely from label similarity.', ['apartments starting on the 26th floor.'], ['penthouse_floor_evidence', 'unit_url_alias_review']),
    '775133': ('penthouse_class_floor_claim', 'PH4 is correctly not parsed as floor4. The own advertisement markets three-bedroom penthouse residences with 53rd-floor views and private terraces. This is a useful class-specific advertised-floor lead, but does not establish a building-wide penthouse mapping or physical height.', ['Spectacular 53rd Floor views of the Hudson River,', 'Large private terraces'], ['reviewed_penthouse_floor_claim', 'private_outdoor_features']),
    '4549241': ('label_only_luxury_views', '31A supports the label proxy. Source confirms four bedrooms and size, with river views, corner exposures and four en suites plus a powder room. No independent numeric floor assertion appears.', ['Step into Residence 31A', 'southern and western exposures'], ['unit_view_and_finish_features']),
    '1454942': ('penthouse_floor_unknown', 'PHD supplies no numeric floor. The building-template starting floor26 is not an apartment floor. Missing floor and penthouse-specific features can remain in the unit effect or residual.', ['apartments starting on the 26th floor.'], ['penthouse_floor_evidence', 'conditional_floor_missingness']),
    '2521833': ('label_only_renovated_corner_loft', '17N supports the label proxy; no independent literal floor is stated. Gut renovation, loft proportions, corner exposures and river views are explicit. Furnished or unfurnished availability needs price-specific treatment, not a single inferred surcharge.', ['Residence 17N', 'gut renovated interiors.', 'Available furnished or unfurnished'], ['private_quality_and_view_features', 'furnishing_price_basis']),
    '3973940': ('label_proxy_multilevel_penthouse', '10C is a base advertised-label proxy for a duplex penthouse, not the physical floor of every room. Private elevator access, extensive terraces and a private rooftop pool are explicit omitted distinctions from an ordinary single-level apartment.', ['duplex three-bedroom', 'a rooftop terrace with its own private pool.'], ['multilevel_and_private_outdoor_features']),
    '4169574': ('penthouse_number_not_floor', 'PH2 is a penthouse identity, not floor2. The home has two levels, terraces and private elevator entrances; the building-wide 12-floor count does not identify its unit floor. Sale-style template wording also warrants source-context review for this rental ad.', ['Penthouse Two at ABI Chelsea', 'spread over 12 floors'], ['penthouse_floor_evidence', 'multilevel_and_private_outdoor_features', 'listing_template_scope']),
    '4892020': ('whole_townhouse_not_single_floor', 'The advertised home spans four stories plus a finished basement. Keeping a single unit floor unknown is appropriate; neither the primary suite on the second floor nor building height describes the whole rental. Whole-home type, garden and multilevel access need separate representation.', ['Four-story Greek Revival townhouse', 'Finished basement with storage'], ['whole_building_and_multilevel_features']),
    '2021775': ('duplex_furnishing_coverage', '18D supports an advertised base-floor proxy. First and second level refer to the interior duplex, not building floors1 and2. The source explicitly calls this a furnished rental while the analytical furnished flag is unknown; terrace and duplex attributes are also not separated by floor alone.', ['This furnished rental', 'Both bedrooms on the second level'], ['furnishing_extractor_coverage', 'multilevel_and_private_outdoor_features']),
    '1893537': ('bathroom_conflict_and_alias_lead', 'Structured total4.5/full4/half1 conflicts with own prose specifying three and a half bathrooms and three bedroom en suites. Keep the conflict unresolved pending correction review; do not choose a value from fitted rent. The URL phb versus ph-b in ad1177674 is a separate identity lead. The Cloud Lounge on54 is shared space, not this unit floor.', ['this three bedroom three and half bathroom apartment.', 'Cloud Lounge, on the 54th floor'], ['bathroom_source_conflict', 'unit_url_alias_review', 'penthouse_floor_evidence']),
    '1262316': ('label_only_private_terrace', '18C supports the label proxy. Source confirms size, two bedrooms and2.5 baths. Private terrace, fireplace and multiple landmark/water exposures can account for luxury variation without changing its floor label.', ['285-square foot terrace.', 'WOOD BURNING FIREPLACE.'], ['private_outdoor_and_view_features']),
    '4608899': ('label_only_low_floor_terrace', '5C supports the label proxy; the source does not independently state floor5. The large private terrace and river views show why a low listed floor does not imply ordinary low-floor amenities.', ['a 472 SF terrace.', 'stunning Hudson River views'], ['private_outdoor_and_view_features']),
    '4117017': ('qualitative_high_floor', '35A supports the label proxy. High-floor prose is qualitatively compatible but not an independent numeric measurement. Private balcony, landmark views and two en suites are explicit.', ['high-floor residence', 'a private balcony'], ['private_outdoor_and_view_features']),
    '1328434': ('label_only_flexible_term', '17A supports the label proxy. No independent numeric floor appears; radiant floor heating is a finish. The source offers short or long terms, so price-specific tenancy terms need evidence rather than assuming a standard lease or short-term premium.', ['available short term or long term.'], ['lease_term_and_finish_features']),
    '2616876': ('penthouse_floor_unknown', 'PH3C does not mean floor3. The description says one of the highest floors but supplies no number. Two terraces, high ceilings, fireplace and private storage are specific features beyond the unknown floor.', ['one of the highest floors in Chelsea', '2 terraces and 12 ft ceilings'], ['penthouse_floor_evidence', 'private_outdoor_and_finish_features']),
    '3091654': ('explicit_floor_agrees_net_gross_conflict', 'The explicit floor17 agrees with the source. Target4040 matches the described net rent, while the same lease-assignment text states gross4446 and a tenant incentive. Review the own dated price event before changing the target; do not replace it with the model estimate. Converted two-bedroom layout and lease assignment also merit separate representation.', ['situated on the 17th floor', 'bringing the net rent down to $4040 (actually gross rent is $4446)'], ['own_price_basis_review', 'converted_layout_and_lease_assignment']),
    '2894491': ('penthouse_floor_unknown_alias_lead', 'PHA remains without a numeric floor; the starting-floor26 template is building-wide. URL pha versus ph-a in ad1177683 warrants identity review without assuming a historical room-count change or automatically merging.', ['apartments starting on the 26th floor.'], ['penthouse_floor_evidence', 'unit_url_alias_review']),
    '1554357': ('explicit_floor_agrees', 'Unit label1404 is not newly parsed by this rule; existing explicit floor14 agrees with own prose. Renovation, south exposure and skyline views are additional source characteristics, not floor corrections.', ['located on the 14th Floor', 'coveted south facing apartment.'], ['unit_view_and_renovation_features']),
    '872357': ('label_only_missing_area', '3E supports the label proxy. The analytical area is missing but the own description explicitly states1,356SF. The source also describes a private planted terrace and11-foot ceilings. Review the literal area for enrichment rather than estimating it from price.', ['1,356SF apartment', 'large east facing planted terrace.'], ['area_extractor_coverage', 'private_outdoor_and_finish_features']),
    '3853654': ('label_only_explicit_unfurnished_price', '33A supports the label proxy. The target14000 agrees with the own unfurnished quote; the furnished option is separately15000. No net/gross repair follows. Private terrace and view quality remain distinct from floor.', ['FURNISHED ($15000) or UNFURNISHED for $14000.'], ['furnishing_price_options', 'private_outdoor_and_view_features']),
    '5035970': ('numeric_label_needs_building_scheme', 'Numeric label1701 is intentionally not parsed as17. The text identifies the -01 line and a Junior Penthouse but does not independently state floor17. A validated building-specific numbering scheme could recover this; it must not be guessed from the residual.', ['Residence 1701', '"-01" line Junior Penthouses'], ['building_specific_numeric_label_scheme', 'unit_view_and_finish_features']),
    '2221174': ('numeric_label_unresolved', 'Numeric label37056 is ambiguous under the declared rule, and the own description supplies no literal floor. Do not guess37 or370. Corner exposures, ceiling height and luxury features do not resolve numbering.', ['Corner 4 Bedroom, 3.5 Bathroom apartment'], ['building_specific_numeric_label_scheme']),
    '1015598': ('letter_label_floor_unknown', 'Single-letter C does not identify a numeric floor. Homes starting26 is a building-wide range, not this unit floor. This example illustrates how missing floor and a lower building effect can reallocate the unit contribution.', ['Homes start on the 26th floor'], ['building_specific_label_scheme', 'conditional_floor_missingness']),
    '2038417': ('explicit_floor_agrees_included_utilities', 'Existing explicit floor17 agrees with own prose and label17B. Included utilities are part of the advertised offer; they should be separated from base rent for user total-cost analysis, not used to alter floor.', ['APARTMENT on the 17th floor', 'Utilities are included in the price'], ['included_utilities_price_scope']),
    '4798052': ('label_only_high_floor_with_fees', '52B supports the label proxy and passes the captured building-count screen. Starting26 is a building template, not a contradictory unit floor. Mandatory monthly amenity fees are separate from base asking rent; no specific unit-floor prose appears.', ['Amenity Use Fee $135'], ['recurring_cost_scope', 'conditional_floor_missingness']),
    '4933515': ('label_only_exposure_conflict', '34E supports the label proxy, with qualitative high-floor prose. The headline says south/west, while a later sentence says north: do not silently resolve the exposure conflict. A huge private terrace and421a surcharges require their own features/cost treatment.', ['South/West Exposures', 'Featuring north exposures', '421a surcharges apply.'], ['window_exposure_conflict', 'private_outdoor_and_recurring_costs']),
    '4934050': ('label_only_high_floor_with_fees', '52I supports the label proxy. Building-template starting26 is not its literal floor. Monthly amenity and utility costs are separately stated; the unit contribution movement is not a change in the actual asking rent.', ['Amenity Use Fee - $135'], ['recurring_cost_scope', 'conditional_floor_missingness']),
    '4952256': ('label_only_high_floor_with_fees', '52A supports the label proxy. Building-template starting26 is not its literal floor. Monthly amenity and utility costs are separately stated; unit/building attribution changes should not be read as source price corrections.', ['Amenity Use Fee - $135'], ['recurring_cost_scope', 'conditional_floor_missingness']),
    '5075750': ('letter_prefix_scheme_unresolved', 'C46 does not match the declared digit-prefix rule. The source gives generic apartment/building features but no independent floor46. A building-specific letter-prefix numbering review is needed; no floor is assigned from price.', ['APARTMENT FEATURES:', 'Rooftop Deck with BBQ Grill'], ['building_specific_letter_prefix_scheme']),
    '5089496': ('label_only_building_template', '2A supports the label proxy. The32-story statement describes the building, not this apartment. Recurring amenity/utility fees are separate cost components, and the building-template views do not establish unit-specific exposure.', ['The 32-story luxury apartment building', 'Amenity Use Fee'], ['listing_template_scope', 'recurring_cost_scope']),
}


def run(inputs, output, as_of):
    inputs = Path(inputs)
    manifest, files = _verified_bundle(inputs, retain={'cases.jsonl'})
    if manifest['version'] != 'accepted-floor-fit-movement-source-review-inputs-v1':
        raise ValueError('Unexpected movement-review inputs')
    cases = [json.loads(line) for line in files['cases.jsonl'].decode().splitlines()]
    if {c['observation']['source_listing_id'] for c in cases} != set(REVIEWS):
        raise ValueError('Manual review membership differs')
    decisions = []
    for case in cases:
        row = case['observation']
        status, note, quotes, leads = REVIEWS[row['source_listing_id']]
        spans = []
        for quote in quotes:
            matched = False
            for capture in case['descriptions']:
                start = (capture['description'] or '').find(quote)
                if start < 0:
                    continue
                matched = True
                spans.append({k: capture[k] for k in ('capture_id', 'raw_listing_sha256', 'body_sha256', 'description_sha256')} |
                             {'start': start, 'end': start+len(quote), 'literal': quote})
            if not matched:
                raise ValueError(f'Quote not in own capture: {row["source_listing_id"]}: {quote}')
        decisions.append({k: row[k] for k in ('audit_id', 'unit_id', 'source_listing_id', 'building', 'canonical_unit_url')} |
            {'source_row_sha256': hashlib.sha256(canonical(row).encode()).hexdigest(),
             'status': status, 'note': note, 'quotes': spans, 'followups': leads,
             'reviewed_at': as_of, 'reviewer': 'Codex manual reading of every distinct full own-capture description',
             'applied_correction': False})
    return publish_bundle(output, {
        'decisions.jsonl': ''.join(canonical(d)+'\n' for d in decisions),
        Path(__file__).name: Path(__file__).read_text()}, {
        'version': 'accepted-floor-fit-movement-manual-review-v1',
        'inputs_manifest_sha256': digest(inputs/'complete.json'), 'reviewed_at': as_of,
        'cases': len(decisions), 'source_counts_or_prices_changed': False,
        'interpretation': 'Development source review selected by model movements. Findings identify source conflicts and research leads, not causal attribution, verified physical floors, or a population accuracy estimate. No unit merges, numerical corrections, or model changes applied.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('inputs', 'output', 'as-of'):
        parser.add_argument('--'+name, required=True)
    print(canonical(run(**vars(parser.parse_args()))))
