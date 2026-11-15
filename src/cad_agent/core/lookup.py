# -*- coding: utf-8 -*-
"""lookup 档位查询引擎（FR-02/FR-05）。

MVP：档位表（assets/lookup_tables.json，清单 8.2 起始）按索引命中；
未覆盖项走 rag 兜底（MVP 向量库未启用 → 清单 8.2 值+待人工留痕，Q7）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hit:
    table: str
    row: dict
    src: str
    covered: bool = True   # False = 走了清单兜底/待人工


def _in_range(v: float, rng: str) -> bool:
    """解析 "(125,280]" / "[22,30]" 区间串。"""
    import re
    m = re.match(r"^([\[(])(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)([\])])$", rng.strip())
    if not m:
        return False
    lo, hi = float(m.group(2)), float(m.group(3))
    ok_lo = v > lo if m.group(1) == "(" else v >= lo
    ok_hi = v <= hi if m.group(4) == "]" else v < hi
    return ok_lo and ok_hi


class LookupEngine:
    def __init__(self, tables: dict):
        self.t = tables

    def _hit(self, name: str, **idx) -> Hit | None:
        spec = self.t.get(name)
        if not spec:
            return None
        for row in spec["rows"]:
            if all(
                _in_range(idx[k], row[k]) if isinstance(row.get(k), str) and ("," in str(row.get(k)) or "[" in str(row.get(k)))
                else row.get(k) == idx[k]
                for k in idx
            ):
                return Hit(name, row, row.get("src", spec.get("table", "")))
        return None

    # ── 各查表接口 ──
    def key_slot(self, d: float, b: int) -> Hit | None:
        """表 14-26：键槽 t1/t2/N9/JS9。"""
        for row in self.t["key_slot"]["rows"]:
            if row.get("b") == b and _in_range(d, row["d_range"]) and "t1" in row:
                return Hit("key_slot", row, row["src"])
        return None

    def fit(self, size: float, code: str) -> Hit | None:
        """表 18-1/18-3：孔轴配合偏差。"""
        for row in self.t["fit_tolerance"]["rows"]:
            if row.get("code") == code and _in_range(size, row["size_range"]):
                return Hit("fit_tolerance", row, row["src"])
        return None

    def precision_row(self, d: float, mn: float, grade: int = 8) -> Hit | None:
        """表 19-2/3/4：齿轮检验偏差（F_p/±f_pt/F_α/F_β/F_r）。"""
        for row in self.t["gear_precision"]["rows"]:
            if ("F_p" in row and _in_range(d, row["d_range"])
                    and _in_range(mn, row["mn_range"]) and row["grade"] == grade):
                return Hit("gear_precision", row, row["src"])
        return None

    def center_distance_tol(self, a: float, grade: str = "7~8") -> Hit | None:
        """表 19-5：±f_a。"""
        for row in self.t["center_distance_tol"]["rows"]:
            if _in_range(a, row["a_range"]) and row.get("grade") == grade:
                return Hit("center_distance_tol", row, row["src"])
        return None

    def bearing(self, model: str) -> Hit | None:
        for row in self.t["bearing_6206"]["rows"]:
            if row["model"] == model:
                return Hit("bearing_6206", row, row["src"])
        return None
