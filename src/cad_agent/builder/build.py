# -*- coding: utf-8 -*-
"""构建期编排（cad-agent build）：B0~B3 MVP 落地。

1. 算例输入迁移（U15：复制 docs→input/case001绞车，docs 保留原始档案）
2. B1 资产提取（BF-01：template_assets.json，含 U7 闭环结论）
3. B2 规则库（BF-02~05：六份规则 json，HB1 会签位 pending_sign）
4. 构建报告（含几何归组覆盖率=R4 门禁证据）
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime

from .. import config
from . import asset_extractor, rules_compiler


def migrate_inputs() -> dict:
    """U15：金样例 SRD 复制入 input/case001绞车/（docs 保留原始档案）。"""
    case_dir = config.INPUT_DIR / config.GOLD_CASE
    case_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in (config.S_FILE, config.R_FILE, config.D_FILE):
        src, dst = config.DOCS_DIR / name, case_dir / name
        if not dst.exists():
            shutil.copyfile(src, dst)
            copied.append(name)
    return {"case_dir": str(case_dir), "copied": copied}


def build() -> dict:
    report: dict = {"generated_at": datetime.now().isoformat(timespec="seconds")}
    report["input_migration"] = migrate_inputs()
    tassets = asset_extractor.build()
    report["template_assets"] = {
        "bindings": {p: len(tassets["bindings"][p]) for p in ("gear", "shaft")},
        "binding_verification_problems": tassets["binding_verification_problems"],
        "u7_findings": tassets["u7_findings"],
        "ms_stats": {p: tassets["templates"][p]["ms_stats"] for p in ("gear", "shaft")},
    }
    for part in ("gear", "shaft"):
        gg = tassets["geo_groups"][part]
        n_total = sum(tassets["templates"][part]["ms_stats"].values())
        handles=set(gg['structure_zone'])
        for group in gg['groups'].values():
            handles.update(group['entities'])
        for zone in gg['inherited_zones']:
            handles.update(zone['entities'])
        n_grouped=len(handles)
        if n_grouped != n_total:
            raise ValueError(f'{part} 几何归组未覆盖全部实体：{n_grouped}/{n_total}')
        report[f"geo_coverage_{part}"] = {
            "entities_ms": n_total, "grouped": n_grouped, "coverage": f"{n_grouped / n_total:.1%}",
            "groups": {gid: len(g["entities"]) for gid, g in gg["groups"].items()},
            "inherited_zones": {z["id"]: len(z["entities"]) for z in gg["inherited_zones"]},
        }
    rules_compiler.compile_all()
    report["rules"] = ["formulas.json", "constants.json", "lookup_tables.json",
                       "linked_map.json", "assertions.json", "verdict_rules.json",
                       "layout_rules.json"]

    # ── layout_rules.json（BF-06 独立交付；HB3 签署位） ──
    layout = {
        "generated_at": report["generated_at"],
        "g5_follow_threshold_units": 20,
        "g5_rule": "小幅(≤阈值)自动跟随；超阈 EditorError → H4 人工确认（U14 spike 标定）",
        "u9_injectable_handles": {
            "gear": {"designer": "84D", "class_student": "4CA", "course": "4C9"},
            "shaft": {"designer": "C03", "class_student": "A8C", "course": "A8B"},
        },
        "attribute_verdicts": {
            "C4": {"item": "3.5/2.0 归属", "verdict": "键槽轴向定位（非倒角）",
                   "evidence": "#115 p1=(250.0,187.0)→p2=(246.5,187.0)=3.5 肩→键槽2槽口端；"
                               "#130 p1=(101.0,187.0)→p2=(99.0,187.0)=2.0 端面→键槽1槽口端",
                   "status": "decided_by_geometry", "hb3_signed": ""},
            "C5": {"item": "19.5/31 归属", "verdict": "键槽深1/2（d−t1 图值）",
                   "evidence": "#841 p1=(128.5,96.5)→p2=(109.0,96.5)=19.5 断面F-F；"
                               "#85C p1=(203.0,96.5)→p2=(172.0,96.5)=31 断面G-G；公差 0/-0.020",
                   "status": "decided_by_geometry", "hb3_signed": ""},
        },
        "bindings_digest": {
            part: [{"handle": b["handle"], "item": b["item"], "render": b["render"], "op": b["op"]}
                   for b in tassets["bindings"][part]]
            for part in ("gear", "shaft")
        },
    }
    layout_path=config.ASSETS_DIR/'layout_rules.json'
    if layout_path.exists():
        previous=json.loads(layout_path.read_text(encoding='utf-8'))
        layout['g5_follow_threshold_units']=previous.get('g5_follow_threshold_units',20)
        for cid,verdict in layout['attribute_verdicts'].items():
            verdict['hb3_signed']=previous.get('attribute_verdicts',{}).get(cid,{}).get('hb3_signed','')
    layout_path.write_text(
        json.dumps(layout, ensure_ascii=False, indent=1), encoding="utf-8")

    out = config.ASSETS_DIR / "build_report.json"
    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # 构建报告 markdown（U7 硬门禁证据，BF-07）
    md = ["# 模板解析与构建报告 v2（BF-07 U7 闭环）", "",
          f"生成时间：{report['generated_at']}", "",
          "## 实体统计（模型空间口径 + 块定义口径见 template_assets.json）", ""]
    for part in ("gear", "shaft"):
        md.append(f"- **{part}**: {report['template_assets']['ms_stats'][part]}")
        cov = report[f"geo_coverage_{part}"]
        md.append(f"- 几何归组覆盖率（R4 门禁）：{cov['grouped']}/{cov['entities_ms']} = **{cov['coverage']}**"
                  f"（组 {cov['groups']}，继承区 {cov['inherited_zones']}）")
    md += ["", "## U7 遗留项闭环结论", ""]
    for f in tassets["u7_findings"]:
        md.append(f"- **{f['id']} {f['item']}**：{f['conclusion']}")
    md += ["", "## 绑定对账问题", ""]
    md += [f"- {p}" for p in tassets["binding_verification_problems"]] or ["- 无（全部绑定与模板现值对账通过）"]
    (config.ASSETS_DIR / "build_report.md").write_text("\n".join(md), encoding="utf-8")
    return report
