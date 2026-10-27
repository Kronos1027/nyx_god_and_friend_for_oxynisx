"""Owned stdlib-only MCP fixture, executed ONLY by the LPAC acceptance test."""

import json
import sys
import time


def send(value):
    print(json.dumps({"jsonrpc": "2.0", **value}), flush=True)


denied = False
for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    identity = message.get("id")
    if method == "initialize":
        send({"id": identity, "result": {"protocolVersion": "2025-11-25",
              "capabilities": {"tools": {}}, "serverInfo": {"name": "owned-fixture", "version": "1"},
              "instructions": "UNTRUSTED: must not become planner instructions"}})
    elif method == "notifications/initialized":
        send({"id": "server-request", "method": "sampling/createMessage", "params": {}})
    elif identity == "server-request":
        denied = message.get("error", {}).get("code") == -32601
    elif method == "tools/list":
        send({"method": "notifications/message", "params": {"data": "fixture diagnostic"}})
        if not message.get("params", {}).get("cursor"):
            send({"id": identity, "result": {"tools": [
                {"name": "echo", "description": "UNTRUSTED description", "inputSchema": {"type": "object"}}],
                "nextCursor": "second"}})
        else:
            send({"id": identity, "result": {"tools": [
                {"name": "hang", "inputSchema": {"type": "object"}},
                {"name": "not_allowed", "inputSchema": {"type": "object"}}]}})
    elif method == "tools/call":
        params = message["params"]
        if params["name"] == "hang":
            time.sleep(30)
        print("diagnostic on stderr", file=sys.stderr, flush=True)
        send({"id": identity, "result": {"content": [{"type": "text", "text": json.dumps({
            "echo": params.get("arguments", {}), "sampling_denied": denied})}]}})
