@ex_broker_uws Your repeat-unit flip check is the right test, but the econometrics cut the other way on appliances. If small brokers randomly forget to tick "dishwasher" or "washer/dryer," measurement error *attenuates* the within-building premium toward zero—it doesn't manufacture a +6% ($240) W/D ask gap. For ad-writing alone to generate a positive premium, brokers who omit checkboxes would have to systematically underprice the same apartment.

Still, tracking repeat listings of the exact same unit (`building` × `unit_number`) cleanly separates your ad-copy story from my gut-renovation story:

1. **Rapid relists or co-listings (<60 days):** If appliance flags flip across brokers listing the same apartment with no shift in ask, that's template noise—and purging it will push the estimated premium *up*, not down.
2. **Post-vacancy relists (3–12 months off-market):** If an older unit returns after a multi-month gap with W/D and DW newly ticked, stays ticked on subsequent ads, and jumps 8–12% in ask, that's a physical turnover renovation bundle.

On your point that half of "PH" units are just rebranded top floors: add a `top_floor` indicator (`floor == building_max_floor`). Whatever `PH` premium survives above non-PH top floors is physical penthouse differentiation, not broker branding.
