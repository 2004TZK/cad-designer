# -*- coding: utf-8 -*-
"""构建期会签机制（HB1/HB2/HB3，T3-2/T3-4/T3-5 的人工介入落盘）。

`cad-agent signoff --file signoff.json --by 签署人`：
- HB1：verdict_rules.u_signoffs（U0/U1/U2/U6/U8/U15）→ status=signed + decision
- HB1 冲突项：conflicts C4/C5/C7 等 pending_sign → signed
- HB2：lookup_tables 各表 rows 标记 row_signed=true（逐行确认）
- HB3：属性判定复核（C4/C5 锚点证据）→ attribute_verdict 落 signed

签署只改 status，不改默认取值行为（取值规则与签署解耦，改动经 conflicts.verdict）。
记录落 assets/signoff_record.md（谁/何时/签了什么）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .. import config


_ASSETS_OVERRIDE = None


def _dir():
    return _ASSETS_OVERRIDE or config.ASSETS_DIR


def _load(name: str) -> dict:
    return json.loads((_dir() / (name + ".json")).read_text(encoding="utf-8"))


def _save(name: str, data: dict):
    (_dir() / (name + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                           encoding="utf-8")


def show_pending() -> dict:
    rules = _load("verdict_rules")
    lookup = _load("lookup_tables")
    return {
        "u_signoffs": {k: v["status"] for k, v in rules.get("u_signoffs", {}).items()},
        "conflicts_pending": [c["id"] for c in rules.get("conflicts", [])
                              if "pending" in c.get("status", "")],
        "lookup_tables_signed": {n: all(r.get("row_signed") for r in t.get("rows", []))
                                 for n, t in lookup.items() if isinstance(t, dict) and "rows" in t},
    }


def apply_signoff(data: dict, by: str = "", assets_dir=None) -> dict:
    """data 形如：
    {"HB1": {"U0": "accept", "U1": "accept(按清单4.1值)", "U2": "keep_template",
             "U6": "accept", "U8": "keep", "U15": "accept"},
     "HB1_conflicts": {"C4": "accept", "C5": "accept"},
     "HB2": {"key_slot": true, "fit_tolerance": true, ...},   # 表级确认（行随表签）
     "HB3": {"C4": "accept", "C5": "accept"}}
    """
    now = datetime.now().strftime("%F %T")
    applied, unknown = [], []
    root=Path(assets_dir) if assets_dir else config.ASSETS_DIR
    def _load(name):
        return json.loads((root/(name+'.json')).read_text(encoding='utf-8'))
    def _save(name,data):
        (root/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=1),encoding='utf-8')
    rules = _load("verdict_rules")

    for uid, decision in (data.get("HB1") or {}).items():
        u = rules["u_signoffs"].get(uid)
        if not u:
            unknown.append(f"HB1.{uid}")
            continue
        u["status"], u["decision"], u["signed_by"], u["signed_at"] = "signed", decision, by, now
        applied.append({"hb": "HB1", "id": uid, "status": "signed", "decision": decision})
    for cid, decision in (data.get("HB1_conflicts") or {}).items():
        hit = next((c for c in rules["conflicts"] if c["id"] == cid), None)
        if not hit:
            unknown.append(f"HB1_conflicts.{cid}")
            continue
        hit["status"] = f"signed({decision})@{now} by {by}"
        applied.append({"hb": "HB1", "id": cid, "status": "signed", "decision": decision})
    _save("verdict_rules", rules)

    lookup = _load("lookup_tables")
    for tname, ok in (data.get("HB2") or {}).items():
        t = lookup.get(tname)
        if not t or not isinstance(t, dict) or "rows" not in t:
            unknown.append(f"HB2.{tname}")
            continue
        if ok:
            for row in t["rows"]:
                row["row_signed"] = True
                row["signed_by"] = by
            t["signed"] = True
            applied.append({"hb": "HB2", "id": tname, "status": "signed",
                            "decision": f"{len(t['rows'])} 行逐行确认"})
    _save("lookup_tables", lookup)

    layout = None
    if (root / "layout_rules.json").exists():
        layout = _load("layout_rules")
        for cid, decision in (data.get("HB3") or {}).items():
            if "attribute_verdicts" in layout and cid in layout["attribute_verdicts"]:
                layout["attribute_verdicts"][cid]["hb3_signed"] = f"{by}@{now}:{decision}"
                applied.append({"hb": "HB3", "id": cid, "status": "signed", "decision": decision})
            else:
                unknown.append(f"HB3.{cid}")
        if layout:
            _save("layout_rules", layout)

    record = {"signed_at": now, "by": by or "(未署名)", "applied": applied, "unknown": unknown}
    rec_path = root / "signoff_record.md"
    lines = [rec_path.read_text(encoding="utf-8") if rec_path.exists() else
             "# 构建期会签记录（HB1/HB2/HB3）\n", "",
             f"## {now} 签署人：{record['by']}", ""]
    lines += [f"- HB{r['hb'][2:] if r['hb'].startswith('HB') else r['hb']} {r['id']} → {r['status']}"
              f"（{r.get('decision', '')}）" for r in applied]
    if unknown:
        lines += [f"- ⚠ 未识别：{unknown}"]
    rec_path.write_text("\n".join(lines), encoding="utf-8")
    return record
