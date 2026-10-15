-- Fails for each row of `rows` with no row of the same ordinal in the audited model.
AUDIT (name every_row);
SELECT ordinal FROM @rows EXCEPT SELECT ordinal FROM @this_model
