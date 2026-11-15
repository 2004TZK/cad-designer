# -*- coding: utf-8 -*-
"""文本勘察：参数表/技术要求/标题栏全量 dump。"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"D:\CODE\cad-designer\src")
import ezdxf

for name in ["大齿轮"]:
    doc = ezdxf.readfile(rf"D:\CODE\cad-designer\dwg\{name}.dxf")
    msp = doc.modelspace()
    print(f"===== {name} 全部 MTEXT =====")
    for e in sorted(msp.query("MTEXT"), key=lambda e: (-e.dxf.insert.y, e.dxf.insert.x)):
        x, y = e.dxf.insert.x, e.dxf.insert.y
        print(f"#{e.dxf.handle} ({x:6.1f},{y:6.1f}) {e.plain_text()!r}")
    print("\nLEADER:")
    for e in msp.query("LEADER"):
        print(f"#{e.dxf.handle} n={len(e.vertices)}")
    print("\nDIMENSION 完整 text:")
    for e in msp.query("DIMENSION"):
        print(f"#{e.dxf.handle} {e.dxf.text!r}  dimtype={e.dimtype}  defpoint=({e.dxf.defpoint.x:.1f},{e.dxf.defpoint.y:.1f}) text_midpoint=({e.dxf.get('text_midpoint', None)})")
