# -*- coding: utf-8 -*-
"""MCP stdio 客户端（双会话管理，T1-2 余项 / FR-06 底层）。

会话 A：AUTOCAD_MCP_BACKEND=ezdxf（出图）；
会话 B：AUTOCAD_MCP_BACKEND=com（DWG 转换）。
Runner --engine mcp 时经此客户端执行 P6/P7，与 inline 引擎等价（regress diff=0 验证）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


class McpClient:
    def __init__(self, backend: str = "ezdxf", log_cb=print):
        self.backend = backend
        self.log = log_cb
        env = dict(os.environ)
        env["AUTOCAD_MCP_BACKEND"] = backend
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "cad_agent.mcp.server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=str(Path(__file__).resolve().parents[3]), text=True,
            encoding="utf-8", bufsize=1)
        self._id = 0
        self.initialize()

    # ── JSON-RPC ──
    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read() if self.proc.poll() is not None else ""
                raise RuntimeError(f"MCP server 无响应（backend={self.backend}）{err[:400]}")
            msg = json.loads(line)
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"MCP {method}: {msg['error']}")
                return msg["result"]

    def initialize(self):
        r = self._rpc("initialize", {"protocolVersion": "2024-11-05",
                                     "capabilities": {}, "clientInfo": {"name": "cad-agent"}})
        self.log(f"[mcp:{self.backend}] 会话建立 {r['serverInfo']['name']} "
                 f"tools={len(self._rpc('tools/list')['tools'])}")

    # ── 工具调用 ──
    def call(self, tool: str, **args) -> dict:
        r = self._rpc("tools/call", {"name": tool, "arguments": args})
        if r.get("isError"):
            raise RuntimeError(f"tool {tool}: {r['content'][0]['text']}")
        return json.loads(r["content"][0]["text"])

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
            self.proc.wait(timeout=10)
        finally:
            for stream in (self.proc.stdin,self.proc.stdout,self.proc.stderr):
                if stream and not stream.closed:
                    stream.close()
