# -*- coding: utf-8 -*-
"""构造变体算例 case002变体（T5-1，缺省人工构造路径）。

变化（小幅差异边界内，U13）：减重孔数量 6→4（manual）、输出轴第 4 段长 52→56（S/R）。
结构形式/视图方案/其余参数零变更。
"""
import shutil
from pathlib import Path

ROOT = Path(r"D:\CODE\cad-designer")
SRC = ROOT / "docs"
DST = ROOT / "input" / "case002变体"
DST.mkdir(parents=True, exist_ok=True)

# S 说明书：轴段 4 52.0→56.0
s = (SRC / "一级减速器(含开式齿轮)设计说明书.txt").read_text(encoding="utf-8")
s2 = s.replace("23×53.0，28×50，30×44.5，35×52.0，36×26.5，30×16mm",
               "23×53.0，28×50，30×44.5，35×56.0，36×26.5，30×16mm")
assert s2 != s, "S 轴段行未命中"
(DST / "一级减速器(含开式齿轮)设计说明书.txt").write_text(s2, encoding="utf-8")

# R 取数报告：分段行同步（联动留痕）
r = (SRC / "减速器CAD取数报告.txt").read_text(encoding="utf-8")
r2 = r.replace("分段: 23×53, 28×50, 30×44.5, 35×52, 36×26.5, 30×16",
               "分段: 23×53, 28×50, 30×44.5, 35×56, 36×26.5, 30×16")
assert r2 != r, "R 分段行未命中"
(DST / "减速器CAD取数报告.txt").write_text(r2, encoding="utf-8")

# D 绘图数据：减重孔数量 6→4 + 直径 59→52（manual 选定值变化；直径变化触发 G1 几何更新）
d = (SRC / "减速器绘图数据.txt").read_text(encoding="utf-8")
d2 = d.replace("减重孔数量 6       = 6（选择）公式未给孔数，常用 4~8，取 6",
               "减重孔数量 4       = 4（选择）公式未给孔数，常用 4~8，取 4")
assert d2 != d, "D 减重孔数量行未命中"
d3 = d2.replace("减重孔直径 Ø59    = 59（取值）公式 d0=0.25(D1−d1) 得 49，图纸为 59；以图纸为准",
                "减重孔直径 Ø52    = 52（取值）公式 d0=0.25(D1−d1) 得 49，图纸为 52；以图纸为准")
assert d3 != d2, "D 减重孔直径行未命中"
(DST / "减速器绘图数据.txt").write_text(d3, encoding="utf-8")

# U9 演示：标题栏注入（设计者/班级/学号）
(DST / "case.yaml").write_text(
    "title:\n  designer: 张三\n  course: 机械设计课程设计\n  class_no: 飞制2401\n  student_no: 2024010101\n",
    encoding="utf-8")

print("变体算例就绪:", DST, "（含 U9 case.yaml）")
