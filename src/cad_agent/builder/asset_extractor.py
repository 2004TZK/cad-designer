# -*- coding: utf-8 -*-
"""总模板资产提取（T2-3/T2-5/BF-01 + 布点绑定 T3-6 底表）。

产出 assets/template_assets.json：
- frame/layers/style_templates/tables/views  结构资产（R-2 零变更）
- value_snapshot   值快照（金样例对照基准，handle→文本）
- geo_groups       参数化几何组（geo_grouper）
- bindings         落图绑定表（item id → 实体 handle + 渲染规则，E1~E5 依据）
- u7_findings      U7 遗留项闭环结论（BF-07 硬门禁）
"""
from __future__ import annotations

import json
from datetime import datetime

from .. import config
from ..parsers.template_parser import ParsedTemplate, parse_template
from .geo_grouper import group_gear, group_shaft


# ───────────────────── 落图绑定表（布点规则，构建期判定固化） ─────────────────────
# item: 数据项 id；handle: 模板实体；render: 渲染器；expect: 构建期对账用的模板现值
# op: E1 数值修正 / E2 落格 / E4 公差修正 / E5 异常清理（G4 文本替换大类）
def _gear_bindings() -> list[dict]:
    # render 类型：dim_dia(%%C 主值)/dim_dia_tol/dim_num/dim_num_tol/dim_nxd/dim_pm/mtext
    # 同一 handle 的多个数据项写在一个 item 里（+ 连接），渲染时合并为单条文本操作
    return [
        # 剖视尺寸（DIMENSION）
        {"item": "gear.bore_d+gear.bore_tol", "handle": "EA", "kind": "dimension", "render": "dim_dia_tol", "expect": "φ35+0.030/  0", "op": "E1"},
        {"item": "gear.d2", "handle": "F8", "kind": "dimension", "render": "dim_dia", "expect": "φ268", "op": "E1"},
        {"item": "gear.da2+gear.da2_tol", "handle": "105", "kind": "dimension", "render": "dim_dia_tol", "expect": "φ272 0/ -0.300", "op": "E1"},
        {"item": "gear.hub_d", "handle": "112", "kind": "dimension", "render": "dim_dia", "expect": "φ56", "op": "E1"},
        {"item": "gear.d0_circle", "handle": "11F", "kind": "dimension", "render": "dim_dia", "expect": "φ154", "op": "E1"},
        {"item": "gear.rim_inner", "handle": "12C", "kind": "dimension", "render": "dim_dia", "expect": "φ252", "op": "E1"},
        {"item": "gear.hole_n+gear.d0_hole", "handle": "139", "kind": "dimension", "render": "dim_nxd", "expect": "6Xφ59", "op": "E1"},
        {"item": "gear.key_w", "handle": "146", "kind": "dimension", "render": "dim_num", "expect": "10", "op": "E1"},
        {"item": "gear.hub_l", "handle": "153", "kind": "dimension", "render": "dim_num", "expect": "54", "op": "E1"},
        {"item": "gear.key_w+gear.key_w_tol", "handle": "160", "kind": "dimension", "render": "dim_pm", "expect": "10±0.0215", "op": "E4"},
        {"item": "gear.key_depth+gear.key_depth_tol", "handle": "16E", "kind": "dimension", "render": "dim_num_tol", "expect": "39+0.2/  0", "op": "E1"},
        # 参数表格子（MTEXT，E2 落格）
        {"item": "gear.m", "handle": "620", "kind": "mtext", "render": "mtext", "expect": "2", "op": "E2"},
        {"item": "gear.z2", "handle": "621", "kind": "mtext", "render": "mtext", "expect": "134", "op": "E2"},
        {"item": "gear.alpha", "handle": "61D", "kind": "mtext", "render": "mtext", "expect": "20°", "op": "E2"},
        {"item": "gear.ha_star", "handle": "61E", "kind": "mtext", "render": "mtext", "expect": "1.0", "op": "E2"},
        {"item": "gear.x_shift", "handle": "622", "kind": "mtext", "render": "mtext", "expect": "0", "op": "E2"},
        {"item": "gear.precision", "handle": "623", "kind": "mtext", "render": "mtext", "expect": "8", "op": "E2"},
        {"item": "gear.a_tol_text", "handle": "624", "kind": "mtext", "render": "mtext", "expect": "161±0.032", "op": "E2"},
        {"item": "gear.z1", "handle": "625", "kind": "mtext", "render": "mtext", "expect": "27", "op": "E2"},
        {"item": "gear.F_r", "handle": "60C", "kind": "mtext", "render": "mtext", "expect": "0.043", "op": "E2"},
        {"item": "gear.F_alpha", "handle": "615", "kind": "mtext", "render": "mtext", "expect": "0.022", "op": "E2"},
        {"item": "gear.f_pt", "handle": "61C", "kind": "mtext", "render": "mtext", "expect": "±0.012", "op": "E2"},
        {"item": "gear.W", "handle": "617", "kind": "mtext", "render": "mtext", "expect": "42.439", "op": "E2"},  # U7: 遗留值→89.37
        {"item": "gear.W_tol_up", "handle": "61A", "kind": "mtext", "render": "mtext", "expect": "-0.132", "op": "E2"},
        {"item": "gear.W_tol_down", "handle": "61B", "kind": "mtext", "render": "mtext", "expect": "-0.176", "op": "E2"},
        {"item": "gear.k", "handle": "619", "kind": "mtext", "render": "mtext", "expect": "6", "op": "E2"},      # U7: 遗留值→15
        # 技术要求 / 标题栏（E2/E5）
        {"item": "gear.tech_req", "handle": "4CB", "kind": "mtext", "render": "mtext", "expect": "技术要求(45钢正火170-210HBW/R5/C2)", "op": "E2"},
        {"item": "gear.title_name", "handle": "4C0", "kind": "mtext", "render": "mtext", "expect": "大齿轮", "op": "E2"},
        {"item": "gear.title_scale", "handle": "61F", "kind": "mtext", "render": "mtext", "expect": "1:1.5", "op": "E2"},
        {"item": "gear.title_designer", "handle": "84D", "kind": "mtext", "render": "mtext", "expect": "郑佳暄", "op": "E2"},
        {"item": "gear.title_course", "handle": "4C9", "kind": "mtext", "render": "mtext", "expect": "机械设计课程设计", "op": "E2"},
        {"item": "gear.abnormal_text", "handle": "4CA", "kind": "mtext", "render": "mtext", "expect": "飞制2303|233423030303", "op": "E5"},  # U8 待确认；case.yaml 注入班级/学号时可被替换（U9）
    ]


def _shaft_bindings() -> list[dict]:
    return [
        # 轴段长
        {"item": "shaft.seg1_l", "handle": "B9", "kind": "dimension", "render": "dim_num", "expect": "53", "op": "E1"},
        {"item": "shaft.seg2_l", "handle": "C7", "kind": "dimension", "render": "dim_num", "expect": "50", "op": "E1"},
        {"item": "shaft.seg3_l", "handle": "D4", "kind": "dimension", "render": "dim_num", "expect": "44.5", "op": "E1"},
        {"item": "shaft.seg4_l", "handle": "E1", "kind": "dimension", "render": "dim_num", "expect": "52", "op": "E1"},
        {"item": "shaft.seg6_l", "handle": "EE", "kind": "dimension", "render": "dim_num", "expect": "16", "op": "E1"},
        {"item": "shaft.total_l", "handle": "FB", "kind": "dimension", "render": "dim_num", "expect": "242", "op": "E1"},
        # 键槽（3.5/2.0=键槽定位 C4 判定；19.5/31=键槽深 C5 判定）
        {"item": "shaft.key2_l", "handle": "108", "kind": "dimension", "render": "dim_num", "expect": "45", "op": "E1"},
        {"item": "shaft.key2_pos", "handle": "115", "kind": "dimension", "render": "dim_num", "expect": "3.5", "op": "E1"},
        {"item": "shaft.key1_l", "handle": "123", "kind": "dimension", "render": "dim_num", "expect": "50", "op": "E1"},
        {"item": "shaft.key1_pos", "handle": "130", "kind": "dimension", "render": "dim_num", "expect": "2", "op": "E1"},
        # 轴段径+公差（U1 修正对象）
        {"item": "shaft.seg1_d+shaft.seg1_d_tol", "handle": "13E", "kind": "dimension", "render": "dim_dia_tol", "expect": "φ23+0.050/ +0.034", "op": "E4"},
        {"item": "shaft.seg2_d", "handle": "14B", "kind": "dimension", "render": "dim_dia", "expect": "φ28", "op": "E1"},
        {"item": "shaft.seg3_d+shaft.seg3_d_tol", "handle": "158", "kind": "dimension", "render": "dim_dia_tol", "expect": "φ30+0.021/ +0.002", "op": "E4"},
        {"item": "shaft.seg4_d+shaft.seg4_d_tol", "handle": "165", "kind": "dimension", "render": "dim_dia_tol", "expect": "φ35+0.060/+0.041", "op": "E4"},
        {"item": "shaft.seg5_d", "handle": "172", "kind": "dimension", "render": "dim_dia", "expect": "φ36", "op": "E1"},
        {"item": "shaft.seg6_d+shaft.seg6_d_tol", "handle": "17F", "kind": "dimension", "render": "dim_dia_tol", "expect": "φ30+0.021/ +0.002", "op": "E4"},
        {"item": "shaft.key1_w+shaft.key1_w_tol", "handle": "833", "kind": "dimension", "render": "dim_num_tol", "expect": "8 0/ -0.043", "op": "E1"},
        {"item": "shaft.key1_depth+shaft.key1_depth_tol", "handle": "841", "kind": "dimension", "render": "dim_num_tol", "expect": "19.5 0/ -0.020", "op": "E1"},
        {"item": "shaft.key2_w+shaft.key2_w_tol", "handle": "84E", "kind": "dimension", "render": "dim_num_tol", "expect": "10 0/ -0.043", "op": "E1"},
        {"item": "shaft.key2_depth+shaft.key2_depth_tol", "handle": "85C", "kind": "dimension", "render": "dim_num_tol", "expect": "31 0/ -0.020", "op": "E1"},
        # 技术要求/标题栏
        {"item": "shaft.tech_req", "handle": "A8D", "kind": "mtext", "render": "mtext", "expect": "技术要求(调质220-250HBW/R2/C1.5)", "op": "E2"},
        {"item": "shaft.title_name", "handle": "A82", "kind": "mtext", "render": "mtext", "expect": "输出轴", "op": "E2"},
        {"item": "shaft.title_scale", "handle": "AF2", "kind": "mtext", "render": "mtext", "expect": "1:1", "op": "E2"},
        {"item": "shaft.title_designer", "handle": "C03", "kind": "mtext", "render": "mtext", "expect": "郑佳暄", "op": "E2"},
        {"item": "shaft.title_course", "handle": "A8B", "kind": "mtext", "render": "mtext", "expect": "机械设计课程设计", "op": "E2"},
        {"item": "shaft.abnormal_text", "handle": "A8C", "kind": "mtext", "render": "mtext", "expect": "飞制2303|233423030303", "op": "E5"},  # U8；case.yaml 注入（U9）
    ]


# 绑定对账：期望值与模板现值归一化比对（构建期校验 bindings 与模板一致）
def _norm_txt(s: str) -> str:
    return (s.replace("%%C", "").replace("%%P", "±").replace("φ", "")
             .replace(" ", "").replace("\n", "|"))


def _verify_bindings(part: str, pt: ParsedTemplate, bindings: list[dict]) -> list[str]:
    import re as _re
    problems = []
    for b in bindings:
        t = pt.text_by_handle(b["handle"])
        if t is None:
            problems.append(f"[{part}] 绑定 handle {b['handle']}（{b['item']}）在模板中不存在")
            continue
        exp, actual = b.get("expect", ""), _norm_txt(t.raw)
        actual_plain = _norm_txt(t.plain)
        # 有效数字 token（长度≥2）在 raw 或 plain 归一化后全部出现即通过；无数字时要求文本前缀出现
        digits = [d for d in _re.findall(r"[+-]?\d+(?:\.\d+)?", exp) if len(d.lstrip("+-")) >= 2]
        if digits:
            if not (all(d in actual for d in digits) or all(d in actual_plain for d in digits)):
                problems.append(f"[{part}] {b['item']} handle {b['handle']} 期望 '{exp}'，模板实为 '{t.plain}'")
        elif exp and exp.split("(")[0] not in t.plain and exp.split("(")[0] not in actual:
            problems.append(f"[{part}] {b['item']} handle {b['handle']} 期望含 '{exp.split('(')[0]}'，模板实为 '{t.plain}'")
    return problems


def extract() -> dict:
    """构建期 B1 主入口：两张模板 → template_assets dict。"""
    gear_pt = parse_template(config.TEMPLATE_GEAR)
    shaft_pt = parse_template(config.TEMPLATE_SHAFT)

    gear_groups = group_gear(gear_pt)
    shaft_groups = group_shaft(shaft_pt)

    def snapshot(pt: ParsedTemplate) -> dict:
        return {
            t.handle: {"kind": t.kind, "layer": t.layer, "raw": t.raw, "plain": t.plain,
                       "x": round(t.x, 2), "y": round(t.y, 2)}
            for t in pt.texts
        }

    gear_b = _gear_bindings()
    shaft_b = _shaft_bindings()
    problems = _verify_bindings("gear", gear_pt, gear_b) + _verify_bindings("shaft", shaft_pt, shaft_b)

    u7_findings = [
        {"id": "N1", "item": "输出轴 26.5/19.5/31/3.5/2.0 归属", "conclusion":
            "依模板图形判定（2026-11-14 defpoint 锚点实测，C4/C5）：3.5=键槽2轴向定位（肩246.5→槽口端250，#115）；"
            "2.0=键槽1轴向定位（端面99→101，#130）；19.5/31=键槽深1/2（d−t1 图值，断面 #841/#85C，公差 0/-0.020）；"
            "26.5（第5段长）未单独标注，由总长 242 反算。D 六 的'倒角/键槽定位'标签互换系文档笔误。HB3 复核位保留"},
        {"id": "N2", "item": "参数表 K=6 / W=42.439", "conclusion":
            "与本算例 z2=134（k=z/9+0.5=15，W=89.37）不匹配，为参考图遗留值；按 A 通道修正 K→15、W→89.37（E4/E2）；"
            "±0.012(f_pt)、0.043(F_r)、0.022(F_α) 归属参数表检验项目，B 通道取模板值（C8~C13 差异记录）；GB/T10095-2008/-2001 年号并存：取模板 -2008"},
        {"id": "N3", "item": "标题栏字段", "conclusion": "图号/日期/班级/学号占位（郑佳暄/飞制2303 等），算例可经 case.yaml 注入（U9）；MVP 不注入"},
        {"id": "N4", "item": "异常文本 飞制2303|233423030303", "conclusion": "两模板标题栏各 1 处（#4CA/#A8C）；U8 建议清理，默认保留待会签（E5 能力预留，update_plan 默认不含）"},
        {"id": "N5", "item": "技术要求完整行文", "conclusion":
            "齿轮 #4CB：材料45钢正火170-210HBW/R5/C2（C7 高风险待书面确认）；轴 #A8D：调质220-250HBW/R2/C1.5"},
        {"id": "N6", "item": "实体统计口径", "conclusion":
            f"需求文档 2.3 为全文件口径（含块定义/匿名*D尺寸块）；ezdxf 模型空间口径：齿轮 "
            f"{gear_pt.ms_stats}，轴 {shaft_pt.ms_stats}；匿名 *D 块由 DIMENSION 引用，需随标注同步更新；INSERT=0 不代表这些块未被引用"},
    ]

    assets = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "templates": {
            "gear": {"path": str(config.TEMPLATE_GEAR), "dxfversion": gear_pt.dxfversion,
                     "codepage": gear_pt.codepage, "bbox": [round(v, 2) for v in gear_pt.bbox],
                     "ms_stats": gear_pt.ms_stats, "block_stats": gear_pt.block_stats},
            "shaft": {"path": str(config.TEMPLATE_SHAFT), "dxfversion": shaft_pt.dxfversion,
                      "codepage": shaft_pt.codepage, "bbox": [round(v, 2) for v in shaft_pt.bbox],
                      "ms_stats": shaft_pt.ms_stats, "block_stats": shaft_pt.block_stats},
        },
        "layers": {"gear": gear_pt.layers, "shaft": shaft_pt.layers},
        "style_templates": {
            "simsun": "工程字2/Standard（SimSun）",
            "dim_stack": "%%C{main}{{\\H0.71x;\\C3;\\S{sup}^ {sub};}}",
            "dim_pm": "{main}%%P{v}",
            "plain": "{text}",
        },
        "tables": {
            "gear_params": {"x_range": [345, 415], "y_range": [173, 292],
                            "cells": "绑定表 bindings（item↔handle）即格子映射"},
            "titleblock": {"x_range": [265, 415], "y_range": [5, 40]},
            "techreq": {"gear": "4CB", "shaft": "A8D"},
        },
        "views": {
            "gear": {"section": "主视全剖（x<150，中心(82,148.5)，比例1:1.5）",
                     "side": "孔端视图（中心(233.7,148.5)）", "scale": "1:1.5"},
            "shaft": {"main": "主视（轴线y=187，比例1:1）", "sections": ["F-F@129", "G-G@203"], "scale": "1:1"},
        },
        "bindings": {"gear": gear_b, "shaft": shaft_b},
        "geo_groups": {"gear": gear_groups.to_dict(), "shaft": shaft_groups.to_dict()},
        "value_snapshot": {"gear": snapshot(gear_pt), "shaft": snapshot(shaft_pt)},
        "u7_findings": u7_findings,
        "binding_verification_problems": problems,
    }
    return assets


def build(assets_dir=None) -> dict:
    assets = extract()
    validate_assets(assets)
    out_dir = assets_dir or config.ASSETS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "template_assets.json"
    out.write_text(json.dumps(assets, ensure_ascii=False, indent=1), encoding="utf-8")
    return assets


def validate_assets(assets):
    problems=assets.get('binding_verification_problems',[])
    findings=assets.get('u7_findings',[])
    if problems or len(findings)<6 or any(not f.get('conclusion') for f in findings):
        raise ValueError(f'BF-07/U7 未闭环：绑定问题={problems}，遗留结论数={len(findings)}')
