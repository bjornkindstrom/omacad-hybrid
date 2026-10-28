"""A bad formula is an error message, never a crash (callers only catch ValueError)."""
import pytest

from omacad.model.expr import evaluate


@pytest.mark.parametrize("text", ["(-8)^(1/3)", "(64^64)^64", "1/0", "sqrt(-1)"])
def test_bad_formulas_raise_value_error(text):
    with pytest.raises(ValueError):
        evaluate(text)


def test_ordinary_formulas_still_work():
    assert evaluate("2^10") == 1024.0
    assert evaluate("8^(1/3)") == pytest.approx(2.0)
    assert evaluate("7 % 3") == 1.0
    assert evaluate("w*2", {"w": 3.5}) == 7.0
