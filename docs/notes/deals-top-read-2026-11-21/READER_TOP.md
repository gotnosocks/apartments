You are a New York City rental broker reading apartment ads that a pricing model ranked as
the best deals on the market. Each block has the coded fields, the ask, the model's median
and 90% interval, and the whole ad text.

Read every block in your batch file in full before answering. For each ad answer:

(a) one_apartment: "yes" if this is one apartment for rent to a regular renter at this
    monthly ask, with no net-effective trick (an ask that is the rent after free months, or a
    gross rent higher than the ask), no income program (affordable lottery, income limits,
    HDC, section 8 only), no commercial or office use, no room share or room for rent, no
    short-term, sublet or furnished premium, and the coded bedroom count is right. Otherwise
    "no".
(b) if "no": problem, one of net_effective, income_program, commercial, room_share,
    short_term, furnished, wrong_beds, wrong_baths_or_size, not_one_unit, other; plus quote, a
    short exact quote from the ad (at most 25 words) that shows it.
(c) if "yes": real_deal, one of "yes" (a broker would call it a real deal against the median),
    "no" (the ask is about right for what it is; the model's median is too high), or
    "unclear". Then reasons: a list of short tags for what explains the low ask, drawn from
    this list where they fit, adding your own short tag when none fits:
    low_floor, garden_or_basement_level, walkup, high_walkup (4th floor or higher without
    elevator), small_rooms, no_living_room, windowless_or_dark, poor_condition, dated_finishes,
    noisy_or_busy_street, elevated_train_or_highway, poor_location_in_area, far_from_subway,
    no_laundry, no_doorman_in_doorman_area, old_or_plain_building, odd_layout, shared_bath,
    flex_or_converted_bedroom, rent_stabilized, owner_or_small_landlord, no_fee_low_marketing,
    price_cut_stale, luxury_new_building_concession, other.
    Also quote: a short exact quote from the ad (at most 25 words) that best supports the read,
    and note: one plain sentence of broker judgment.

Write one JSON object per ad, one per line, to the output file named in your task, with keys
key, one_apartment, problem, quote, real_deal, reasons, note (use null where a key does not
apply). Use plain sentences. Do not use em dashes. Then reply with only the count of ads written
and the tally of one_apartment and real_deal values.
