# -*- coding: utf-8 -*-
"""总模板全量解析底层（T2-1 / BF-01，builder 与运行期共用）。

ezdxf 解析，$DWGCODEPAGE=ANSI_936 自动 GBK 解码统一 Unicode。
口径说明（U7 闭环记录）：需求文档 2.3 的实体统计（256 LINE/149 MTEXT/22 SOLID/
33 POINT…）为「模型空间 + 全部块定义（含匿名 *D 尺寸块）」全文件口径；本解析器
以模型空间为操作口径，同时输出块定义统计供口径对账。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.entities import DXFEntity

# DIMENSION text override 中 MTEXT 公差堆叠的解析辅助：%%C→φ，\S..^..;→上下偏差
_PARTS_STYLE = ("\\A1;", "\\S", "^", ";")


@dataclass
class TextValue:
    """一条落图文本值（MTEXT/DIMENSION/TOLERANCE/TEXT 统一抽象）。"""

    handle: str
    kind: str          # mtext | dimension | tolerance | text
    layer: str
    raw: str           # 原始文本（含格式码）
    plain: str         # 去格式码文本（对照用）
    x: float = 0.0
    y: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class GeoEntity:
    """一条几何实体（LINE/ARC/CIRCLE/LWPOLYLINE/HATCH/POINT/SOLID/INSERT）。"""

    handle: str
    type: str
    layer: str
    data: dict = field(default_factory=dict)  # type 相关几何数据


@dataclass
class ParsedTemplate:
    path: Path
    dxfversion: str
    codepage: str
    layers: list[str]
    text_styles: list[str]
    entities: list[GeoEntity]
    texts: list[TextValue]
    block_stats: dict[str, dict]      # 块名 → {实体类型: 数量}（口径对账）
    ms_stats: dict[str, int]          # 模型空间实体统计
    bbox: tuple[float, float, float, float]  # 模型空间包围盒

    def text_by_handle(self, handle: str) -> TextValue | None:
        for t in self.texts:
            if t.handle == handle:
                return t
        return None

    def entity_by_handle(self, handle: str) -> GeoEntity | None:
        for e in self.entities:
            if e.handle == handle:
                return e
        return None


def _plain_mtext(e: DXFEntity) -> str:
    try:
        return e.plain_text()
    except Exception:  # pragma: no cover - 个别损坏文本
        return str(e.dxf.get("text", ""))


def _dim_plain(text: str) -> str:
    """DIMENSION text override → 可读文本（%%C→φ，堆叠 \S+0.030^0; → +0.030/0）。"""
    s = text.replace("%%c", "%%C").replace("%%C", "φ").replace("%%p", "±")
    if "\\S" in s:
        # 取第一个堆叠段
        i = s.index("\\S")
        j = s.index("^", i)
        k = s.index(";", j)
        sup, sub = s[i + 2 : j], s[j + 1 : k]
        s = s[:i] + f"{sup}/{sub}" + s[k + 1 :]
    return s.replace("{", "").replace("}", "").replace("\\H0.71x;", "").replace("\\C3;", "").strip()


def parse_template(path: str | Path) -> ParsedTemplate:
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    entities: list[GeoEntity] = []
    texts: list[TextValue] = []

    for e in msp:
        t = e.dxftype()
        h = e.dxf.handle
        layer = e.dxf.get("layer", "0")
        if t == "LINE":
            entities.append(GeoEntity(h, t, layer, {
                "start": (e.dxf.start.x, e.dxf.start.y),
                "end": (e.dxf.end.x, e.dxf.end.y),
            }))
        elif t == "ARC":
            entities.append(GeoEntity(h, t, layer, {
                "center": (e.dxf.center.x, e.dxf.center.y),
                "radius": e.dxf.radius,
                "start_angle": e.dxf.start_angle,
                "end_angle": e.dxf.end_angle,
            }))
        elif t == "CIRCLE":
            entities.append(GeoEntity(h, t, layer, {
                "center": (e.dxf.center.x, e.dxf.center.y),
                "radius": e.dxf.radius,
            }))
        elif t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            entities.append(GeoEntity(h, t, layer, {"points": pts, "closed": e.closed}))
        elif t == "HATCH":
            entities.append(GeoEntity(h, t, layer, {"paths": len(e.paths)}))
        elif t in ("POINT", "SOLID", "INSERT", "LEADER"):
            d: dict = {}
            if t == "INSERT":
                d = {"name": e.dxf.get("name", ""), "insert": (e.dxf.insert.x, e.dxf.insert.y)}
            elif t == "LEADER":
                d = {"n_vertices": len(e.vertices)}
            entities.append(GeoEntity(h, t, layer, d))

        # 文本值表
        if t == "MTEXT":
            ins = e.dxf.insert
            texts.append(TextValue(h, "mtext", layer, e.text, _plain_mtext(e), ins.x, ins.y))
        elif t == "TEXT":
            ins = e.dxf.insert
            texts.append(TextValue(h, "text", layer, e.dxf.get("text", ""), e.dxf.get("text", ""), ins.x, ins.y))
        elif t == "DIMENSION":
            override = e.dxf.get("text", "")
            dp = e.dxf.defpoint
            texts.append(TextValue(
                h, "dimension", layer, override, _dim_plain(override) if override else "<由几何测量>",
                dp.x, dp.y, {"dimtype": e.dimtype & 7},
            ))
        elif t == "TOLERANCE":
            ins = e.dxf.insert
            content = e.dxf.get("content", "")
            plain = content.replace("\\Fgdt;", "").replace("%%v", "|").strip()
            texts.append(TextValue(h, "tolerance", layer, content, plain, ins.x, ins.y))

    xs = [p for e in entities for p in (
        [e.data.get("start", e.data.get("center", (None, None)))] if e.type in ("LINE", "ARC", "CIRCLE") else []
    )]
    bbox = (0.0, 0.0, 0.0, 0.0)
    all_pts = []
    for e in entities:
        if e.type == "LINE":
            all_pts += [e.data["start"], e.data["end"]]
        elif e.type in ("ARC", "CIRCLE"):
            all_pts.append(e.data["center"])
        elif e.type == "LWPOLYLINE":
            all_pts += e.data["points"]
    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        bbox = (min(xs), min(ys), max(xs), max(ys))

    ms_stats: dict[str, int] = {}
    for e in msp:
        ms_stats[e.dxftype()] = ms_stats.get(e.dxftype(), 0) + 1

    block_stats: dict[str, dict] = {}
    for blk in doc.blocks:
        if blk.name.startswith("*Model_Space") or blk.name.startswith("*Paper_Space"):
            continue
        st: dict[str, int] = {}
        for e in blk:
            st[e.dxftype()] = st.get(e.dxftype(), 0) + 1
        block_stats[blk.name] = st

    return ParsedTemplate(
        path=Path(path),
        dxfversion=doc.dxfversion,
        codepage=doc.header.get("$DWGCODEPAGE", ""),
        layers=[l.dxf.name for l in doc.layers],
        text_styles=[s.dxf.name for s in doc.styles],
        entities=entities,
        texts=texts,
        block_stats=block_stats,
        ms_stats=ms_stats,
        bbox=bbox,
    )
