# -*- coding: utf-8 -*-
"""金样例回归断言（可独立运行：python tests/test_gold.py）。

校验 output/runs/case001绞车 的 final 表与需求文档 3.2 全表一致（金样例基准）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "output" / "runs" / "case001绞车"

EXPECT_GEAR = {  # 需求文档 3.2 金样例基准（落图口径）
    "gear.m": "2", "gear.z2": "134", "gear.z1": "27", "gear.d2": "268", "gear.da2": "272",
    "gear.df2": "263", "gear.b2": "54", "gear.a": "161", "gear.hub_d": "56", "gear.hub_l": "54",
    "gear.rim_inner": "252", "gear.d0_circle": "154", "gear.d0_hole": "59", "gear.hole_n": "6",
    "gear.web_t": "10", "gear.key_w": "10", "gear.key_depth": "39", "gear.key_len": "45",
    "gear.k": "15", "gear.W": "89.37",
}
EXPECT_SHAFT = {
    "shaft.seg1_d": "23", "shaft.seg1_l": "53", "shaft.seg2_d": "28", "shaft.seg2_l": "50",
    "shaft.seg3_d": "30", "shaft.seg3_l": "44.5", "shaft.seg4_d": "35", "shaft.seg4_l": "52",
    "shaft.seg5_d": "36", "shaft.seg5_l": "26.5", "shaft.seg6_d": "30", "shaft.seg6_l": "16",
    "shaft.total_l": "242", "shaft.key1_w": "8", "shaft.key1_l": "50",
    "shaft.key2_w": "10", "shaft.key2_l": "45", "shaft.key1_depth": "19.5", "shaft.key2_depth": "31",
}


def main() -> int:
    fails = []
    for name, expects in (("final_gear.json", EXPECT_GEAR), ("final_shaft.json", EXPECT_SHAFT)):
        table = json.loads((RUN / "extracted" / name).read_text(encoding="utf-8"))
        for fid, want in expects.items():
            got = table.get(fid, {}).get("text")
            if got != want:
                fails.append(f"{fid}: 期望 {want} 实际 {got}")
    plan = json.loads((RUN / "extracted" / "update_plan.json").read_text(encoding="utf-8"))
    if plan["summary"]["geo_ops"] != 0:
        fails.append(f"金样例几何变更 {plan['summary']['geo_ops']} 处（应零变更，R-3）")
    summary=json.loads((RUN/'run_summary.json').read_text(encoding='utf-8'))
    if summary.get('stage')!='DONE':
        fails.append('当前运行尚未验收完成')
    for part,name in (('gear','大齿轮'),('shaft','输出轴')):
        entry=summary.get('delivery',{}).get(part,{})
        ext='.dwg' if entry.get('mode')=='dwg' else '.dxf'
        if not (RUN/(name+ext)).exists():
            fails.append(f'缺交付 {name}{ext}')
    if fails:
        print("金样例断言失败：")
        for x in fails:
            print(" -", x)
        return 1
    print(f"金样例断言全过：gear {len(EXPECT_GEAR)} 项 + shaft {len(EXPECT_SHAFT)} 项，几何零变更，交付齐备")
    return 0


if __name__ == "__main__":
    sys.exit(main())
