# -*- coding: utf-8 -*-
"""P5 校验（FR-07：断言 A1~A15 + 完备性矩阵）与 update_plan/final 冻结。

全绿放行：已知 4 偏差按豁免表自动留痕（Q8），新偏差 → BLOCKED（H2 中断）。
"""
from __future__ import annotations

import json

from ..parsers.template_parser import _dim_plain
from .dispatcher import FinalItem


from .checks import run_assertions


def completeness(data: dict, bindings: dict) -> tuple[list[dict], bool]:
    """完备性矩阵：每个绑定（落图）项有值/有源/有裁决。"""
    rows, ok = [], True
    for part in ("gear", "shaft"):
        table = data[part]
        for b in bindings[part]:
            for fid in b["item"].split("+"):
                if fid.startswith("gear.") or fid.startswith("shaft."):
                    it = table.get(fid)
                    if it is None:
                        rows.append({"part": part, "id": fid, "binding": b["handle"],
                                     "status": "missing", "note": "无对应数据项"})
                        ok = False
                        continue
                    has_v = it["value"] is not None or it["text"] not in (None, "", "None")
                    has_s = bool(it["source"])
                    has_j = bool(it["verdict"]) or it["channel"] in ("B", "C")
                    if not (has_v and has_s and has_j):
                        ok = False
                    rows.append({"part": part, "id": fid, "binding": b["handle"],
                                 "status": "ok" if (has_v and has_s and has_j) else "incomplete",
                                 "value": it["text"], "channel": it["channel"], "verdict": it["verdict"]})
    return rows, ok


# ── update_plan / final 冻结（P5 门禁放行后） ──────────────────────────

def render_binding_text(binding: dict, table: dict) -> str | None:
    """按绑定渲染目标文本（合并同 handle 的全部数据项；格式与 _dim_plain 归一化一致）。"""
    ids = binding["item"].split("+")
    val = lambda fid: table[fid]["value"] if fid in table else None
    txt = lambda fid: table[fid]["text"] if fid in table else None
    num = lambda v: f"{v:g}" if isinstance(v, (int, float)) and v is not None else (str(v) if v is not None else None)

    def main_of() -> str | None:
        for f in ids:
            if f.endswith("_tol") or f in ("gear.hole_n",):
                continue
            v = num(val(f))
            if v is not None:
                return v
            if txt(f):
                return txt(f)
        return None

    def tol_of() -> tuple[str, str] | None:
        for f in ids:
            if f.endswith("_tol"):
                v = val(f)
                if isinstance(v, str) and "/" in v:
                    sup, sub = v.split("/", 1)
                    return sup.strip(), sub.strip()
        return None

    r = binding["render"]
    if r == "mtext":
        f = ids[0]
        return txt(f) if txt(f) else (num(val(f)) if f in table else None)
    if r == "dim_nxd":
        n, d = val(ids[0]), val(ids[1])
        return f"{n:g}X%%C{d:g}" if n is not None and d is not None else None
    main = main_of()
    if main is None:
        return None
    tol = tol_of()
    if r == "dim_dia":
        return f"%%C{main}"
    if r == "dim_dia_tol":
        return f"%%C{main}{{\\H0.71x;\\C3;\\S{tol[0]}^ {tol[1]};}}" if tol else f"%%C{main}"
    if r == "dim_num":
        return main
    if r == "dim_num_tol":
        return f"{main}{{\\H0.71x;\\C3;\\S{tol[0]}^ {tol[1]};}}" if tol else main
    if r == "dim_pm":
        pm = None
        for f in ids:
            if f.endswith("_tol") and table.get(f):
                pm = str(table[f]["value"] or "").replace("±", "")
        return f"{main}%%P{pm}" if pm else main
    return None


def freeze(data: dict, assets: dict, run_out: "Path", case_id: str) -> dict:
    """生成 final_*.json + update_plan.json（P6 出图执行与 P8 验收共用契约）。"""
    from pathlib import Path
    run_out = Path(run_out)
    ex = run_out / "extracted"
    ex.mkdir(parents=True, exist_ok=True)
    plan = {"case_id": case_id, "geo_ops": [], "text_ops": [], "summary": {}}

    for part in ("gear", "shaft"):
        table = data[part]
        (ex / f"final_{part}.json").write_text(
            json.dumps({fid: dict(it) for fid, it in table.items()}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        # 按 handle 合并绑定后渲染（一处 DIMENSION 可能承载主值+公差多项）
        by_handle: dict[str, dict] = {}
        for b in assets["bindings"][part]:
            merged = by_handle.setdefault(b["handle"], dict(b))
            if merged["item"] != b["item"]:
                merged["item"] = merged["item"] + "+" + b["item"]
        for handle, b in by_handle.items():
            new = render_binding_text(b, table)
            if new is None:
                continue
            snap = assets["value_snapshot"][part].get(handle)
            old_plain = snap["plain"] if snap else None
            old_raw = snap["raw"] if snap else None
            # 渲染串为 raw 格式码语言 → 转换为 plain 口径再对比（与模板快照同口径）
            new_disp = _dim_plain(new) if b["kind"] == "dimension" else new
            if old_plain is None or _norm(new_disp) == _norm(old_plain):
                continue
            if b["op"] == "E5" and not any(table.get(fid,{}).get('verdict')=='u9_inject(u8_resolved)' for fid in b['item'].split('+')):
                continue  # U8 异常清理待会签，默认不动
            plan["text_ops"].append({
                "handle": handle, "part": part, "kind": b["kind"], "op": b["op"],
                "old_raw": old_raw, "new_text": new,
                "old_plain": old_plain, "new_plain": new_disp,
                "items": b["item"].split("+"),
                "reason": "A 通道模板修正/lookup 裁决落图",
            })
        # 几何操作：按草图模型对比（金样例零变更 → 空）
        plan["geo_ops"] += _geo_ops_for(part, table, assets["geo_groups"][part])

    # 计划预览从模板生成，记录逐实体预期几何及结构；P8 不再仅数实体。
    import copy
    import ezdxf
    from ..mcp.editor import Editor
    from ..qa.snapshot import drawing_snapshot, snapshot_diff
    from .. import config
    preview = Editor(run_out / "work" / "plan_preview", log_cb=lambda _: None)
    plan['expected_geometry'] = {}
    for part in ('gear','shaft'):
        ops = copy.deepcopy([o for o in plan['geo_ops'] if o['part']==part])
        for op in ops:
            op['large_move_confirmed'] = True  # 仅用于预览；实际执行仍检查 H4。
        preview.apply_geo(part,ops)
        res=preview.apply_text(part,[o for o in plan['text_ops'] if o['part']==part])
        expected=drawing_snapshot(ezdxf.readfile(res['final']),text=False)
        baseline=drawing_snapshot(ezdxf.readfile(str(config.TEMPLATE_GEAR if part=='gear' else config.TEMPLATE_SHAFT)),text=False)
        plan['expected_geometry'][part]=expected
        plan.setdefault('expected_diff',{})[part]=snapshot_diff(baseline,expected)

    plan["summary"] = {"text_ops": len(plan["text_ops"]), "geo_ops": len(plan["geo_ops"])}
    (ex / "update_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return plan


def _norm(s: str) -> str:
    return s.replace(" ", "").replace("φ", "").replace("%%C", "").strip()


def _geo_ops_for(part: str, table: dict, groups: dict) -> list[dict]:
    """几何更新计划：对比 final 参数与模板草图模型，产出 G1~G3 操作。

    MVP 支持：
    - shaft: seg{i}_l 变化 → 后续段边界平移（G1）+ 尺寸跟随（G5）
    - gear: d0_hole 变化 → 减重孔空档上下边平移（G1）
    （hole_n 数量变化仅联动文本 6X→4X；剖视图几何不变，见 spike 报告）
    """
    sketch = groups.get("sketch", {})
    ops: list[dict] = []
    if part == "shaft":
        old = sketch.get("segments", [])
        new_lens = [table.get(f"shaft.seg{i}_l", {}).get("value") for i in range(1, 7)]
        if len(old) == 6 and all(v is not None for v in new_lens):
            old_bounds = [seg["x0"] for seg in old] + [old[-1]["x1"]]
            new_bounds = [old_bounds[0]]
            for i in range(6):
                new_bounds.append(new_bounds[i] + float(new_lens[i]))
            if any(abs(a - b) > 1e-6 for a, b in zip(old_bounds, new_bounds)):
                ops.append({
                    "part": "shaft", "group": "GG-4", "op": "G1", "desc": "轴段长变化 → 边界重算",
                    "old_bounds": old_bounds, "new_bounds": new_bounds,
                    "sub_steps": sketch.get("sub_steps", {}),
                    "entities": _shaft_followers(groups),
                    "followers": ">=变动边界的轮廓/键槽/中心线/尺寸实体平移（G2/G5）",
                })
    elif part == "gear":
        sk = sketch
        new_hole = table.get("gear.d0_hole", {}).get("value")
        if new_hole is not None and sk:
            scale = groups.get("scale", 1.5)
            cy = sk.get("cy", groups.get("center", {}).get("y", 148.5))
            r_new = float(new_hole) / 2 / scale
            r_old = sk["r_hole"]
            if abs(r_new - r_old) > 0.05:
                hc = sk["hole_center_r"]
                moves = []
                for gid, g in groups.get("groups", {}).items():
                    if gid != "GG-2":
                        continue
                    for hdl, role in g["entities"].items():
                        if role != "hole_edge":
                            continue
                        ent = next((e for e in groups.get("_entities", []) if e["handle"] == hdl), None)
                        if not ent:
                            continue
                        y = ent["data"]["start"][1]
                        rel = y - cy  # +hc±r 或 -hc±r
                        mag = abs(rel) - hc  # ±r_old
                        sgn = 1 if mag > 0 else -1  # 外缘/内缘
                        moves.append({"handle": hdl, "dy": round((1 if rel>0 else -1)*sgn * (r_new - r_old), 6)})
                if moves:
                    # G5：6Xφ59 标注 defpoint 挂在上孔内缘（y=180.2），随内缘 dy 平移
                    ops.append({"part": "gear", "group": "GG-2", "op": "G1",
                                "desc": f"减重孔直径 59→{new_hole:g}", "entity_moves": moves,
                                "dim_follow": [{"handle": "139", "dy": round(r_old - r_new, 3)}]})
    return ops


def _shaft_followers(groups):
    """仅主视区跟随：剖面、图框、标题栏均排除。"""
    import ezdxf
    from .. import config
    doc=ezdxf.readfile(str(config.TEMPLATE_SHAFT))
    structure=set(groups.get('structure_zone',[]))
    handles=[]
    for e in doc.modelspace():
        kind=e.dxftype()
        if kind=='DIMENSION':
            anchors=[e.dxf.get(k) for k in ('defpoint2','defpoint3')]
            if all(p is not None and p.y>130 and 90<p.x<370 for p in anchors):
                handles.append(e.dxf.handle)
            continue
        if kind in ('MTEXT','TEXT','TOLERANCE'):
            p=e.dxf.insert
            if 90<p.x<370 and 130<p.y<260:
                handles.append(e.dxf.handle)
            continue
        if e.dxf.handle in structure:
            continue
        from ezdxf import bbox
        box=bbox.extents([e])
        if box.has_data and box.extmin.y>130 and box.extmax.y<260 and box.extmin.x>85 and box.extmax.x<380:
            handles.append(e.dxf.handle)
    return handles
