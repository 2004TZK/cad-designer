# -*- coding: utf-8 -*-
"""LLM 辅助位（FR-14 / T4-8，Q11）——MVP 接口骨架，默认关闭。

红线 R-4：LLM 输出永不进入自动落图通道；无密钥/无 API → 辅助位整体关闭，
主链路功能不降级（7.2 无 LLM 回归）。三个挂载位：
- structure：P4 检索命中块数值结构化（附原文对照，人工确认后采信）
- advisor：H1/H2/H3 中断裁决建议（两源值+相似先例汇总，人签字生效）
- SRD 字段兜底提取：P1 正则失败个别字段（产出必过断言并留痕）
选型：DeepSeek 首选（OpenAI 兼容接口），密钥 env：DEEPSEEK_API_KEY（U16）。
"""
from __future__ import annotations

import json
import os


class LlmClient:
    def __init__(self, enabled: bool | None = None):
        # mock 模式：CAD_AGENT_LLM_MOCK=1 → 离线集成测试（R-4 断言门禁可测，不出网）
        self.mock = os.environ.get("CAD_AGENT_LLM_MOCK", "") == "1"
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.failure = None
        if enabled is False:          # --no-llm 显式关闭
            self.enabled = False
        else:
            self.enabled = self.mock or bool(self.api_key)

    def _call(self, system: str, user: str) -> str | None:
        if not self.enabled:
            return None
        if self.mock:  # 离线 mock：确定性输出，供 R-4 门禁与降级路径测试
            return json.dumps({"table": "MOCK", "index": "MOCK", "values": [],
                               "_note": "mock 输出，必须人工确认"}, ensure_ascii=False)
        try:
            from openai import OpenAI  # extras: llm
        except ImportError:
            self.enabled=False
            self.failure='openai SDK 未安装'
            return None
        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=30)
            resp = client.chat.completions.create(
                model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return resp.choices[0].message.content
        except Exception as exc:
            self.enabled=False
            self.failure=f'{type(exc).__name__}: {exc}'
            return None  # 失败自动降级（R7），调用方退回规则路径

    # ── P4：命中块结构化 ──
    def structure_hit(self, chunk_text: str) -> dict:
        out = self._call(
            "从机械标准表格文本中提取数值，输出 JSON：{table, index, values}。"
            "只输出 JSON，不得编造表中不存在的数值。",
            chunk_text[:1500])
        structured=None
        if out:
            try:
                structured=json.loads(out)
                if not isinstance(structured,dict) or not all(k in structured for k in ('table','index','values')):
                    raise ValueError('结构化响应缺少 table/index/values')
            except (ValueError,TypeError) as exc:
                self.enabled=False
                self.failure=str(exc)
                structured=None
        return {"structured": structured, "original":chunk_text[:1500],"needs_human_confirm": True, "note": "R-4：人工确认后方可采信"}

    # ── H1/H2/H3：中断裁决建议 ──
    def advise(self, context: dict) -> str | None:
        if not self.enabled:
            return None
        return self._call(
            "你是机械设计课程设计辅助。根据给定两源数值与历史裁决，给出简短建议（不落图，仅建议）。",
            str(context)[:1500])

    def status(self) -> dict:
        return {"enabled": self.enabled, "provider": "DeepSeek(首选)/通义/GLM(备选)",
                "key_env": "DEEPSEEK_API_KEY",
                'failure':self.failure,
                "note": "辅助位启用；输出需确认" if self.enabled else "辅助位关闭，主链路零 LLM 依赖（R-4/U16）"}
