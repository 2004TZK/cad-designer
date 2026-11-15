# -*- coding: utf-8 -*-
"""模板 DXF 结构预研（一次性勘察脚本，不属于交付代码）。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import ezdxf
from collections import Counter

for name in ["大齿轮", "输出轴"]:
    path = rf"D:\CODE\cad-designer\dwg\{name}.dxf"
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    print("=" * 70)
    print(f"模板: {name}  DXF版本={doc.dxfversion}  codepage={doc.header.get('$DWGCODEPAGE')}")
    types = Counter(e.dxftype() for e in msp)
    print("模型空间实体统计:", dict(types))
    for layout_name in doc.layout_names():
        layout = doc.layout(layout_name)
        pt = Counter(e.dxftype() for e in layout)
        tag = "模型空间" if layout_name == "Model" else f"图纸空间[{layout_name}]"
        if layout_name != "Model" and pt:
            print(f"  {tag}:", dict(pt))
    for blk in doc.blocks:
        if blk.name.startswith("*"):
            continue
        bt = Counter(e.dxftype() for e in blk)
        if bt:
            print(f"  块[{blk.name}]:", dict(bt))
    print("\n图层:")
    for layer in doc.layers:
        print(f"  {layer.dxf.name}")
    print("\n文字样式:", [ts.dxf.name for ts in doc.styles])
    # 文本值表
    print("\nMTEXT 样本（前 40 条，带 handle/layer/插入点）:")
    n = 0
    for e in msp.query("MTEXT"):
        txt = e.plain_text().replace("\n", "|")[:60]
        print(f"  #{e.dxf.handle} L={e.dxf.layer} ({e.dxf.insert.x:.0f},{e.dxf.insert.y:.0f}) {txt}")
        n += 1
        if n >= 40:
            break
    print("\nDIMENSION 样本（前 30 条）:")
    n = 0
    for e in msp.query("DIMENSION"):
        t = e.dxf.text if isinstance(e.dxf.text, str) else ""
        print(f"  #{e.dxf.handle} L={e.dxf.layer} type={e.dimtype} text={t!r} defpoint=({e.dxf.defpoint.x:.1f},{e.dxf.defpoint.y:.1f})")
        n += 1
        if n >= 30:
            break
    print("\nTOLERANCE:")
    for e in msp.query("TOLERANCE"):
        attribs = e.dxf.all_existing_dxf_attribs()
        print(f"  #{e.dxf.handle} L={e.dxf.layer} {attribs.get('text', attribs)}")
    print("\nCIRCLE/ARC（大齿轮）/LINE 端点范围:")
    if name == "大齿轮":
        for e in msp.query("CIRCLE"):
            print(f"  C #{e.dxf.handle} L={e.dxf.layer} c=({e.dxf.center.x:.1f},{e.dxf.center.y:.1f}) r={e.dxf.radius:.2f}")
        for e in msp.query("ARC"):
            print(f"  A #{e.dxf.handle} L={e.dxf.layer} c=({e.dxf.center.x:.1f},{e.dxf.center.y:.1f}) r={e.dxf.radius:.2f} {e.dxf.start_angle:.0f}~{e.dxf.end_angle:.0f}")
    print("\nPOINT 层分布:", Counter(e.dxf.layer for e in msp.query("POINT")))
    print("LWPOLYLINE:")
    for e in msp.query("LWPOLYLINE"):
        pts = list(e.get_points("xy"))
        print(f"  P #{e.dxf.handle} L={e.dxf.layer} n={len(pts)} 首点={pts[0] if pts else None}")
    print("HATCH 层分布:", Counter(e.dxf.layer for e in msp.query("HATCH")))
