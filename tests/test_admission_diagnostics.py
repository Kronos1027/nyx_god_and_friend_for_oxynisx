import pytest

from core import runtime_budget as budget


def test_admission_error_distinguishes_missing_inventory_from_memory(monkeypatch):
    snapshot = budget.ResourceSnapshot(2 * budget.GIB, 12 * budget.GIB, 10 * budget.GIB)
    monkeypatch.setattr(budget, 'ollama_models', lambda host, endpoint: [])
    with pytest.raises(budget.InferencePressureError) as missing:
        budget.ollama_request_context('http://localhost', 'selected:4b', snapshot)
    assert missing.value.details['code'] == 'MODEL_SIZE_UNKNOWN'
    monkeypatch.setattr(budget, 'ollama_models', lambda host, endpoint:
                        [{'name': 'selected:4b', 'size': 6 * budget.GIB}] if endpoint == 'tags' else [])
    with pytest.raises(budget.InferencePressureError) as pressure:
        budget.ollama_request_context('http://localhost', 'selected:4b', snapshot)
    assert pressure.value.details['code'] == 'MODEL_BUDGET'
    assert pressure.value.details['weight_budget_bytes'] == 3 * budget.GIB
    assert 'pesos: 6.00 GiB' in str(pressure.value)
    assert 'RAM livre: 2.00 GiB' in str(pressure.value)
