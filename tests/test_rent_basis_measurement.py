import pytest

from apartments.rent_basis_measurement import measure


@pytest.mark.parametrize('text,net,gross', [
    ('The gross rent is $3,100 with 1 month free on a 14-month lease term, the net rent is just $2,878!', 2878, 3100),
    ("Making $5,800 (Gross) $4,833 (Net)", 4833, 5800),
    ('Gross monthly rent $3,395; net effective rent: $3,160.00.', 3160, 3395),
    ('Net-effective price is $2,500.50. Gross price: $2,750.', 2500.50, 2750),
])
def test_literal_amounts_preserve_basis_and_exact_offsets(text, net, gross):
    result = measure(text, net)
    assert {(r['basis_label'], r['amount']) for r in result['amounts']} == {('net', net), ('gross', gross)}
    assert result['target_matches'] == ['net']
    assert measure(text, gross)['target_matches'] == ['gross']
    for claim in result['amounts']:
        assert text[claim['start']:claim['end']] == claim['literal']


@pytest.mark.parametrize('text', ['Net effective price listed.', 'NET EFFECTIVE RENT ADVERTISED.',
    'The listed rent is net effective.', 'Rent is advertised as net effective.', 'Advertised rent is net.'])
def test_sentence_order_variants_are_review_signals(text):
    result = measure(text, 3000)
    assert len(result['advertised_net_statements']) == 1
    assert result['target_matches'] == []  # Never invent a missing amount.


def test_legal_is_not_silently_equated_with_gross():
    result = measure('NET EFFECTIVE RENT ADVERTISED: LEGAL RENT $9,200', 9200)
    assert result['target_matches'] == ['legal']


def test_administrative_wording_is_preserved_without_asserting_a_price_basis():
    result = measure('Approval is based on gross rent rather than net rent.', 3000)
    assert result['target_matches'] == [] and result['advertised_net_statements'] == []
    assert result['mentions'][0]['administrative_context']


@pytest.mark.parametrize('text', ['Not net rent $3,000.', 'This is not a net effective rent of $3,000.',
                               'Gross rather than net rent $3,000.'])
def test_negated_amount_labels_are_not_positive_target_matches(text):
    result = measure(text, 3000)
    assert result['target_matches'] == [] and result['amounts'][0]['preceded_by_negation']


def test_missing_or_ambiguous_text_does_not_imply_gross():
    assert not measure(None, 3000)['description_available']
    assert measure('Internet included; three months free.', 3000)['mentions'] == []
    assert measure('Net effective rent listed, gross is 7,300.', 7300)['target_matches'] == []
    assert measure('Net $3,000, gross $3,000.', 3000)['target_matches'] == ['gross', 'net']


@pytest.mark.parametrize('separator', ['\n', ' '])
def test_a_following_net_label_does_not_relabel_the_preceding_gross_amount(separator):
    text = 'Gross rent: $1895'+separator+'Net rent (2 weeks free for an immediate lease start): $1815'
    result = measure(text, 1895)
    assert result['target_matches'] == ['gross']
    assert [(c['basis_label'], c['amount']) for c in result['amounts']] == [('gross', 1895), ('net', 1815)]


@pytest.mark.parametrize('text', ['$4095 Gross Rent - $3755 Net Effective Rent',
                                'Gross rent $4095 Net rent $3755'])
def test_leading_and_trailing_quote_pairs_keep_each_amount_with_its_label(text):
    result = measure(text, 4095)
    assert result['target_matches'] == ['gross']
    assert [(c['basis_label'], c['amount']) for c in result['amounts']] == [('gross', 4095), ('net', 3755)]


def test_parenthetical_net_price_does_not_relabel_unlabelled_headline():
    result = measure('$3995 (net effective rent is $3687 - 13 month lease)', 3995)
    assert result['target_matches'] == []
    assert [(c['basis_label'], c['amount']) for c in result['amounts']] == [('net', 3687)]


def test_gross_price_per_month_is_not_relabelled_by_following_net_offer():
    text = 'Gross Price per month = $4,500 Net Effective Rent with 1 Month Free on an 18 Month Lease = $4,250'
    result = measure(text, 4500)
    assert result['target_matches'] == ['gross']
    assert result['amounts'][0]['amount'] == 4500 and result['amounts'][0]['basis_label'] == 'gross'


@pytest.mark.parametrize('target', [0, -1, float('nan'), float('inf')])
def test_invalid_target_rejected(target):
    with pytest.raises(ValueError): measure('Net rent $3,000', target)


@pytest.mark.parametrize('texts,expected', [
    (['Net rent $3,000.', 'Net effective rent $3,000.'], 'all_captures_match_explicit_net_only'),
    (['Net rent $3,000.', None], 'some_captures_match_explicit_net'),
    (['Net rent $3,000.', 'Gross rent $3,000.'], 'target_matches_both_net_and_gross_quotes'),
    (['Net effective rent advertised. Gross rent $3,000.'], 'target_matches_explicit_gross'),
    (['Legal rent $3,000.'], 'target_matches_explicit_legal'),
    (['Net effective rent advertised.'], 'advertised_net_statement_without_target_amount_match'),
    (['Income approval uses net rent $3,000.'], 'net_mention_without_target_amount_match'),
])
def test_all_attached_captures_and_administrative_context_affect_review_priority(texts, expected):
    from models.rent_basis_source_audit import classify
    assert classify([{'measurement': measure(t, 3000)} for t in texts]) == expected
