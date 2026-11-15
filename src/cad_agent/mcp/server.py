# -*- coding: utf-8 -*-
"""进程内引擎的 MCP stdio Server（T1-2 余项）。

工具词汇对齐改造方案 §3.2（drawing_open / entity_edit_text / entity_edit_geometry /
cad_batch / checkpoint_create / entity_list / entity_get / drawing_info / saveas /
drawing_critique / drawing_finalize / drawing_verify_requirements + convert_dwg）。
环境变量 AUTOCAD_MCP_BACKEND：ezdxf（会话 A）/ com（会话 B）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cad_agent import config  # noqa: E402
from cad_agent.mcp import rpc  # noqa: E402

BACKEND = os.environ.get("AUTOCAD_MCP_BACKEND", "ezdxf")
_SESSION = {"docs": {},'applied':{}}  # part → 文档路径（会话状态）


def _edit():
    from cad_agent.mcp.editor import Editor
    return Editor(Path(config.ROOT) / "output" / "mcp_sessions" / BACKEND,
                  log_cb=lambda m: None)


def _t(name, desc, props: dict, required=None):
    return {"name": name, "description": f"[{BACKEND}] {desc}",
            "inputSchema": {"type": "object", "properties": props,
                            "required": required or []}}


def _spec() -> list[dict]:
    return [
        _t("drawing_open", "复制总模板为工作底板并登记会话",
           {"part": {"type": "string", "enum": ["gear", "shaft"]},
            "workdir": {"type": "string"}}, ["part"]),
        _t("entity_edit_text", "文本替换（E1~E5/G4）：raw token 对齐替换+回读校验",
           {"part": {"type": "string"}, "handle": {"type": "string"},
            "old_plain": {"type": "string"}, "new_plain": {"type": "string"}},
           ["part", "handle", "old_plain", "new_plain"]),
        _t("entity_edit_geometry", "几何更新（G1/G2/G5）：轴段边界平移/减重孔空档边",
           {"part": {"type": "string"}, "plan_geo": {"type": "array"}}, ["part", "plan_geo"]),
        _t("cad_batch", "批量原子操作：文本批次（全部成功才提交）",
           {"part": {"type": "string"}, "steps": {"type": "array"}}, ["part", "steps"]),
        _t("checkpoint_create", "检查点：工作副本快照",
           {"part": {"type": "string"}, "label": {"type": "string"}}, ["part", "label"]),
        _t("entity_list", "实体清单/计数", {"part": {"type": "string"}}, ["part"]),
        _t("entity_get", "读取实体文本值", {"part": {"type": "string"}, "handle": {"type": "string"}},
           ["part", "handle"]),
        _t("drawing_info", "DXF 元信息（版本/编码/实体统计）", {"part": {"type": "string"}}, ["part"]),
        _t("saveas", "保存 final DXF", {"part": {"type": "string"}}, ["part"]),
        _t("drawing_critique", "质量检查（critique）", {"part": {"type": "string"},'plan':{'type':'object'}}, ["part"]),
        _t("drawing_finalize", "finalize 打分（≥90 门禁）", {"part": {"type": "string"},'plan':{'type':'object'}}, ["part"]),
        _t("drawing_verify_requirements", "关键值实测读回", {"part": {"type": "string"},'data':{'type':'object'}}, ["part",'data']),
        _t("convert_dwg", "DXF→DWG（会话 B：COM 主/ODA 回退/DXF 保底）",
           {"dxf": {"type": "string"}, "dwg": {"type": "string"}}, ["dxf", "dwg"]),
    ]


def _doc_path(part: str) -> Path:
    p = _SESSION["docs"].get(part)
    if not p:
        raise ValueError(f"会话未打开 {part}（先 drawing_open）")
    return Path(p)


def _read_texts(part: str) -> dict:
    from cad_agent.parsers.template_parser import parse_template
    from cad_agent.qa.quality import _snapshot_texts
    pt = parse_template(_doc_path(part))
    return {t.handle: {"kind": t.kind, "plain": t.plain, "layer": t.layer} for t in pt.texts}


def dispatch(name: str, args: dict) -> dict:
    ed = _edit()
    if args.get('part') in _SESSION['docs'] and name != 'drawing_open':
        ed.work = _doc_path(args['part']).parent
    if name == "drawing_open":
        part, workdir = args["part"], args.get("workdir", "")
        src = config.TEMPLATE_GEAR if part == "gear" else config.TEMPLATE_SHAFT
        wd = Path(workdir) if workdir else ed.work
        wd.mkdir(parents=True, exist_ok=True)
        dst = wd / f"{part}_working.dxf"
        shutil.copyfile(src, dst)
        _SESSION["docs"][part] = str(dst)
        _SESSION['applied'][part]=[]
        return {"part": part, "working": str(dst), "backend": BACKEND}
    if name == "entity_edit_text":
        part, handle = args["part"], args["handle"]
        from cad_agent.parsers.template_parser import parse_template
        current = parse_template(_doc_path(part)).text_by_handle(handle)
        if current is None:
            raise ValueError(f'handle {handle} 不存在')
        res = ed.apply_text(part, [{"handle": handle, "part": part, "kind": "dimension",
                                    "op": "E4", "old_raw": current.raw,
                                    "old_plain": args["old_plain"],
                                    "new_plain": args["new_plain"], "items": []}])
        if not res["applied"] and args.get("old_raw"):
            from cad_agent.parsers.template_parser import parse_template
            pt = parse_template(_doc_path(part))
            t = pt.text_by_handle(handle)
            raw = t.raw if t else ""
            res = ed.apply_text(part, [{"handle": handle, "part": part, "kind": "dimension",
                                        "op": "E4", "old_raw": raw,
                                        "old_plain": args["old_plain"],
                                        "new_plain": args["new_plain"], "items": []}])
        _SESSION['applied'][part]+=res['applied']
        return res
    if name == "entity_edit_geometry":
        return ed.apply_geo(args["part"], args["plan_geo"], reset=False)
    if name == "cad_batch":
        steps = args["steps"]
        res = ed.apply_text(args["part"], steps)
        if res["skipped"]:  # 原子性：任一失败整体报错（调用方重跑副本）
            raise RuntimeError(f"cad_batch 原子性失败 {len(res['skipped'])} 项: "
                               f"{[s.get('error') for s in res['skipped']]}")
        _SESSION['applied'][args['part']]+=res['applied']
        return res
    if name == "checkpoint_create":
        src = _doc_path(args["part"])
        ck = ed.work / "checkpoints"
        ck.mkdir(parents=True, exist_ok=True)
        dst = ck / f"{args['part']}_{args['label']}.dxf"
        shutil.copyfile(src, dst)
        return {"checkpoint": str(dst)}
    if name == "entity_list":
        from cad_agent.parsers.template_parser import parse_template
        pt = parse_template(_doc_path(args["part"]))
        return {"stats": pt.ms_stats, "n_texts": len(pt.texts)}
    if name == "entity_get":
        t = _read_texts(args["part"]).get(args["handle"])
        if t is None:
            raise ValueError(f"handle {args['handle']} 不存在")
        return t
    if name == "drawing_info":
        from cad_agent.parsers.template_parser import parse_template
        pt = parse_template(_doc_path(args["part"]))
        return {"dxfversion": pt.dxfversion, "codepage": pt.codepage,
                "ms_stats": pt.ms_stats, "bbox": pt.bbox}
    if name == "saveas":
        src = _doc_path(args["part"])
        dst = ed.work / f"{args['part']}_final.dxf"
        shutil.copyfile(src, dst)
        return {"final": str(dst)}
    if name in ("drawing_critique", "drawing_finalize", "drawing_verify_requirements"):
        # 质量闭环（进程内 qa 等价；finalize 与 critique 合并打分口径）
        from cad_agent.qa.quality import quality, verify_requirements, _snapshot_texts
        part = args["part"]
        plan = args.get('plan',{"text_ops": [], "geo_ops": []})
        plan['_applied_by_part']=_SESSION['applied']
        snap_all = {}
        tpl = config.TEMPLATE_GEAR if part == "gear" else config.TEMPLATE_SHAFT
        snap_all[part] = {h:{'plain':t} for h,t in _snapshot_texts_by(tpl).items()}
        q = quality(part, _doc_path(part), plan, snap_all[part],
                    n_tpl_entities=sum(1 for _ in _ms(tpl)))
        if name == "drawing_verify_requirements":
            if not args.get('data'):
                raise ValueError('verify 必须提供最终 data 表')
            return verify_requirements(part,_doc_path(part),args['data'])
        return q
    if name == "convert_dwg":
        from cad_agent.mcp.converter import Converter
        res = Converter(log_cb=lambda m: print(m,file=sys.stderr)).convert(Path(args["dxf"]), Path(args["dwg"]))
        res["verify"] = Converter.verify(Path(args["dxf"]), res)
        return res
    raise ValueError(f"unknown tool {name}")


def _ms(path: Path):
    import ezdxf
    return ezdxf.readfile(str(path)).modelspace()


def _snapshot_texts_by(tpl: Path) -> dict:
    import ezdxf
    from cad_agent.qa.quality import _snapshot_texts
    return _snapshot_texts(ezdxf.readfile(str(tpl)))


if __name__ == "__main__":
    rpc.serve(_spec(), dispatch)
