# -*- coding: utf-8 -*-
"""参数化几何组归组（T2-4 / BF-01，改造方案 §2.2 GG-1~GG-7）。

归组策略（构建期一次，资产化）：
- 依几何特征规则将模型空间实体归入 GG-1~GG-7 + 结构区 + 继承区，全部实体 100% 归组（R4 门禁）；
- 同时产出「参数化草图模型」（sketch model：scale/center/segments/…），
  运行期 G1~G5 更新算子按模型重算实体几何——这是"小幅差异参数化局部更新"的落地。

实测基准（2026-11-14 勘察，写死并断言校验，模板冻结后不再漂移）：
- 大齿轮：比例 1:1.5，剖视中心 (82, 148.5)，轴向 x∈[64.03,100.03]=b2/1.5，径向 y；
  侧视中心 (233.7,148.5)，孔 r=11.67（φ35/1.5），键槽 x 230.36~237.03。
- 输出轴：比例 1:1，轴线 y=187，六段 x 边界 [100,152,202,246.5,298.5,325,340(341)]，
  半径 [11.5,14,15,17.5,18,15]；键槽1 x 105~147（宽8），键槽2 x 255~290（宽10）。
"""
from __future__ import annotations

from collections import defaultdict

from ..parsers.template_parser import ParsedTemplate

TOL = 0.35  # 几何匹配容差（图纸单位）


def _approx(a: float, b: float, tol: float = TOL) -> bool:
    return abs(a - b) <= tol


class GeoGroups:
    """单个零件的几何归组结果（可 json 序列化）。"""

    def __init__(self, part: str):
        self.part = part
        self.scale = 1.0
        self.center = {"x": 0.0, "y": 0.0}
        self.groups: dict[str, dict] = {}   # group_id → {name, drivers, entities{handle:role}}
        self.inherited_zones: list[dict] = []
        self.structure_zone: list[str] = []  # 图框/表格等结构资产 handle（R-2 零变更）
        self.sketch: dict = {}               # 参数化草图模型

    def add(self, gid: str, name: str, handle: str, role: str, drivers: list[str] | None = None):
        g = self.groups.setdefault(gid, {"name": name, "drivers": drivers or [], "entities": {}})
        g["entities"][handle] = role

    def all_handles(self) -> set[str]:
        s = set(self.structure_zone)
        for g in self.groups.values():
            s |= set(g["entities"])
        for z in self.inherited_zones:
            s |= set(z["entities"])
        return s

    def to_dict(self) -> dict:
        return {
            "part": self.part,
            "scale": self.scale,
            "center": self.center,
            "groups": self.groups,
            "inherited_zones": self.inherited_zones,
            "structure_zone": sorted(set(self.structure_zone)),
            "sketch": self.sketch,
        }


# ─────────────────────────── 大齿轮 ───────────────────────────

def group_gear(pt: ParsedTemplate) -> GeoGroups:
    gg = GeoGroups("gear")
    gg.scale = 1.5
    cx, cy = 82.0, 148.5
    gg.center = {"x": cx, "y": cy}
    s = gg.scale
    # 草图模型：驱动参数 → 几何（单位：图纸坐标）
    gg.sketch = {
        "section_x": [64.03, 100.03],          # b2=54/1.5=36
        "r_tip": 272 / 2 / s,                   # 90.67
        "r_rim": 252 / 2 / s,                   # 84.0
        "r_hub": 56 / 2 / s,                    # 18.67
        "r_bore": 35 / 2 / s,                   # 11.67
        "web_half_t": 10 / 2 / s,               # 3.33（腹板厚 10）
        "hole_center_r": 154 / 2 / s,           # 51.33（分布圆 154）
        "r_hole": 59 / 2 / s,                   # 19.67（孔 59）
        "fillet_r": 5 / s,                      # 3.33（未注圆角 R5）
        "side_cx": 233.7,
        "key_w_half": 10 / 2 / s,               # 键槽宽 10（侧视）
        "key_depth": 39 / 2 / s,                # d+t₂=39
    }
    D = gg.sketch

    sec_x0, sec_x1 = D["section_x"]
    side_cx = D["side_cx"]

    for e in pt.entities:
        h, t, lay = e.handle, e.type, e.layer
        if t == "LINE":
            (x0, y0), (x1, y1) = e.data["start"], e.data["end"]
            horiz = _approx(y0, y1)
            vert = _approx(x0, x1)
            # 中心线层 → GG-7
            if lay == "中心线":
                gg.add("GG-7", "中心线", h, "centerline")
                continue
            # 图框/标题栏/参数表结构区
            if (lay == "粗实线" and _approx(y0, 5.0) and _approx(y1, 5.0)) or \
               (lay == "粗实线" and max(y0, y1) <= 40.5 and min(x0, x1) >= 264.5) or \
               (lay == "粗实线" and min(x0, x1) >= 344.5 and max(y0, y1) >= 172.5):
                gg.structure_zone.append(h)
                continue
            if lay in ("细实线", "细实线层", "尺寸线") and min(x0, x1) >= 260 and max(y0, y1) <= 295 \
               and min(x0, x1) >= 260 and (max(y0, y1) <= 64.5 or min(x0, x1) >= 344.5):
                # 标题栏细格线（y<65）与参数表格线（x≥345）
                gg.structure_zone.append(h)
                continue
            if vert and _approx(x0, side_cx, 0.5) and lay in ("细实线", "细实线层", "文字"):
                gg.structure_zone.append(h)
                continue
            # 剖视图（x < 150）
            if max(x0, x1) < 150:
                if vert:
                    if _approx(x0, sec_x0) or _approx(x0, sec_x1):
                        # 端面竖线（含倒角小段）
                        if abs(max(y0, y1) - min(y0, y1)) > 3 * D["web_half_t"]:
                            gg.add("GG-1", "齿轮外廓", h, f"face_vert@{x0:.1f}")
                        else:
                            gg.add("GG-2", "减重孔/腹板", h, "web_vert")
                    elif _approx(x0, cx - D["web_half_t"]) or _approx(x0, cx + D["web_half_t"]):
                        gg.add("GG-2", "减重孔/腹板", h, "web_vert")
                    elif _approx(x0, 64.70) or _approx(x0, 99.36):
                        gg.add("GG-2", "减重孔/腹板", h, "chamfer_vert")
                    else:
                        gg.inherited_zones.append({"id": "Z-sec-vert", "entities": [h],
                                                   "reason": "剖视未归类竖线（继承区）"})
                else:  # 水平线，按半径归类
                    r = abs(y0 - cy)
                    if _approx(r, D["r_tip"], 0.5):
                        gg.add("GG-1", "齿轮外廓", h, "rim_tip")
                    elif _approx(r, D["r_rim"], 0.5):
                        gg.add("GG-1", "齿轮外廓", h, "rim_inner")
                    elif _approx(r, D["r_hub"], 0.5):
                        gg.add("GG-3", "轮毂/键槽", h, "hub_outer")
                    elif _approx(r, D["r_bore"], 0.5):
                        gg.add("GG-3", "轮毂/键槽", h, "bore")
                    elif _approx(r, D["hole_center_r"] + D["r_hole"], 0.5) or _approx(r, D["hole_center_r"] - D["r_hole"], 0.5):
                        gg.add("GG-2", "减重孔/腹板", h, "hole_edge")
                    else:
                        gg.inherited_zones.append({"id": "Z-sec-horiz", "entities": [h],
                                                   "reason": f"剖视未归类水平线 r={r:.2f}（继承区）"})
            else:
                # 侧视图（x > 150）
                if vert and (_approx(x0, side_cx - D["key_w_half"]) or _approx(x0, side_cx + D["key_w_half"])):
                    gg.add("GG-3", "轮毂/键槽", h, "side_key_vert")
                elif horiz and (_approx(y0, cy + D["key_depth"]) or _approx(y0, cy - D["key_depth"])):
                    gg.add("GG-3", "轮毂/键槽", h, "side_key_horiz")
                else:
                    gg.inherited_zones.append({"id": "Z-side", "entities": [h],
                                               "reason": "侧视细线（继承区）"})
        elif t == "ARC":
            c = e.data["center"]
            if _approx(e.data["radius"], D["fillet_r"], 0.2) and max(c) < 150:
                gg.add("GG-6", "剖面过渡圆角", h, "fillet_arc")
            elif _approx(e.data["radius"], D["r_bore"], 0.2):
                gg.add("GG-3", "轮毂/键槽", h, "side_bore_arc")
            else:
                gg.inherited_zones.append({"id": "Z-arc", "entities": [h], "reason": "未归类圆弧（继承区）"})
        elif t == "HATCH":
            gg.add("GG-6", "剖面线", h, "hatch")
        elif t == "LWPOLYLINE":
            gg.inherited_zones.append({"id": "Z-lwpoly", "entities": [h], "reason": "多段线（粗糙度勾，继承区）"})
        elif t in ("DIMENSION", "TOLERANCE", "MTEXT", "LEADER"):
            gg.structure_zone.append(h)  # 标注类由 layout_rules 管辖（G4/G5 走文本/微调）
        else:
            gg.structure_zone.append(h)

    # 侧视 bore arc 之外未归组检查放 regress；此处先合并继承区同名桶
    merged: dict[str, dict] = {}
    for z in gg.inherited_zones:
        bucket = merged.setdefault(z["id"], {"id": z["id"], "reason": z["reason"], "entities": []})
        bucket["entities"] += z["entities"]
    gg.inherited_zones = list(merged.values())
    # 标注类（DIMENSION/MTEXT/TOLERANCE）入结构区：由 bindings/layout_rules 管辖（G4/G5 走文本/微调）
    for t in pt.texts:
        gg.structure_zone.append(t.handle)
    return gg


# ─────────────────────────── 输出轴 ───────────────────────────

def group_shaft(pt: ParsedTemplate) -> GeoGroups:
    gg = GeoGroups("shaft")
    gg.scale = 1.0
    axis_y = 187.0
    gg.center = {"x": 100.0, "y": axis_y}
    # 草图模型：六段轴（x 边界与半径，图纸=实际 1:1）。
    # 段长含端面 1mm 倒角小阶：seg1 几何 x 99~152（=53），seg6 325~341（=16）；
    # sub_steps 记录小阶位置（φ 段内竖线），平移时随段移动。
    gg.sketch = {
        "axis_y": axis_y,
        "segments": [
            {"x0": 99.0, "x1": 152.0, "r": 11.5},    # 1 φ23×53
            {"x0": 152.0, "x1": 202.0, "r": 14.0},   # 2 φ28×50
            {"x0": 202.0, "x1": 246.5, "r": 15.0},   # 3 φ30×44.5
            {"x0": 246.5, "x1": 298.5, "r": 17.5},   # 4 φ35×52
            {"x0": 298.5, "x1": 325.0, "r": 18.0},   # 5 φ36×26.5
            {"x0": 325.0, "x1": 341.0, "r": 15.0},   # 6 φ30×16
        ],
        "sub_steps": {"1": 100.0, "6": 340.0},   # 段内 1mm 小阶（轮廓竖线）
        "keyways": [
            {"seg": 1, "x0": 105.0, "x1": 147.0, "half_w": 4.0},   # 8 宽
            {"seg": 4, "x0": 255.0, "x1": 290.0, "half_w": 5.0},   # 10 宽
        ],
        "sections": {"F-F": 129.0, "G-G": 203.0},
    }
    SK = gg.sketch

    def seg_index_at(x: float) -> int | None:
        for i, sg in enumerate(SK["segments"]):
            if sg["x0"] - 0.6 <= x <= sg["x1"] + 0.6:
                return i
        return None

    for e in pt.entities:
        h, t, lay = e.handle, e.type, e.layer
        if t == "LINE":
            (x0, y0), (x1, y1) = e.data["start"], e.data["end"]
            horiz = _approx(y0, y1)
            vert = _approx(x0, x1)
            if lay == "中心线":
                gg.add("GG-7", "中心线", h, "centerline")
                continue
            # 结构区：图框（25..415 × 5..292）与标题栏（265..415 × 5..40）
            if _approx(min(x0, x1), 25.0) or _approx(max(x0, x1), 415.0) or _approx(min(y0, y1), 5.0) or _approx(max(y0, y1), 292.0):
                if max(x0, x1) >= 414 or min(x0, x1) <= 25.5 or max(y0, y1) >= 291.5 or min(y0, y1) <= 5.5:
                    if not (175 < y0 < 212 or 165 < y1 < 212):
                        gg.structure_zone.append(h)
                        continue
            if min(x0, x1) >= 264.5 and max(y0, y1) <= 40.5:
                gg.structure_zone.append(h)
                continue
            if lay == "尺寸线" and min(x0, x1) >= 200 and max(y0, y1) <= 70:
                gg.structure_zone.append(h)  # 技术要求下方横线
                continue
            if horiz and abs(y0 - axis_y) < 0.2 and lay == "粗实线":
                gg.add("GG-7", "中心线", h, "axis")  # 轴线画在粗实线的个别（归中心线组跟随）
                continue
            if horiz:
                dy = abs(y0 - axis_y)
                xmid = (x0 + x1) / 2
                seg = seg_index_at(xmid)
                # 键槽半宽判定优先
                is_key = False
                for kw in SK["keyways"]:
                    if kw["x0"] - 0.6 <= xmid <= kw["x1"] + 0.6 and _approx(dy, kw["half_w"], 0.3):
                        gg.add("GG-5", "键槽（轴）", h, f"key{kw['seg']}_edge")
                        is_key = True
                if is_key:
                    continue
                if seg is not None and _approx(dy, SK["segments"][seg]["r"], 0.3):
                    gg.add("GG-4", "轴段轮廓", h, f"seg{seg+1}_outline")
                    continue
                # 断面图（y < 130）
                if max(y0, y1) < 130:
                    gg.add("GG-5", "键槽（轴）", h, "section_edge")
                    continue
                gg.inherited_zones.append({"id": "Z-horiz", "entities": [h], "reason": f"未归类水平线 dy={dy:.1f}"})
                continue
            if vert:
                x = x0
                # 断面图竖线
                if max(y0, y1) < 130:
                    gg.add("GG-5", "键槽（轴）", h, "section_edge")
                    continue
                # 轴肩/端面竖线
                seg = seg_index_at(x - 0.3) or seg_index_at(x + 0.3)
                if _approx(abs(y0 - y1), 2 * SK["segments"][3 if False else 0]["r"], 200):
                    pass
                matched = False
                for i, sg in enumerate(SK["segments"]):
                    if _approx(x, sg["x0"]) or _approx(x, sg["x1"]):
                        gg.add("GG-4", "轴段轮廓", h, f"boundary@{x:.1f}")
                        matched = True
                        break
                if not matched and any(_approx(x, xs) for xs in SK.get("sub_steps", {}).values()):
                    gg.add("GG-4", "轴段轮廓", h, f"substep@{x:.1f}")
                    matched = True
                if matched:
                    continue
                # 键槽主视图深度小竖线 / 断面剖切标记（5 长）
                if abs(y0 - y1) <= 6:
                    gg.add("GG-5", "键槽（轴）", h, "key_mark")
                    continue
                gg.inherited_zones.append({"id": "Z-vert", "entities": [h], "reason": f"未归类竖线 x={x:.1f}"})
                continue
            gg.inherited_zones.append({"id": "Z-line", "entities": [h], "reason": "斜线（继承区）"})
        elif t == "ARC":
            gg.inherited_zones.append({"id": "Z-arc", "entities": [h], "reason": "圆弧（退刀/过渡，继承区）"})
        elif t == "HATCH":
            gg.add("GG-6", "剖面线", h, "hatch")
        elif t == "LWPOLYLINE":
            gg.inherited_zones.append({"id": "Z-lwpoly", "entities": [h], "reason": "多段线（继承区）"})
        elif t in ("DIMENSION", "TOLERANCE", "MTEXT", "LEADER"):
            gg.structure_zone.append(h)
        else:
            gg.structure_zone.append(h)

    merged: dict[str, dict] = {}
    for z in gg.inherited_zones:
        bucket = merged.setdefault(z["id"], {"id": z["id"], "reason": z["reason"], "entities": []})
        bucket["entities"] += z["entities"]
    gg.inherited_zones = list(merged.values())
    # 标注类入结构区（同大齿轮）
    for t in pt.texts:
        gg.structure_zone.append(t.handle)
    return gg
