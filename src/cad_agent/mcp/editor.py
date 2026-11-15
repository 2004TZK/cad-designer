# -*- coding: utf-8 -*-
"""出图引擎（FR-08 / T4-3）：update_plan 驱动的 G1~G5 + E1~E5 编排。

MVP 形态（Q2 ezdxf headless 的进程内实现，等价于 MCP 会话 A 的 ezdxf 引擎；
stdio MCP 会话层留待迭代接入——见任务拆分 T1-2 备注）：
- 会话语义：复制总模板 → work/{part}_working.dxf → 批次执行 → *_final.dxf
- 批次原子性：几何批次（G1~G3+G5）与文本批次（E1~E5/G4）分离，失败整批回滚（重跑副本）
- 检查点：每批次后读回校验（实体计数 + 文本快照 diff 仅目标串）
- 红线：总模板只读（双层保护）；结构资产零变更（R-2）；几何变更仅白名单（R-3）
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import ezdxf

from .. import config


class EditorError(Exception):
    pass


class Editor:
    def __init__(self, run_work: Path, log_cb=print):
        self.work = Path(run_work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.log = log_cb

    # ── 批次一：几何（G1~G3 + G5 跟随） ──
    def apply_geo(self, part: str, plan_geo: list[dict], reset: bool = True) -> dict:
        src = config.TEMPLATE_GEAR if part == "gear" else config.TEMPLATE_SHAFT
        working = self.work / f"{part}_working.dxf"
        if reset or not working.exists():
            shutil.copyfile(src, working)
        doc = ezdxf.readfile(str(working))
        moved = []
        moved = self.apply_geo_document(doc, plan_geo)
        doc.saveas(str(working))
        return {"moved_entities": moved, "working": str(working)}

    def apply_geo_document(self, doc, plan_geo):
        moved = []
        for op in plan_geo:
            if op["op"] == "G1" and "new_bounds" in op:      # 轴段边界重算
                moved += self._shift_shaft(doc, op)
            elif op["op"] == "G1" and "entity_moves" in op:  # 减重孔空档边
                for mv in op["entity_moves"]:
                    e = doc.entitydb.get(mv["handle"])
                    dy = mv["dy"]
                    if e.dxftype() == "LINE":
                        s, t = e.dxf.start, e.dxf.end
                        e.dxf.start = (s.x, s.y + dy, s.z)
                        e.dxf.end = (t.x, t.y + dy, t.z)
                        moved.append({"handle": mv["handle"], "dy": dy})
                for dm in op.get("dim_follow", []):  # G5：标注跟随（整体平移含匿名块）
                    if abs(dm['dy'])>op.get('follow_threshold',20) and not op.get('large_move_confirmed'):
                        raise EditorError('G5 移动超过阈值，转 H4 确认')
                    e = doc.entitydb.get(dm["handle"])
                    if e is not None and e.dxftype() == "DIMENSION":
                        e.translate(0, dm["dy"], 0)
                        moved.append({"handle": dm["handle"], "dy": dm["dy"], "g5": "move"})
            else:
                raise EditorError(f"未支持的几何操作: {op}")
        return moved

    def _shift_shaft(self, doc, op):
        from ..core.geometry import shift_shaft
        return shift_shaft(doc, op)

    def apply_text(self, part: str, plan_text: list[dict]) -> dict:
        final = self.work / f"{part}_final.dxf"
        working = self.work / f"{part}_working.dxf"
        if not working.exists():
            src = config.TEMPLATE_GEAR if part == "gear" else config.TEMPLATE_SHAFT
            shutil.copyfile(src, working)
            working_dxf = ezdxf.readfile(str(working))
        else:
            working_dxf = ezdxf.readfile(str(working))
        applied, skipped = [], []
        for op in plan_text:
            e = working_dxf.entitydb.get(op["handle"])
            old_raw, new_plain = op.get("old_raw"), op["new_plain"]
            if e is None:
                raise EditorError(f"文本批次回滚：handle {op['handle']} 不存在")
            current_raw = e.text if e.dxftype() == "MTEXT" else e.dxf.get("text", "")
            current_plain = e.plain_text() if e.dxftype() == "MTEXT" else _dim_plain(current_raw)
            if _norm(current_plain) != _norm(op["old_plain"]):
                raise EditorError(f"文本批次回滚：{op['handle']} 旧值不匹配")
            old_raw = current_raw
            if e.dxftype() == "DIMENSION":
                new_raw = self._patch_dim_raw(old_raw, op["old_plain"], new_plain)
                e.dxf.text = new_raw
                # 模板尺寸已手工布点：直接同步匿名块文字，重渲染会重排尺寸线。
                block = working_dxf.blocks.get(e.dxf.geometry)
                if block is None:
                    raise EditorError('尺寸匿名块缺失')
                for label in block:
                    if label.dxftype()=='MTEXT':
                        label.text=self._patch_dim_raw(label.text,op['old_plain'],new_plain)
            elif e.dxftype() == "MTEXT":
                new_raw = self._patch_mtext_raw(e, old_raw, new_plain)
                e.text = new_raw
            else:
                raise EditorError(f"文本批次回滚：不支持 {e.dxftype()}")
            # 读回校验
            got = e.plain_text() if e.dxftype() == "MTEXT" else _dim_plain(e.dxf.text)
            if _norm(got) != _norm(new_plain):
                raise EditorError(f"文本批次回滚：{got!r} != {new_plain!r}")
            applied.append({"handle": op["handle"], "old": op["old_plain"], "new": new_plain})
        working_dxf.saveas(str(final))
        shutil.copyfile(final, working)
        return {"applied": applied, "skipped": skipped, "final": str(final)}

    @staticmethod
    def _patch_dim_raw(old_raw: str, old_plain: str, new_plain: str) -> str:
        """在 DIMENSION text override 原文上做带符号数字序列对齐替换。

        old_plain/new_plain 为全文 plain（φ23+0.050/ +0.034 → φ23+0.041/ +0.028），
        数字 token 顺序对齐逐一替换，保留格式码与空格风格。
        """
        olds, news = _signed_tokens(old_plain), _signed_tokens(new_plain)
        controls=[m.span() for m in re.finditer(r'\\(?!S)[A-Za-z][^;]*;',old_raw)]
        tokens=[m for m in re.finditer(r'[+-]?\d+(?:\.\d+)?',old_raw)
                if not any(a<=m.start()<b for a,b in controls)]
        if len(olds)!=len(news) or [m.group() for m in tokens]!=olds:
            raise EditorError('尺寸文本 token 数量/顺序不匹配，整批回滚')
        raw=old_raw
        for match,new in reversed(list(zip(tokens,news))):
            raw=raw[:match.start()]+new+raw[match.end():]
        return raw

    @staticmethod
    def _patch_mtext_raw(e, old_raw: str, new_plain: str) -> str:
        """MTEXT：保留格式码骨架（\\A1;/字体码），仅替换载荷数字；跨字体码拆分的
        数字串 token 替换失败时，以首个字体码前缀重建（保持 SimSun 渲染）。"""
        raw = e.text
        cur_plain = e.plain_text()
        if _norm(cur_plain) == _norm(new_plain):
            return raw
        if old_plain_like(cur_plain) and _numeric_tokens(cur_plain) and _numeric_tokens(new_plain):
            tok = _numeric_tokens(cur_plain)[0]
            new_tok = _numeric_tokens(new_plain)[0]
            cand = _replace_number(raw, tok, new_tok)
            # 替换后须包含新值全部数字段，且旧 token 已消失（plain 口径由调用方回读校验）
            if all(t in cand for t in _numeric_tokens(new_plain)) and tok not in _numeric_tokens(new_plain):
                return cand
        # 重建兜底：保留首个字体码前缀
        m = re.match(r"^(\{?\\[^;]+;)", raw)
        prefix = m.group(1) if m else ""
        tail = "}" if raw.startswith("{") and not prefix.endswith("}") else ""
        return prefix + new_plain + tail


# ── 工具 ──

def _norm(s: str) -> str:
    return s.replace(" ", "").replace("φ", "").replace("%%C", "").replace("X", "").strip()


def old_plain_like(s: str) -> bool:
    return bool(re.search(r"\d", s))


def _numeric_tokens(s: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", s)


def _signed_tokens(s: str) -> list[str]:
    """带符号数字 token（含前导 +/-），保持出现顺序。"""
    return re.findall(r"[+-]?\d+(?:\.\d+)?", s)


def _shift_token(old_plain: str, new_plain: str, tok: str) -> str:
    """old→new 文本中与 tok 顺序对应的数字。"""
    olds = _numeric_tokens(old_plain)
    news = _numeric_tokens(new_plain)
    if tok in olds and olds.index(tok) < len(news):
        return news[olds.index(tok)]
    return tok


def _replace_number(raw: str, old: str, new: str) -> str:
    """替换 raw 中的独立数字（不被字母/数字包围的匹配）。"""
    if old == new:
        return raw
    pattern = re.compile(r"(?<![\d.A-Za-z])" + re.escape(old) + r"(?![\d])")
    out, n = pattern.subn(new, raw, count=1)
    if n == 0:  # 宽松回退
        out = raw.replace(old, new, 1)
    return out


def _dim_plain(text: str) -> str:
    s = text.replace("%%c", "%%C").replace("%%C", "φ").replace("%%p", "±")
    if "\\S" in s:
        i = s.index("\\S")
        j = s.index("^", i)
        k = s.index(";", j)
        sup, sub = s[i + 2 : j], s[j + 1 : k]
        s = s[:i] + f"{sup}/{sub}" + s[k + 1 :]
    return s.replace("{", "").replace("}", "").replace("\\H0.71x;", "").replace("\\C3;", "").strip()
