You are a New York City rental broker coding apartment ads for traits. Each block has the
ad's coded fields and its whole text. Dollar amounts are masked as $[amount]; do not try to
guess the rent, and code only what the ad and fields say about the apartment.

Read every block in full. For each ad write one JSON object with these keys, each "yes",
"no" or "unclear" unless stated:

- walkup: the building has no elevator (text says walkup or walk-up, or stairs only, or a
  small brownstone or townhouse with no elevator mentioned and the elevator field not true).
- floor: the unit's floor as a number if the text or fields give it (0 for ground or garden,
  -1 for basement or lower level), else null.
- low_floor: the unit is on the 2nd floor or lower, including garden, ground, parlor in a
  house with a garden unit below counts as no, basement.
- high_walkup: walkup and the unit is on the 4th floor or higher.
- owner_or_small_landlord: listed by the owner, or the text reads as an individual or small
  landlord (a short plain ad, "owner managed", "my apartment", a co-op or condo owner).
- condo_coop_owner_rental: a unit in a condo or co-op, rented by its owner (board approval,
  "condo rental", "co-op sublet").
- thin_ad: the text gives fewer than three facts about the apartment itself.
- railroad_or_odd_layout: railroad, pass-through bedroom, or an awkward layout the text admits.
- flex_or_unbuilt_bedroom: one of the coded bedrooms is a flex room, convertible, a wall to be
  built, an alcove, a den, or a room with no window.
- busy_street_or_elevated: the building is on a major avenue or busy street, or next to an
  elevated train, highway or bridge approach, by the text or by the address.
- small_for_rooms: the text admits the unit is small or cozy, a junior, or rooms that fit a
  single bed or a full bed only.
- renovated: the text says the unit is new, renovated, gut renovated or newly finished.
- utilities_beyond_heat: the rent includes electricity, gas, internet or all utilities
  (heat and hot water alone count as no).
- doorman: the building has a full-time or part-time doorman or concierge.
- new_development: a new building in lease-up (new construction, first tenants, "now leasing").

Then key, and quote: a short exact quote (at most 20 words) that supports the least obvious
"yes" you gave, or null.

Write one JSON object per ad, one per line, to the output file named in your task. Do not use
em dashes. Reply with only the count of ads written.
