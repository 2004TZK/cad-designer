# -*- coding: utf-8 -*-
"""同构 SRD 解析（FR-01 / T4-1）。

B1 边界约束：新算例章节结构与金样例同构，解析为「行标签 → 值」正则规则库；
格式校验前置（U13）：必需章节缺失 → 拒收算例（RejectCaseError）。
个别字段正则失败 → llm.advisor 兜底位（FR-14，MVP 未启用留 TODO 留痕）。

取值优先级（清单 §1）：D 第六节（图纸定稿）> S/R 计算结果 > 标准查表 > 人为选定。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import config


class RejectCaseError(Exception):
    """P1 格式校验拒收（U13）。"""


@dataclass
class Item:
    id: str
    item: str
    value: object          # 数值或文本
    unit: str = "mm"
    category: str = ""     # calculator|lookup|constant|manual（dispatcher 填写）
    source: dict = field(default_factory=dict)  # {doc, section, line}
    channel_hint: str = ""  # A（SRD 硬数据）

    def to_dict(self) -> dict:
        return {
            "id": self.id, "item": self.item, "value": self.value, "unit": self.unit,
            "category": self.category, "source": self.source, "channel_hint": self.channel_hint,
        }


# ── 正则规则库（B1 同构格式；金样例标定） ──────────────────────────

_R_FLOAT = r"(-?\d+(?:\.\d+)?)"

# S 说明书：主要设计结论行
RE_S_CONCLUSION = re.compile(
    r"主要设计结论：Z1=(\d+)、Z2=(\d+)，m=(\d+(?:\.\d+)?)mm，压力角(\d+)°，a=(\d+(?:\.\d+)?)mm，"
    r"b1=(\d+(?:\.\d+)?)mm、b2=(\d+(?:\.\d+)?)mm，d1=(\d+(?:\.\d+)?)mm、d2=(\d+(?:\.\d+)?)mm，"
    r"da1=(\d+(?:\.\d+)?)mm、da2=(\d+(?:\.\d+)?)mm，df1=(\d+(?:\.\d+)?)mm、df2=(\d+(?:\.\d+)?)mm")
RE_S_SEGMENTS = re.compile(r"轴各段直径和长度（6段）：(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)，(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)，"
                           r"(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)，(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)，"
                           r"(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)，(\d+(?:\.\d+)?)×(\d+(?:\.\d+)?)mm")
RE_S_DMIN = re.compile(r"dmin=A0×\(PII/nII\)\^\(1/3\)=(" + _R_FLOAT + r")mm")
RE_S_BEARING = re.compile(r"轴承6206（(\d+)×(\d+)×(\d+)）")
RE_S_KEY_OPEN = re.compile(r"输出轴开式齿轮处键：b×h×l=(\d+)×(\d+)×(\d+)mm")
RE_S_KEY_GEAR = re.compile(r"输出轴大齿轮处键：b×h×l=(\d+)×(\d+)×(\d+)mm")
RE_S_GEAR_MATERIAL = re.compile(r"大齿轮材料为45钢（调质），齿面硬度为(\d+)～(\d+)HBS")

# R 报告 / D 绘图数据：标签-值行（宽松匹配冒号/等号两侧空白）
def _label_line(label_re: str) -> re.Pattern:
    return re.compile(label_re + r"\s*[=:：]\s*" + _R_FLOAT)

RE_HUB_D = _label_line(r"轮毂外径(?:\s*d1)?")
RE_HUB_L = re.compile(r"轮毂长度\s*l\s*[=:：]\s*(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)")
RE_RIM_DELTA = re.compile(r"轮缘厚度\s*δ0\s*[=:：]\s*(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)")
RE_WEB_C = re.compile(r"腹板厚度\s*c\s*[=:：]\s*" + _R_FLOAT)
RE_D0_CIRCLE = _label_line(r"减重孔分布圆(?:\s*D0)?")
RE_D0_HOLE = _label_line(r"减重孔直径(?:\s*d0)?")
RE_K = _label_line(r"跨齿数(?:\s*k)?")
RE_W = _label_line(r"公法线长度(?:\s*W)?")
RE_A = _label_line(r"中心距(?:\s*a)?")
RE_M = _label_line(r"模数(?:\s*m)?")
RE_Z2 = _label_line(r"大齿轮齿数(?:\s*z2)?")
RE_D2 = _label_line(r"大齿轮分度圆(?:\s*d2)?")
RE_DA2 = _label_line(r"大齿轮齿顶圆(?:\s*da2)?")
RE_B2 = _label_line(r"大齿轮齿宽(?:\s*b2)?")
RE_D_BORE = re.compile(r"大齿轮配合轴径\s*d\s*[=:：]\s*" + _R_FLOAT)
RE_RIM_INNER_D1 = re.compile(r"轮缘内径\s*=?\s*Ø?(\d+(?:\.\d+)?)")  # D六/R L3 定稿行
RE_RIM_INNER_LBL = re.compile(r"轮缘内径\s*[=:：]\s*" + _R_FLOAT)

# 定稿行（D 六 / R L3【大齿轮】【输出轴】块内行）
RE_FINAL_HOLE_D = re.compile(r"减重孔直径\s*Ø?(\d+(?:\.\d+)?)\s*=")
RE_FINAL_HOLE_N = re.compile(r"减重孔数量\s*(\d+)\s*=")
RE_FINAL_WEB = re.compile(r"腹板厚度\s*(\d+(?:\.\d+)?)\s*=")
RE_FINAL_KEY_TOL = re.compile(r"腹板厚度公差\s*±(\d+(?:\.\d+)?)")
RE_FINAL_POS39 = re.compile(r"定位尺寸\s*(\d+(?:\.\d+)?)\s*=")
RE_FINAL_CHAMFER35 = re.compile(r"倒角\s*(\d+(?:\.\d+)?)\s*=")
RE_FINAL_KEYPOS = re.compile(r"键槽定位\s*(\d+(?:\.\d+)?)\s*=")

# 轴颈配合公差行（D 七 / R L3）：Ø23 r6 +0.050 / +0.034
RE_FIT = re.compile(r"Ø(\d+(?:\.\d+)?)\s+(\w+)\s+\+?(-?\d+(?:\.\d+)?)\s*/\s*\+?(-?\d+(?:\.\d+)?)")

# 必需章节（U13 格式校验）
REQUIRED = {
    "S": ["第一部分", "第五部分", "7.2", "第八部分", "主要设计结论"],
    "R": ["L1", "L2", "L3", "闭式齿轮", "输出轴"],
    "D": ["一、", "四、", "五、", "六、", "七、", "【大齿轮】", "【输出轴】"],
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def _sec_of(text: str, pos: int) -> str:
    """返回 pos 所在的章节标题（最近一个 「X、」/L1 行）。"""
    head = text[:pos]
    m = re.findall(r"(^第[一二三四五六七八九十]+部分[^\n]*|^\s*7\.2[^\n]*|^[一二三四五六七]、[^\n]+|^L\d[^\n]*)", head, re.M)
    return m[-1].strip() if m else ""


def parse_case(case_dir: str | Path) -> dict:
    """解析算例目录下三份 SRD → {gear:[Item], shaft:[Item], srd:{S,R,D 原文}}。

    格式校验失败抛 RejectCaseError（U13）。
    """
    cdir = Path(case_dir)
    files = {
        "S": cdir / config.S_FILE,
        "R": cdir / config.R_FILE,
        "D": cdir / config.D_FILE,
    }
    missing = [k for k, p in files.items() if not p.exists()]
    if missing:
        raise RejectCaseError(f"算例输入缺失文档: {missing}（应含 {list(files.values())}）")
    texts = {k: _read(p) for k, p in files.items()}

    # ── 格式校验（U13：结构缺失拒收） ──
    for doc, keys in REQUIRED.items():
        absent = [k for k in keys if k not in texts[doc]]
        if absent:
            raise RejectCaseError(f"{doc} 文档章节结构缺失 {absent}，异构算例拒收（边界 B1/U13）")

    gear: list[Item] = []
    shaft: list[Item] = []

    def add(bucket, id_, item, value, doc, section, unit="mm"):
        bucket.append(Item(id_, item, value, unit, source={"doc": doc, "section": section}, channel_hint="A"))

    # ── S 说明书 ──
    s = texts["S"]
    m = RE_S_CONCLUSION.search(s)
    if not m:
        raise RejectCaseError("S 说明书「主要设计结论」行解析失败（异构拒收）")
    (z1, z2, mm, alpha, a, b1, b2, d1, d2, da1, da2, df1, df2) = m.groups()
    sec = _sec_of(s, m.start())
    add(gear, "gear.z1", "配对齿轮齿数 z1", int(z1), "S", sec, "齿")
    add(gear, "gear.z2", "齿数 z2", int(z2), "S", sec, "齿")
    add(gear, "gear.m", "模数 m", float(mm), "S", sec)
    add(gear, "gear.alpha", "压力角 α", float(alpha), "S", sec, "°")
    add(gear, "gear.a", "中心距 a", float(a), "S", sec)
    add(gear, "gear.b2", "齿宽 b2", float(b2), "S", sec)
    add(gear, "gear.d1", "小齿轮分度圆 d1", float(d1), "S", sec)
    add(gear, "gear.d2", "分度圆 d2", float(d2), "S", sec)
    add(gear, "gear.da2", "齿顶圆 da2", float(da2), "S", sec)
    add(gear, "gear.df2", "齿根圆 df2", float(df2), "S", sec)
    m = RE_S_DMIN.search(s)
    if m:
        add(shaft, "shaft.d_min", "最小轴径 dmin(II)", float(m.group(1)), "S", _sec_of(s, m.start()))
    m = RE_S_SEGMENTS.search(s)
    if not m:
        raise RejectCaseError("S 说明书 7.2「轴各段直径和长度（6段）」解析失败（异构拒收）")
    sec = _sec_of(s, m.start())
    vals = [float(v) for v in m.groups()]
    for i in range(6):
        add(shaft, f"shaft.seg{i+1}_d", f"第{i+1}段直径", vals[i * 2], "S", sec)
        add(shaft, f"shaft.seg{i+1}_l", f"第{i+1}段长度", vals[i * 2 + 1], "S", sec)
    m = RE_S_BEARING.search(s)
    if m:
        add(shaft, "shaft.bearing", "轴承型号 6206(d×D×B)", "6206", "S", _sec_of(s, m.start()))
        add(shaft, "shaft.bearing_dims", "轴承 6206 尺寸",
            {"d": int(m.group(1)), "D": int(m.group(2)), "B": int(m.group(3))},
            "S", _sec_of(s, m.start()))
    m = RE_S_KEY_OPEN.search(s)
    if m:
        add(shaft, "shaft.key1", "键1（φ23 处）b×h×L", tuple(int(x) for x in m.groups()), "S", _sec_of(s, m.start()))
        add(shaft, "shaft.key1_l", "键槽1长", int(m.group(3)), "S", _sec_of(s, m.start()))
    m = RE_S_KEY_GEAR.search(s)
    if m:
        add(shaft, "shaft.key2", "键2（φ35 处）b×h×L", tuple(int(x) for x in m.groups()), "S", _sec_of(s, m.start()))
        add(gear, "gear.key_len", "键槽长", int(m.group(3)), "S", _sec_of(s, m.start()))
        add(shaft, "shaft.key2_l", "键槽2长", int(m.group(3)), "S", _sec_of(s, m.start()))

    # ── R 报告 ──
    r = texts["R"]
    for pat, id_, item, bucket, unit in [
        (RE_HUB_D, "gear.hub_d", "轮毂外径", gear, "mm"),
        (RE_K, "gear.k", "公法线跨齿数 k", gear, "齿"),
        (RE_W, "gear.W", "公法线长度 W", gear, "mm"),
        (RE_D0_CIRCLE, "gear.d0_circle", "减重孔分布圆", gear, "mm"),
    ]:
        m = pat.search(r)
        if m:
            add(bucket, id_, item, float(m.group(1)), "R", _sec_of(r, m.start()), unit)
    m = RE_HUB_L.search(r)
    if m:
        add(gear, "gear.hub_l", "轮毂长度", float(m.group(1)), "R", _sec_of(r, m.start()))
    m = RE_RIM_DELTA.search(r)
    if m:
        add(gear, "gear.delta0_range", "轮缘厚度 δ0 范围", [float(m.group(1)), float(m.group(2))], "R", _sec_of(r, m.start()))
    for m in RE_FIT.finditer(r):
        dia, code, sup, sub = m.groups()
        add(shaft, f"shaft.fit{int(float(dia))}", f"Ø{dia} 配合（图纸标注）",
            {"dia": float(dia), "code": code, "sup": "+" + sup.lstrip("+"), "sub": "+" + sub.lstrip("+")},
            "R", _sec_of(r, m.start()))

    # ── D 绘图数据 ──
    d = texts["D"]
    for pat, id_, item, bucket, unit in [
        (RE_A, "gear.a", "中心距 a", gear, "mm"),
        (RE_M, "gear.m", "模数 m", gear, "mm"),
        (RE_Z2, "gear.z2", "齿数 z2", gear, "齿"),
        (RE_D2, "gear.d2", "分度圆 d2", gear, "mm"),
        (RE_DA2, "gear.da2", "齿顶圆 da2", gear, "mm"),
        (RE_B2, "gear.b2", "齿宽 b2", gear, "mm"),
        (RE_D_BORE, "gear.d_bore", "配合轴径 d", gear, "mm"),
        (RE_RIM_INNER_LBL, "gear.rim_inner", "轮缘内径", gear, "mm"),
        (RE_HUB_D, "gear.hub_d", "轮毂外径", gear, "mm"),
        (RE_D0_CIRCLE, "gear.d0_circle", "减重孔分布圆", gear, "mm"),
        (RE_K, "gear.k", "跨齿数 k", gear, "齿"),
        (RE_W, "gear.W", "公法线长度 W", gear, "mm"),
    ]:
        m = pat.search(d)
        if m:
            add(bucket, id_, item, float(m.group(1)), "D", _sec_of(d, m.start()), unit)
    m = RE_HUB_L.search(d)
    if m:
        add(gear, "gear.hub_l", "轮毂长度", float(m.group(1)), "D", _sec_of(d, m.start()))
    m = RE_RIM_DELTA.search(d)
    if m:
        add(gear, "gear.delta0_range", "轮缘厚度 δ0 范围", [float(m.group(1)), float(m.group(2))], "D", _sec_of(d, m.start()))

    # D 六 图纸定稿（优先级最高）
    if "【大齿轮】" in d:
        blk = d.split("【大齿轮】")[1].split("【输出轴】")[0]
        m = RE_RIM_INNER_D1.search(blk)
        if m:
            add(gear, "gear.rim_inner", "轮缘内径（定稿）", float(m.group(1)), "D", "六、图纸定稿数据")
        m = RE_FINAL_HOLE_D.search(blk)
        if m:
            add(gear, "gear.d0_hole", "减重孔直径（定稿·manual）", float(m.group(1)), "D", "六、图纸定稿数据")
        m = RE_FINAL_HOLE_N.search(blk)
        if m:
            add(gear, "gear.hole_n", "减重孔数量（定稿·manual）", int(m.group(1)), "D", "六、图纸定稿数据")
        m = RE_FINAL_WEB.search(blk)
        if m:
            add(gear, "gear.web_t", "腹板厚度（定稿·manual）", float(m.group(1)), "D", "六、图纸定稿数据")
        m = RE_FINAL_KEY_TOL.search(blk)
        if m:
            add(gear, "gear.key_w_tol_pm", "键槽宽公差 ±（定稿）", float(m.group(1)), "D", "六、图纸定稿数据")
        m = RE_FINAL_POS39.search(blk)
        if m:
            add(gear, "gear.key_depth", "键槽深（定稿）", float(m.group(1)), "D", "六、图纸定稿数据")
    if "【输出轴】" in d:
        blk = d.split("【输出轴】")[1].split("七、")[0] if "七、" in d else d.split("【输出轴】")[1]
        chs = [float(x) for x in RE_FINAL_CHAMFER35.findall(blk)]   # D 六 标"倒角"：3.5 / 2.0
        poss = [float(x) for x in RE_FINAL_KEYPOS.findall(blk)]     # D 六 标"键槽定位"：19.5 / 31
        # U4/C4/C5 构建期依模板图形判定（2026-11-14 实测 defpoint 锚点）：
        #   3.5 = 键槽2 轴向定位（肩 246.5→槽口端 250，DIM #115）；2.0 = 键槽1 定位（端面 99→101，#130）
        #   19.5/31 = 键槽深 1/2（d−t1 图值，断面 #841/#85C）
        if len(chs) >= 2:
            add(shaft, "shaft.key2_pos", "键槽2定位 3.5（C4 判定：键槽定位，D 六 标签'倒角'有误）",
                chs[0], "D", "六、图纸定稿数据")
            add(shaft, "shaft.key1_pos", "键槽1定位 2.0（C4 判定：键槽定位，D 六 标签'倒角'有误）",
                chs[1], "D", "六、图纸定稿数据")
        if len(poss) >= 2:
            add(shaft, "shaft.key1_depth", "键槽深1（d−t1 图值，C5 判定：键槽深，D 六 标签'键槽定位'有误）",
                poss[0], "D", "六、图纸定稿数据")
            add(shaft, "shaft.key2_depth", "键槽深2（d−t1 图值，C5 判定：键槽深）", poss[1], "D", "六、图纸定稿数据")
    # D 七 轴颈配合（图纸标注值，U1 修正对象）
    for m in RE_FIT.finditer(d):
        dia, code, sup, sub = m.groups()
        add(shaft, f"shaft.fit{int(float(dia))}", f"Ø{dia} 配合（图纸标注）",
            {"dia": float(dia), "code": code, "sup": "+" + sup.lstrip("+"), "sub": "+" + sub.lstrip("+")},
            "D", _sec_of(d, m.start()))

    # 去重（同 id 保留优先级最高：D 六 > D > R > S；列表后写优先，故按文档顺序 S,R,D 追加后倒序去重）
    def dedup(items: list[Item]) -> list[Item]:
        seen: dict[str, Item] = {}
        prio = {"D": 3, "R": 2, "S": 1}
        for it in items:
            p = prio.get(it.source["doc"], 0)
            p += 1 if "定稿" in it.source.get("section", "") else 0
            if it.id not in seen or p >= seen[it.id]._p:
                it._p = p  # type: ignore[attr-defined]
                seen[it.id] = it
        return list(seen.values())

    return {
        "gear": dedup(gear),
        "shaft": dedup(shaft),
        "srd": texts,
        "files": {k: str(p) for k, p in files.items()},
    }
