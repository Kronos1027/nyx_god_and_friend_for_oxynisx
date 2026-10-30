import json
import pytest

from tools.calculator_tool import calculate


@pytest.mark.parametrize("operation,values,expected", [
    ("sum", [11,22,33,44,55,66,77,88], "396"),
    ("sum", ["0.1", "0.2"], "0.3"),
    ("subtract", [10, "0.1"], "9.9"),
    ("product", ["0.5", "0.2"], "0.1"),
    ("mean", [1, 2, 3], "2"), ("min", [2, -1], "-1"), ("max", [2, -1], "2"),
])
def test_decimal_operations(operation, values, expected):
    result = calculate({"operation": operation, "values": values})
    assert result.ok and result.meta["result"] == expected and not result.meta["rounded"]
    assert json.loads(result.output)["result"] == expected


def test_inexact_division_is_explicit():
    result = calculate({"operation": "divide", "values": [1, 3]})
    assert result.ok and result.meta["rounded"] and result.meta["precision_digits"] == 80


@pytest.mark.parametrize("params", [
    {"operation": "sum", "values": ["__import__('os').system('x')"]},
    {"operation": "sum", "values": [float("nan")]},
    {"operation": "sum", "values": [True]},
    {"operation": "sum", "values": ["1e999999999"]},
    {"operation": "sum", "values": ["1,000"]},
    {"operation": "sum", "values": [1] * 129},
    {"operation": "divide", "values": [1, 0]},
    {"operation": "divide", "values": [1]},
    {"operation": "product", "values": ["1e99"] * 128},
    {"operation": "eval", "values": ["1+1"]},
])
def test_invalid_and_unbounded_calculations_are_rejected(params):
    assert not calculate(params).ok
