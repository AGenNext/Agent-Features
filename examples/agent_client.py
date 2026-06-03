"""Tiny example: drive the gateway the way an agent would.

Run the gateway first:

    uvicorn gateway.main:app

Then:

    python examples/agent_client.py

This lists features via MCP (each manifest is already an MCP tool definition),
then calls one — exactly the discover-then-invoke loop an LLM agent performs.
"""

from __future__ import annotations

import json
import urllib.request

GATEWAY = "http://127.0.0.1:8000/mcp"


def rpc(method: str, params: dict | None = None, msg_id: int = 1) -> dict:
    payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    req = urllib.request.Request(
        GATEWAY,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main() -> None:
    # 1. Discover — the manifests come back already shaped as MCP tools.
    tools = rpc("tools/list")["result"]["tools"]
    print("Available features (as agent tools):")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")

    # 2. Invoke one, the way an agent's tool-call would.
    print("\nCalling calculator with expression '2 * (3 + 4)' ...")
    result = rpc(
        "tools/call",
        {"name": "calculator", "arguments": {"expression": "2 * (3 + 4)"}},
        msg_id=2,
    )
    print("Result:", result["result"]["content"][0]["text"])


if __name__ == "__main__":
    main()
