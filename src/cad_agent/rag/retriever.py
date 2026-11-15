# -*- coding: utf-8 -*-
"""向量检索兜底（FR-05 / T4-2 / T1-4，Q7 三态输出）。

双后端：
- bge-m3（FlagEmbedding + torch，本机 D:/CODE/bge/models/bge-m3；766×1024 归一化库）
  → U11 同构验证（建库 chunk 重编码 cos>0.99）+ U5 阈值标定（清单 8.2 做 ground truth）
- 词面兜底（char 2-gram Jaccard，零依赖）→ bge 不可用时仍可粗检索（降级不致盲）

三态输出（Q7/U6）：hit（≥τ 采信候选，仍须与清单 8.2 交叉/人工确认）/
ambiguous（τ 附近，转人工）/ miss（走清单 8.2 兜底，两源皆缺列待确认 H3）。
红线 R-4/FR-05：命中值不自动落图——进 pending 由人确认，或 LLM 结构化（若启用）+人工。
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .. import config


def _load_chunks() -> list[dict]:
    f = config.VECTORS_DIR / "chunks.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def _ngrams(text: str, n: int = 2) -> set[str]:
    t = re.sub(r"\s+", "", text)
    return {t[i:i + n] for i in range(max(len(t) - n + 1, 1))}


class Retriever:
    DEFAULT_TAU = 0.60  # U5 标定前缺省；标定后由 assets/tau_calibration.json 覆盖

    def __init__(self, lookup_tables: dict | None = None):
        self.tables = lookup_tables or {}
        self._chunks = _load_chunks()
        self._emb = None
        self._model = None
        self._vector_failed = False
        self._backend_error = None
        self._tau_path = config.ASSETS_DIR / "tau_calibration.json"
        self._tau_doc = None
        self.tau = self.DEFAULT_TAU

    def _active_tau(self) -> float:
        """τ 惰性解析：按当前可用后端取标定值（避免 __init__ 期 import torch）。"""
        if self._tau_doc is None:
            if self._tau_path.exists():
                try:
                    self._tau_doc = json.loads(self._tau_path.read_text(encoding="utf-8"))
                except Exception:
                    self._tau_doc = {}
            else:
                self._tau_doc = {}
        vector=self.vector_ready()
        key = "tau_bge" if vector else "tau_lexical"
        value=self._tau_doc.get(key)
        return value if value is not None else (self.DEFAULT_TAU if vector else .30)

    # ── 后端可用性 ──
    def vector_ready(self) -> bool:
        if self._vector_failed:
            return False
        try:
            import torch  # noqa: F401
            import FlagEmbedding  # noqa: F401
        except (ImportError,OSError,RuntimeError):
            return False
        return bool(config.BGE_MODEL_DIR.exists() and self._chunks and
                    (config.VECTORS_DIR / "embeddings.npy").exists())

    def _ensure_model(self):
        if self._model is None:
            from FlagEmbedding import BGEM3FlagModel
            self._model = BGEM3FlagModel(str(config.BGE_MODEL_DIR), use_fp16=False)
        return self._model

    def _encode(self, text: str, is_query: bool = False):
        """is_query=True 时加检索指令前缀（meta.json query_instruction）；
        文档侧（建库 chunk/U11 重编码）不加——与建库口径同构（U11 关键）。"""
        import numpy as np
        instr = ""
        if is_query:
            mf = config.VECTORS_DIR / "meta.json"
            if mf.exists():
                instr = json.loads(mf.read_text(encoding="utf-8")).get("query_instruction", "")
        model = self._ensure_model()
        vec = model.encode([instr + text], max_length=1024)["dense_vecs"][0]
        v = np.asarray(vec, dtype="float32")
        return v / (float((v ** 2).sum()) ** 0.5 + 1e-12)

    def _ensure_emb(self):
        import numpy as np
        if self._emb is None:
            self._emb = np.load(config.VECTORS_DIR / "embeddings.npy")
        return self._emb

    # ── U11 同构验证（T1-4） ──
    def verify_isomorphism(self, n: int = 3, sample=None) -> dict:
        """抽 n 个建库 chunk 重编码与库存向量比对（cos>0.99 通过）。"""
        if not self.vector_ready():
            return {"pass": False, "note": "torch/FlagEmbedding 不可用，未验证（U11 未闭环）"}
        import numpy as np
        emb = self._ensure_emb()
        idx = sample or [0, len(self._chunks) // 2, len(self._chunks) - 1][:n]
        rows = []
        for i in idx:
            v = self._encode(self._chunks[i]["text"], is_query=False)
            cos = float(np.dot(v, emb[i]) / ((np.linalg.norm(v) * np.linalg.norm(emb[i])) + 1e-12))
            rows.append({"chunk_id": self._chunks[i].get("chunk_id", str(i)), "cos": round(cos, 5),
                         "pass": cos > 0.99})
        return {"pass": all(r["pass"] for r in rows), "rows": rows,
                "note": "bge-m3 编码同构验证（U11）"}

    # ── 主查询（三态） ──
    def query(self, item_desc: str, tau: float | None = None, top_k: int = 5) -> dict:
        tau = self._active_tau() if tau is None else tau
        self.tau = tau
        if not self._chunks:
            return {"query": item_desc, "state": "miss", "hits": [],'top_score':0.0,'backend':'none','tau':tau,
                    "note": "向量库缺失；走清单 8.2 兜底（Q7）"}
        if self.vector_ready():
            import numpy as np
            try:
                emb = self._ensure_emb()
                q = self._encode(item_desc, is_query=True)
                scores = emb @ q
                if len(scores)!=len(self._chunks):
                    raise ValueError('向量与 chunk 数量不一致')
            except Exception as exc:
                self._vector_failed=True
                self._backend_error=str(exc)
                return self.query(item_desc,tau=None,top_k=top_k)
            order = np.argsort(-scores)[:top_k]
            hits = [{"chunk_id": self._chunks[i].get("chunk_id", str(i)),
                     "doc": self._chunks[i].get("doc", ""),
                     "heading": self._chunks[i].get("heading", "")[:40],
                     "score": round(float(scores[i]), 4),
                     "excerpt": self._chunks[i]["text"][:200]}
                    for i in order]
            top = hits[0]["score"] if hits else 0.0
            if top >= tau + 0.05:
                state = "hit"
            elif top >= tau - 0.05:
                state = "ambiguous"
            else:
                state = "miss"
            return {"query": item_desc, "state": state, "tau": tau, "backend": "bge-m3",
                    "hits": hits, "top_score": top,
                    "note": "R-4：命中值为采信候选，须与清单 8.2 交叉或人工确认后方可落图"}
        # 词面兜底（bge 不可用时降级，不致盲）
        qg = _ngrams(item_desc)
        scored = []
        for c in self._chunks:
            g = _ngrams(c["text"])
            if not g:
                continue
            jac = len(qg & g) / len(qg | g)
            scored.append((jac, c))
        scored.sort(key=lambda x: -x[0])
        hits = [{"chunk_id": c.get("chunk_id", ""), "doc": c.get("doc", ""),
                 "heading": c.get("heading", "")[:40], "score": round(s, 4),
                 "excerpt": c["text"][:200]} for s, c in scored[:top_k]]
        top = hits[0]["score"] if hits else 0.0
        state = "hit" if top >= tau else ("ambiguous" if top >= tau*.8 else "miss")
        return {"query": item_desc, "state": state, "tau": tau, "backend": "lexical_fallback",
                "hits": hits, "top_score": top,
                "note": "bge-m3 不可用，词面兜底检索；命中仍须人工确认（R-4）"}

    # ── U5 τ 标定 ──
    def calibrate_tau(self, cases: list[dict]) -> dict:
        """cases: [{query, expect_chunk_contains:[关键词], expect_chunk_id?}]。
        以清单 8.2 已知行做 ground truth：命中正确 chunk 的最低分 − 0.05 → τ。"""
        rows = []
        best = []
        for c in cases:
            r = self.query(c["query"], tau=0.0)
            ok = None
            for h in r["hits"]:
                if all(k in h["excerpt"] or k in self._chunk_text(h["chunk_id"])
                       for k in c["expect_chunk_contains"]):
                    ok = h
                    break
            rows.append({"query": c["query"], "top_score": r["top_score"],
                         "top_chunk": r["hits"][0]["chunk_id"] if r["hits"] else None,
                         "expected_found": bool(ok),
                         "hit_score": ok["score"] if ok else None})
            if ok:
                best.append(ok["score"])
        if best:
            if self.vector_ready():
                tau_bge = max(0.5, round(min(best) - 0.05, 3))
                tau_lexical = None
                tau = tau_bge
            else:  # 词面 Jaccard 分布低，按比例取阈
                tau_lexical = round(max(min(best) * 0.9, 0.05), 3)
                tau_bge = None
                tau = tau_lexical
        else:
            tau = self.DEFAULT_TAU
            tau_bge = tau_lexical = None
        out = {"tau": tau, "tau_bge": tau_bge, "tau_lexical": tau_lexical,
               "rows": rows, "n_correct": len(best), "n_cases": len(cases),
               "backend": "bge-m3" if self.vector_ready() else "lexical_fallback",
               "note": "U5 阈值标定：清单 8.2 做 ground truth；向量后端 τ=正确命中最低分−0.05，词面后端按比例"}
        self._tau_path.parent.mkdir(parents=True, exist_ok=True)
        prev = {}
        if self._tau_path.exists():
            try:  # 保留另一后端的标定值
                prev = json.loads(self._tau_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        for k in ("tau_bge", "tau_lexical"):
            if out.get(k) is None and prev.get(k) is not None:
                out[k] = prev[k]
        self._tau_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        self.tau = tau
        self._tau_doc=out
        return out

    def _chunk_text(self, chunk_id: str) -> str:
        for c in self._chunks:
            if str(c.get("chunk_id")) == str(chunk_id):
                return c["text"]
        return ""

    def status(self) -> dict:
        return {
            "vector_enabled": self.vector_ready(),
            "backend": "bge-m3" if self.vector_ready() else "lexical_fallback",
            "model_dir": str(config.BGE_MODEL_DIR),
            "chunks": len(self._chunks),
            "tau": self._active_tau(),
            "tau_calibrated": self._tau_path.exists(),
        }
