import pytest

from core.resource_profiles import resource_profile_scope, profile_name
from core import runtime_budget as budget
from core.resource_governor import ResourceGovernor


def test_profile_scope_restores_after_error():
    original = profile_name()
    with pytest.raises(RuntimeError), resource_profile_scope('game'):
        assert profile_name() == 'game'
        raise RuntimeError('stop')
    assert profile_name() == original


def test_normal_gpu_budget_does_not_scale_weights_with_host_ram():
    low = budget.ResourceSnapshot(3 * budget.GIB, 12 * budget.GIB, 11 * budget.GIB)
    high = budget.ResourceSnapshot(7 * budget.GIB, 12 * budget.GIB, 11 * budget.GIB)
    with resource_profile_scope('normal'):
        assert budget.model_weight_budget_bytes(low) == budget.model_weight_budget_bytes(high)
        assert budget.model_weight_budget_bytes(low) == int(7.5 * budget.GIB)
        assert budget.safe_context_tokens(low) == 8192
        assert budget.model_weight_budget_bytes(budget.ResourceSnapshot(2 * budget.GIB, 12 * budget.GIB, 11 * budget.GIB)) == 0


def test_game_does_not_credit_a_large_resident_model_or_background_work():
    installed = {'name': 'large', 'digest': 'same', 'size': 6 * budget.GIB}
    running = [{**installed, 'size_vram': 6 * budget.GIB, 'context_length': 4096}]
    snapshot = budget.ResourceSnapshot(4 * budget.GIB, 12 * budget.GIB, 8 * budget.GIB, cpu_percent=5)
    with resource_profile_scope('game'):
        assert budget.resident_context(snapshot, installed, running) is None
        assert not ResourceGovernor().evaluate(snapshot, budget.WorkPriority.BACKGROUND).allowed
        assert ResourceGovernor().evaluate(snapshot, budget.WorkPriority.INTERACTIVE).allowed


def test_game_keep_alive_is_zero_and_profile_metadata_not_sent_as_model_instruction(monkeypatch):
    import io
    import json
    import urllib.request
    snapshot = budget.ResourceSnapshot(4 * budget.GIB, 12 * budget.GIB, 11 * budget.GIB)
    captured = []
    monkeypatch.setattr(budget, 'resource_snapshot', lambda: snapshot)
    monkeypatch.setattr(budget, 'ollama_models', lambda host, endpoint:
                        [{'name': 'small', 'size': 3 * budget.GIB}] if endpoint == 'tags' else [])
    def send(request, timeout):
        captured.append(json.loads(request.data))
        return io.BytesIO(b'{}')
    monkeypatch.setattr(urllib.request, 'urlopen', send)
    with resource_profile_scope('game'):
        budget.post_ollama_json('http://localhost/api/generate', {'model': 'small', 'prompt': 'oi'}, 10)
    assert captured[0]['keep_alive'] == 0
    assert captured[0]['options']['num_ctx'] == 4096
