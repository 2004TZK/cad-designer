# -*- coding: utf-8 -*-
"""几何勘察第二遍：INSERT/LINE 分布与减重孔定位。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import ezdxf
from collections import Counter

for name in ["大齿轮", "输出轴"]:
    path = rf"D:\CODE\cad-designer\dwg\{name}.dxf"
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    print("=" * 70)
    print(f"模板: {name}")
    print("全部类型:", dict(Counter(e.dxftype() for e in msp)))
    print("\nINSERT:")
    for e in msp.query("INSERT"):
        print(f"  #{e.dxf.handle} L={e.dxf.layer} blk={e.dxf.name} at=({e.dxf.insert.x:.1f},{e.dxf.insert.y:.1f}) scale={e.dxf.xscale}")
    print("\nLINE 按层统计:", dict(Counter(e.dxf.layer for e in msp.query("LINE"))))
    print("\n中心线层 LINE:")
    for e in msp.query("LINE[layer=='中心线']"):
        print(f"  #{e.dxf.handle} ({e.dxf.start.x:.1f},{e.dxf.start.y:.1f})-({e.dxf.end.x:.1f},{e.dxf.end.y:.1f})")
    if name == "大齿轮":
        print("\n粗实线 LINE（全部）:")
        for e in msp.query("LINE[layer=='粗实线']"):
            print(f"  #{e.dxf.handle} ({e.dxf.start.x:.2f},{e.dxf.start.y:.2f})-({e.dxf.end.x:.2f},{e.dxf.end.y:.2f})")
        print("\n双点划线/虚线/细实线层 LINE:")
        for e in msp.query("LINE"):
            if e.dxf.layer in ("双点划线", "虚线", "细实线"):
                print(f"  #{e.dxf.handle} L={e.dxf.layer} ({e.dxf.start.x:.1f},{e.dxf.start.y:.1f})-({e.dxf.end.x:.1f},{e.dxf.end.y:.1f})")
    else:
        # 轴：找 6 段轴轮廓的水平线
        print("\n粗实线水平线（y 相同 ±0.1）:")
        for e in msp.query("LINE[layer=='粗实线']"):
            if abs(e.dxf.start.y - e.dxf.end.y) < 0.1:
                print(f"  #{e.dxf.handle} y={e.dxf.start.y:.2f} x:{e.dxf.start.x:.2f}~{e.dxf.end.x:.2f} len={abs(e.dxf.end.x-e.dxf.start.x):.2f}")
        print("\n粗实线垂直线:")
        for e in msp.query("LINE[layer=='粗实线']"):
            if abs(e.dxf.start.x - e.dxf.end.x) < 0.1:
                print(f"  #{e.dxf.handle} x={e.dxf.start.x:.2f} y:{e.dxf.start.y:.2f}~{e.dxf.end.y:.2f} len={abs(e.dxf.end.y-e.dxf.start.y):.2f}")
