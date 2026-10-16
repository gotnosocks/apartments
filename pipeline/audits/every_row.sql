-- Fails for each row of `rows` with no row of the same listing in the audited model.
AUDIT (name every_row);
SELECT listing_id FROM @rows EXCEPT SELECT listing_id FROM @this_model
