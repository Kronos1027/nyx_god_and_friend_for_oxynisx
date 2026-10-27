import json

import pytest

from core.sandbox_channel import SandboxChannel
from core.sandbox_rpc import SandboxRPC


def test_split_response_and_notification_are_framed_correctly():
    channel = SandboxChannel()
    channel.started.set()  # Unit transport fixture, not an isolation claim.
    for part in (b'{"jsonrpc":"2.0","method":"notifications/progress"}\n',
                 b'{"jsonrpc":"2.0","id":1,"res', b'ult":{"value":96}}\n'):
        channel.deliver(part)
    rpc = SandboxRPC(channel)
    assert rpc.request("fixture", {})["result"] == {"value": 96}
    assert json.loads(channel.take_input())["id"] == 1


@pytest.mark.parametrize("line", [
    b'{"jsonrpc":"2.0","id":2,"result":{}}\n',
    b'{"jsonrpc":"2.0","id":true,"result":{}}\n',
    b'{"jsonrpc":"2.0","id":1,"id":1,"result":{}}\n',
    b'{"jsonrpc":"2.0","id":1,"result":{},"error":{}}\n',
    b'not-json\n', b'\xff\n', b'x' * 70000,
], ids=["wrong-id", "boolean-id", "duplicate-key", "both-results", "not-json", "invalid-utf8", "too-long"])
def test_invalid_response_stops_session_without_false_success(line):
    channel = SandboxChannel()
    channel.started.set()
    for index in range(0, len(line), 16384):
        channel.deliver(line[index:index + 16384])
    result = SandboxRPC(channel).request("tools/call", {})
    assert "error" in result and result["_transport"]["outcome_unknown"]
    assert channel.stop_requested.is_set()


def test_deadline_before_start_is_not_reported_as_unknown_action():
    channel = SandboxChannel()
    result = SandboxRPC(channel, timeout=0.05).request("tools/call", {})
    assert result["_transport"] == {"outcome_unknown": False, "reason": "timeout"}
    assert channel.take_input() is None and channel.stop_requested.is_set()


def test_overflowing_number_and_server_request_cannot_bypass_policy():
    channel = SandboxChannel()
    channel.started.set()
    channel.deliver(b'{"jsonrpc":"2.0","id":"s","method":"roots/list"}\n')
    channel.deliver(b'{"jsonrpc":"2.0","id":1,"result":1e999}\n')
    result = SandboxRPC(channel).request("fixture", {})
    assert "error" in result
    channel.take_input()  # Original request.
    refusal = json.loads(channel.take_input())
    assert refusal["id"] == "s" and refusal["error"]["code"] == -32601


def test_progress_flood_has_a_fixed_bound():
    channel = SandboxChannel()
    channel.started.set()
    channel.deliver(b'{"jsonrpc":"2.0","method":"notifications/progress"}\n' * 34)
    result = SandboxRPC(channel).request("fixture", {})
    assert "Excesso" in result["error"] and channel.stop_requested.is_set()


def test_server_cannot_supply_host_transport_metadata():
    channel = SandboxChannel()
    channel.started.set()
    channel.deliver(b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"failed"},'
                    b'"_transport":{"outcome_unknown":false,"verified":true}}\n')
    result = SandboxRPC(channel).request("tools/call", {})
    assert "error" in result and "_transport" not in result
