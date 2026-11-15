# -*- coding: utf-8 -*-
"""最小 MCP stdio 传输层（JSON-RPC 2.0，换行分帧；零外部依赖）。

对齐 MCP 2024-11-05 协议的最小子集：initialize / tools/list / tools/call / ping。
供 T1-2 余项：进程内引擎包装为 stdio MCP server，Runner 经 client 双会话调用
（会话 A=ezdxf 出图，会话 B=com 转换），与 Autocad-MCP 工具词汇对齐。
"""
from __future__ import annotations

import json
import sys
from typing import Callable

PROTOCOL_VERSION = "2024-11-05"


def send(msg: dict, out=None):
    (out or sys.stdout).write(json.dumps(msg, ensure_ascii=False) + "\n")
    (out or sys.stdout).flush()


def serve(tool_specs: list[dict], dispatcher: Callable[[str, dict], dict]):
    """stdio 主循环。tool_specs: [{name,description,inputSchema}]；
    dispatcher(name, args) → 结果 dict（异常转 isError）。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None,
                  "error": {"code": -32700, "message": "parse error"}})
            continue
        method, rid = req.get("method"), req.get("id")
        params = req.get("params") or {}
        try:
            if method == "initialize":
                result = {"protocolVersion": PROTOCOL_VERSION,
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "cad-agent-inline-mcp", "version": "0.2.0"}}
            elif method == "notifications/initialized":
                continue  # 通知无响应
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": tool_specs}
            elif method == "tools/call":
                name = params["name"]
                args = params.get("arguments") or {}
                try:
                    data = dispatcher(name, args)
                    result = {"content": [{"type": "text",
                                           "text": json.dumps(data, ensure_ascii=False)}]}
                except Exception as exc:  # 工具级错误 → isError 内容
                    result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                              "isError": True}
            else:
                send({"jsonrpc": "2.0", "id": rid,
                      "error": {"code": -32601, "message": f"unknown method {method}"}})
                continue
            if rid is not None:
                send({"jsonrpc": "2.0", "id": rid, "result": result})
        except Exception as exc:  # 框架级错误
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"}})


def read_message(stdin=None) -> dict | None:
    line = (stdin or sys.stdin).readline()
    if not line:
        return None
    return json.loads(line)
