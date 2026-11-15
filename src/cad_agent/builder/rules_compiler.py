# -*- coding: utf-8 -*-
"""规则库构建（T3-1~T3-4 / BF-02~05）。

转录来源：
- formulas.json      ← 清单 4.1（calculator 公式库）
- constants.json     ← 清单 8.1（常量表）
- lookup_tables.json ← 清单 8.2（档位表起始）+ 需求文档 3.2（模板现值 B 通道）
- linked_map.json    ← 清单 8.3（七组联动键）
- assertions.json    ← 清单 2.3/3.3/8.3 + 需求 7.1（A1~A15 + 已知偏差豁免）
- verdict_rules.json ← 需求 3.3 三通道 + 3.4 C1~C14 冲突基准（U0/U1/U2/U6/U8/U15 会签位）

HB1/HB2 人工会签位：本 MVP 以 "status": "pending_sign" 落盘，待用户签署后生效；
默认规则按需求文档建议处置执行（U1 暂按清单 5.2 取 4.1 值等），保证流水线可运行。
"""
from __future__ import annotations

import json
from datetime import datetime

from .. import config

FORMULAS = {
    "_comment": "calculator 公式库（清单 4.1）",
    "d1": "m*z1",
    "d2": "m*z2",
    "da2": "d2+2*m",
    "df2": "d2-2.5*m",
    "a": "(d1+d2)/2",
    "hub_d": "1.6*d_bore",
    "hub_l": "max(1.2*d_bore, b2) 图纸定稿优先",
    "rim_inner": "da2-2*delta0",
    "d0_circle": "(rim_inner+hub_d)/2",
    "k": "round(z2/9+0.5) 取整",
    "W": "m*cos(alpha*pi/180)*(pi*(k-0.5)+z2*inv_alpha), inv_alpha=tan(alpha)-alpha*pi/180",
    "shaft_total_l": "sum(seg_l)",
    "d_min": "A0*(P/n)^(1/3)",
    "key_l": "键长（键 b×h×L）",
    "seg_l_chain": "轴承宽T+壁厚δ+间隙Δ+s 累加链（SRD 直接给定）",
}

CONSTANTS = {
    "_comment": "常量表（清单 8.1，与零件参数无关）",
    "alpha_deg": 20,
    "ha_star": 1.0,
    "c_star": 0.25,
    "precision_grade": 8,
    "tol_codes": {"bore": "H7", "tip_circle": "h11", "seg1": "r6", "seg3": "k6", "seg4": "r6",
                  "key_hub": "JS9", "key_shaft": "N9"},
    "ra_series": [0.4, 0.8, 1.6, 3.2, 6.3, 12.5],
    "chamfer": "C1.5~C2", "corner_r": "R2~R5",
    "linear_tol_grade": "GB/T 1804-m", "geo_tol_grade": "GB/T 1184-H",
    "structure": "腹板式", "material_shaft": "45 钢调质",
    "standards": ["GB/T 1095", "GB/T 1800.1", "GB/T 10095.1/.2", "GB/T 6443",
                  "GB/T 1804", "GB/T 1184", "GB/T 1031", "GB/T 276", "GB/T 1357", "GB/T 117"],
}

# 档位表：MVP 起始值 = 清单 8.2 本档行 + 跨档示例行（HB2 逐行签字位留痕）。
# 运行期 lookup 按「索引→命中行」取值；未覆盖项 → rag 兜底（MVP：清单兜底+待人工）。
LOOKUP_TABLES = {
    "_comment": "档位表（清单 8.2；表号=李育锡《机械设计课程设计》第二版）",
    "gear_precision": {
        "table": "表 19-2/19-3/19-4（GB/T 10095.1/.2-2008）",
        "index": ["d_range", "mn_range", "grade"],
        "signed": False,
        "rows": [
            {"d_range": "(125,280]", "mn_range": "(0,2.5]", "grade": 8, "F_p": 0.069, "f_pt": 0.017,
             "F_alpha": 0.020, "F_beta": 0.029, "F_r": 0.055, "src": "清单8.2 本档"},
            {"d_range": "(50,125]", "mn_range": "(0,2.5]", "grade": 8, "F_p": 0.052, "f_pt": 0.015,
             "F_alpha": 0.017, "F_beta": None, "F_r": 0.042, "src": "清单8.2 跨档示例"},
            {"d_range": "(125,280]", "mn_range": "(0,2.5]", "grade": 8, "F_beta_b_10_20": 0.022,
             "src": "清单8.2 F_β 跨档（b∈(10,20]）"},
        ],
    },
    "center_distance_tol": {
        "table": "表 19-5（±f_a）",
        "index": ["a_range", "grade"],
        "signed": False,
        "rows": [
            {"a_range": "(120,180]", "grade": "7~8", "fa_pm": 0.0315, "src": "清单8.2 本档"},
            {"a_range": "(180,250]", "grade": "7~8", "fa_pm": 0.036, "src": "清单8.2 跨档示例"},
        ],
    },
    "key_slot": {
        "table": "表 14-26（GB/T 1095-2003）",
        "index": ["d_range", "b"],
        "signed": False,
        "rows": [
            {"d_range": "[22,30]", "b": 8, "t1": 4.0, "t2": 3.3, "shaft_N9": "0/-0.036",
             "hub_JS9": "±0.018", "src": "清单8.2 本档"},
            {"d_range": "(30,38]", "b": 10, "t1": 5.0, "t2": 3.3, "shaft_N9": "0/-0.036",
             "hub_JS9": "±0.018", "src": "清单8.2 本档"},
            {"d_range": "(30,38]", "b": 12, "shaft_N9": "0/-0.043", "hub_JS9": "±0.0215",
             "src": "清单8.2 跨档示例（b=12~16）"},
        ],
    },
    "fit_tolerance": {
        "table": "表 18-1/18-3（GB/T 1800.1/.2-2009）",
        "index": ["size_range", "code"],
        "signed": False,
        "rows": [
            {"size_range": "(30,50]", "code": "H7", "sup": "+0.025", "sub": "0", "src": "清单8.2 本档"},
            {"size_range": "(50,80]", "code": "H7", "sup": "+0.030", "sub": "0", "src": "清单8.2 跨档示例"},
            {"size_range": "(18,30]", "code": "r6", "sup": "+0.041", "sub": "+0.028", "src": "GB/T 1800.1（18~30 同值）"},
            {"size_range": "(30,40]", "code": "r6", "sup": "+0.050", "sub": "+0.034", "src": "GB/T 1800.1"},
            {"size_range": "(24,30]", "code": "k6", "sup": "+0.015", "sub": "+0.002", "src": "GB/T 1800.1（清单 4.1 Ø30）"},
            {"size_range": "(30,40]", "code": "k6", "sup": "+0.018", "sub": "+0.002", "src": "GB/T 1800.1"},
            {"size_range": "(240,315]", "code": "h11", "sup": "0", "sub": "-0.32", "src": "GB/T 1800.1"},
        ],
    },
    "bearing_6206": {
        "table": "GB/T 276", "index": ["model"], "signed": False,
        "rows": [{"model": "6206", "d": 30, "D": 62, "B": 16, "src": "S 第九部分"}],
    },
}

LINKED_MAP = {
    "_comment": "联动同步表（清单 8.3：改一处必须同步；运行期由 calculator 重算保证一致性，本表作断言依据）",
    "groups": [
        {"key": "d_bore(=35)", "items": ["gear.bore_d", "shaft.seg4_d", "gear.hub_d", "gear.key_depth", "shaft.seg4_key"], "n": 5},
        {"key": "key10x8x45", "items": ["shaft.key2_l", "gear.key_len", "gear.key_w", "shaft.key2_depth", "gear.key_depth"], "n": 5},
        {"key": "m(=2)", "items": ["gear.da2", "gear.df2", "gear.W", "gear.da2_tol_rule", "gear.m"], "n": 5},
        {"key": "b2(=54)", "items": ["gear.b2", "gear.hub_l", "shaft.seg4_l"], "n": 4},
        {"key": "a(=161)", "items": ["gear.a", "gear.a_tol_text", "box_delta", "box_df"], "n": 4},
        {"key": "z2(=134)", "items": ["gear.k", "gear.W", "gear.da2", "gear.df2"], "n": 4},
        {"key": "6206", "items": ["shaft.seg3_d", "shaft.seg6_d", "shaft.seg5_d", "bearing_6206"], "n": 4},
        {"key": "hole_n(=6)", "items": ["gear.hole_n", "gear.hole_nxd_text(139)"], "n": 2, "note": "R5 均布联动扩展（V1.2）"},
    ],
}

# A1~A15 断言（需求 7.1 表，公式化跨算例）+ 已知偏差豁免（Q8 自动留痕）
ASSERTIONS = {
    "_comment": "尺寸链断言 A1~A15 + 豁免表（清单 8.4：图纸取值类偏差自动留痕放行）",
    "assertions": [
        {"id": "A1", "expr": "da2 == d2 + 2*m", "expect_case001": 272},
        {"id": "A2", "expr": "df2 == d2 - 2.5*m", "expect_case001": 263},
        {"id": "A3", "expr": "rim_inner == da2 - 2*delta0", "expect_case001": 252},
        {"id": "A4", "expr": "d0_circle == (rim_inner + hub_d)/2", "expect_case001": 154},
        {"id": "A5", "expr": "d0_hole ≈ 0.25*(rim_inner - hub_d)", "expect_case001": 49, "tol": 10.01},
        {"id": "A6", "expr": "key_depth ≈ d_bore + t2", "expect_case001": 38.3, "tol": 0.71},
        {"id": "A7", "expr": "total_l == sum(seg_l)", "expect_case001": 242},
        {"id": "A8", "expr": "key1_depth ≈ d1 - t1", "expect_case001": 19.0, "tol": 0.51},
        {"id": "A9", "expr": "key2_depth ≈ d4 - t1", "expect_case001": 30.0, "tol": 1.01},
        {"id": "A10", "expr": "key_len == 键长", "expect_case001": [50, 45]},
        {"id": "A11", "expr": "seg3_d == seg6_d == bearing内径", "expect_case001": 30},
        {"id": "A12", "expr": "seg5_d == seg3_d + 2*h定位", "expect_case001": 36, "tol": 0.01},
        {"id": "A13", "expr": "b2 == hub_l（本例）", "expect_case001": 54},
        {"id": "A14", "expr": "k == round(z2/9 + 0.5)", "expect_case001": 15},
        {"id": "A15", "expr": "|W - 公式值| <= 0.01", "expect_case001": 89.37, "tol": 0.01},
    ],
    "exemptions": [
        {"assertion": "A5", "reason": "减重孔直径为图纸取值 59（公式 49），清单 5.1 已裁决取 59", "status": "auto_exempt"},
        {"assertion": "A6", "reason": "键槽深 39 为图纸取值（38.3+0.7），清单 8.4 图纸取值", "status": "auto_exempt"},
        {"assertion": "A8", "reason": "键槽深 19.5 为图纸取值（19.0+0.5）", "status": "auto_exempt"},
        {"assertion": "A9", "reason": "键槽深 31 为图纸取值（30.0+1.0）", "status": "auto_exempt"},
    ],
}

VERDICT_RULES = {
    "_comment": "三通道裁决规则（需求 3.3，U0 会签位）+ 冲突基准 C1~C14（需求 3.4）",
    "channels": {
        "A": {"scope": "算例硬数据（SRD 计算/选定值）", "rule": "SRD（D 六 > S/R）为准，模板不符则修正；数值变化经联动表同步"},
        "B": {"scope": "查表标准值（公差带/检验偏差/粗糙度档）", "rule": "模板现值为准；lookup 换档时按档位表重查，新值与模板档位模式一致方可落图"},
        "C": {"scope": "工艺/材料（热处理/圆角/倒角）", "rule": "模板为准；工艺方式变更须书面确认（U2）"},
    },
    "conflicts": [
        {"id": "C1", "item": "gear.d0_hole", "v1": "49（D四 公式）", "v2": "59（D六/模板）", "verdict": "取 59", "status": "decided"},
        {"id": "C2", "item": "gear.web_t", "v1": "16.2（公式）", "v2": "10（D六/模板）", "verdict": "取 10（低于下限 10.8 留痕）", "status": "decided"},
        {"id": "C3", "item": "gear.key_w_tol", "v1": "±0.0215（D六 标为腹板厚公差）", "v2": "±0.018（10JS9）", "verdict": "挂键槽宽 10，值取模板 ±0.0215", "status": "decided"},
        {"id": "C4", "item": "shaft.key2_pos/key1_pos", "v1": "倒角（D六）", "v2": "键槽定位（清单 5.2）",
         "verdict": "依模板图形判定为键槽轴向定位：3.5=肩246.5→键槽2槽口端250（DIM#115 锚点实测）；2.0=端面99→键槽1槽口端101（#130）",
         "status": "decided_by_geometry（U4，HB3 复核位）"},
        {"id": "C5", "item": "shaft.key1_depth/key2_depth", "v1": "键槽定位（D六）", "v2": "键槽深（清单 3.1）",
         "verdict": "依模板图形判定为键槽深：19.5/31 为断面 F-F/G-G 的 d−t1 图值（#841/#85C 锚点实测，公差 0/-0.020）",
         "status": "decided_by_geometry（U4，HB3 复核位）"},
        {"id": "C6", "item": "shaft.seg1/3/6_d_tol", "v1": "清单 5.2：改 4.1 值", "v2": "Q5：模板为准", "verdict": "U1：暂按清单 5.2 取 4.1 值修正；后续算例按 lookup 档位自动取值", "status": "pending_sign"},
        {"id": "C7", "item": "gear.material", "v1": "调质 197~286HBS（S）", "v2": "正火 170-210HBW（模板）", "verdict": "C 通道模板为准 + 书面确认（U2）", "status": "pending_sign"},
        {"id": "C8", "item": "gear.bore_tol", "v1": "+0.025/0（H7 清单）", "v2": "+0.030/0（模板）", "verdict": "B 通道取模板值，差异记录", "status": "decided"},
        {"id": "C9", "item": "gear.da2_tol", "v1": "0/-0.32（h11）", "v2": "0/-0.300（模板）", "verdict": "B 通道取模板值", "status": "decided"},
        {"id": "C10", "item": "gear.f_pt", "v1": "±0.017（表19-2）", "v2": "±0.012（模板）", "verdict": "B 通道取模板值", "status": "decided"},
        {"id": "C11", "item": "gear.F_r", "v1": "0.055（表19-4）", "v2": "0.043（模板）", "verdict": "B 通道取模板值", "status": "decided"},
        {"id": "C12", "item": "shaft.key1_w_tol", "v1": "8N9=0/-0.036", "v2": "0/-0.043（模板）", "verdict": "B 通道取模板值，差异记录", "status": "decided"},
        {"id": "C13", "item": "gear.key_w_tol", "v1": "10JS9=±0.018", "v2": "±0.0215（模板）", "verdict": "B 通道取模板值", "status": "decided"},
        {"id": "C14", "item": "定位销 M8", "v1": "D二", "v2": "8×30 圆锥销（清单 5.2）", "verdict": "装配图内容，V1 不适用", "status": "na"},
    ],
    "u_signoffs": {
        "U0": {"desc": "三通道裁决规则认可", "status": "pending_sign"},
        "U1": {"desc": "轴颈偏差取清单 4.1 值（φ23 r6 +0.041/+0.028、φ30 k6 +0.015/+0.002、φ35 r6 +0.050/+0.034）", "status": "pending_sign", "default": "apply"},
        "U2": {"desc": "大齿轮热处理 正火 vs 调质", "status": "pending_sign", "default": "keep_template"},
        "U6": {"desc": "向量库与清单 8.2 双源不一致：向量库优先+差异留痕（MVP 向量库未启用，清单 8.2 兜底）", "status": "pending_sign"},
        "U8": {"desc": "异常文本清理（飞制2303…）", "status": "pending_sign", "default": "keep"},
        "U15": {"desc": "算例输入目录迁移=复制（docs 保留原始档案）", "status": "decided"},
    },
}


def compile_all(assets_dir=None) -> dict[str, dict]:
    out_dir = (assets_dir or config.ASSETS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "formulas.json": {"generated_at": datetime.now().isoformat(timespec="seconds"), **FORMULAS},
        "constants.json": {"generated_at": datetime.now().isoformat(timespec="seconds"), **CONSTANTS},
        "lookup_tables.json": {"generated_at": datetime.now().isoformat(timespec="seconds"), **LOOKUP_TABLES},
        "linked_map.json": {"generated_at": datetime.now().isoformat(timespec="seconds"), **LINKED_MAP},
        "assertions.json": {"generated_at": datetime.now().isoformat(timespec="seconds"), **ASSERTIONS},
        "verdict_rules.json": {"generated_at": datetime.now().isoformat(timespec="seconds"), **VERDICT_RULES},
    }
    for name, data in files.items():
        path=out_dir/name
        if path.exists():
            # 重建不得抹掉已录入档位、用户裁决和签署记录。
            previous=json.loads(path.read_text(encoding='utf-8'))
            if name in ('lookup_tables.json','verdict_rules.json','constants.json'):
                data={**data,**previous}
        if name=='assertions.json':
            for entry in data['exemptions']:
                entry['expected'],entry['actual']={'A5':(49,59),'A6':(38.3,39),'A8':(19,19.5),'A9':(30,31)}[entry['assertion']]
        files[name]=data
        (out_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return files
