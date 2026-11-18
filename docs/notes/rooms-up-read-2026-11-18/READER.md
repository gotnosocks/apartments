# Reader brief

You are a seasoned New York City rental broker. Your group file is a JSON list of about 20
rental ads. Each ad has its text, its coded fields (asks included), its amenity tags, and
`unit_earlier_ads`: the same apartment's earlier ads with dates and asks.
`previous_ad_description` is the text of the most recent earlier ad.

Some of these ads ask much less than a pricing model expected and some are ordinary. You are
not told which. For every ad, read the whole description, every coded field and the earlier
ads before writing anything. Then answer:

1. `low_vs_history`: is this ask clearly lower than the unit's own earlier asks, after
   allowing for the dates? One of "lower", "similar", "higher", "no_history".
2. `reasons`: every reason, backed by words in the ad or by the fields, for a broker to
   expect this ad to ask less than a typical apartment of its bedroom count in its building
   and neighbourhood. Use these codes, as many as apply, or an empty list:
   - `regulated`: rent stabilized, preferential rent, legal rent, lease renewal caps
   - `income`: income limits, lottery, affordable housing program, HDFC, voucher language
   - `room`: a room in a shared apartment, or a price for a single room
   - `shared_house`: unit in the owner's house, shared entrance, landlord lives on site
   - `basement`: basement, garden level, lower level, ground floor
   - `walkup_high`: fourth floor or higher with no elevator
   - `small`: very small, micro studio, alcove sold as a bedroom, no real living room
   - `beds_dubious`: the bedroom count in the fields is higher than the text supports
     (flex or convertible rooms, a junior or "convertible" layout, an office counted as a bedroom,
     windowless or interior room, loft sleeping area counted as a bedroom)
   - `condition`: dated, as-is, unrenovated, no dishwasher or laundry where the earlier ad
     had them, landlord's basic finish
   - `location`: loud avenue, highway, elevated train, far from the subway, per the text
   - `takeover`: lease assignment, sublet, lease break, short remaining term
   - `short_or_furnished_before`: an earlier ad was furnished, short-term or corporate and
     this one is a plain lease (so the earlier asks were inflated)
   - `net_effective`: the ask shown is a net-effective rent after free months
   - `concession_gone`: earlier ads carried free months and this one has none (or the reverse)
   - `different_unit`: the earlier ads describe a different apartment (other layout, floor,
     bedroom or bath count, size, a combined or split unit)
   - `renovated_before`: the earlier ad sold a renovation, furniture or amenity this ad lacks
   - `not_a_home`: commercial, office, storage, parking, several units in one ad
   - `ask_error`: the coded ask disagrees with the rent in the text, or looks like a typo
   - `owner_direct`: by owner, small landlord, no broker, plainly written ad with few photos
   - `restrictions`: no pets, no smoking, students only, must qualify 40x with no guarantors and similar
   - `quick_cut`: the landlord cut the ask after the unit sat, or relists soon after a
     failed rental, with no other reason given
   - `other`: say what in `note`
3. `changed_since_previous`: a short list of what differs between this ad and the previous
   ad of the unit (text and fields): bedrooms, baths, size, furnished, lease length, free
   months, agency, floor label, wording of condition. Empty when there is no earlier ad or
   nothing differs.
4. `real_deal`: "yes" when the ad reads as a sound apartment asking less than its own
   history or neighbours with no reason you can find, "no" when a reason above explains a
   lower ask, "ordinary" when nothing about the ad suggests a low ask.
5. `note`: one or two sentences in broker voice, quoting the few words of the ad you rely on.

Base every answer on what the ad or the fields say. Do not guess which ads the model missed.

Write one JSON object per line to the answers file named in your task, in the ads' order:

{"ad": "G00-03", "listing_id": "...", "low_vs_history": "lower", "reasons": ["regulated"],
 "changed_since_previous": ["bedrooms 2 -> 1"], "real_deal": "no", "note": "..."}
