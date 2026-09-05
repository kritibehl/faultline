from faultline.invariants.effects import at_most_one_effect


def test_at_most_one_effect_passes_with_zero_effects():
    result = at_most_one_effect(0)

    assert result.name == "at-most-one-effect"
    assert result.passed is True
    assert result.observed == 0
    assert result.limit == 1


def test_at_most_one_effect_passes_with_one_effect():
    result = at_most_one_effect(1)

    assert result.passed is True
    assert result.observed == 1


def test_at_most_one_effect_fails_with_two_effects():
    result = at_most_one_effect(2)

    assert result.passed is False
    assert result.observed == 2


def test_at_most_one_effect_fails_with_many_effects():
    result = at_most_one_effect(10)

    assert result.passed is False
    assert result.observed == 10
