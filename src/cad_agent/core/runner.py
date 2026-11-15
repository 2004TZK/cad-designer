# -*- coding: utf-8 -*-
"""运行期编排（FR-06）：P1~P9 状态机 + 中断-恢复。

状态：RUNNING / PENDING（manual 缺失等，H1）/ BLOCKED（断言新偏差，H2）/ DONE。
断点：runs/{case_id}/state.json；恢复：cad-agent resume --case X --answers answers.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .. import config
from ..parsers import docs_parser
from ..parsers.template_parser import parse_template
from ..core.calculator import derive as calc_derive
from ..core.dispatcher import Dispatcher
from ..core.lookup import LookupEngine
from ..core.validator import run_assertions, completeness, freeze
from ..mcp.editor import Editor
from ..mcp.converter import Converter
from ..qa.quality import quality, verify_requirements, consistency
from ..report.render import render_run_page
from ..rag.retriever import Retriever
from ..llm.advisor import LlmClient


def _log(run: Path, msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    with (run / "logs" / "run.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _load_assets() -> dict:
    need = ["template_assets.json", "formulas.json", "lookup_tables.json", "constants.json",
            "linked_map.json", "assertions.json", "verdict_rules.json", "layout_rules.json"]
    missing = [n for n in need if not (config.ASSETS_DIR / n).exists()]
    if missing:
        raise RuntimeError(f"流水线资产缺失 {missing}，请先执行 cad-agent build")
    result={Path(n).stem: json.loads((config.ASSETS_DIR / n).read_text(encoding="utf-8")) for n in need}
    from ..builder.asset_extractor import validate_assets
    validate_assets(result['template_assets'])
    return result


def run_case(case_id: str, answers: dict | None = None, engine: str | None = None,
             no_llm: bool | None = None, resume: bool = False) -> dict:
    """重放确定性阶段；恢复时合并已保存答复，输入变化时作废旧裁决。"""
    import hashlib
    from .geometry import unsupported_changes
    from .checks import _close
    run = config.ensure_run_tree(case_id)
    state_file = run / 'state.json'
    old = json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {}
    resuming = resume or answers is not None
    digest = hashlib.sha256()
    for name in (config.S_FILE,config.R_FILE,config.D_FILE,'case.yaml'):
        path=config.INPUT_DIR/case_id/name
        digest.update(path.read_bytes() if path.exists() else b'<missing>')
    fingerprint=digest.hexdigest()
    engine=engine or (old.get('engine','inline') if resuming else 'inline')
    no_llm=bool(old.get('no_llm',False) if no_llm is None and resuming else no_llm)
    state={'case_id':case_id,'stage':'P1','engine':engine,'no_llm':no_llm,
           'input_fingerprint':fingerprint,'answers':{}}
    log=lambda m:_log(run,m)

    def save(stage, **fields):
        state.update(stage=stage,updated=time.strftime('%F %T'),**fields)
        payload=json.dumps(state,ensure_ascii=False,indent=1)
        state_file.write_text(payload,encoding='utf-8')
        # 失败/中断也覆盖旧成功摘要，预览入口不得展示旧 DONE。
        (run/'run_summary.json').write_text(payload,encoding='utf-8')
        if stage!='DONE':
            from html import escape
            (run/'reports'/'index.html').write_text(
                '<!doctype html><meta charset="utf-8"><h1>'+escape(case_id)+' · '+stage+
                '</h1><pre>'+escape(payload)+'</pre>',encoding='utf-8')
        return dict(state)

    def pending(items, point='H1'):
        (run/'pending.json').write_text(json.dumps(items,ensure_ascii=False,indent=1),encoding='utf-8')
        log(f'{point} 中断：{len(items)} 项待处理')
        advice=llm.advise({'point':point,'pending':items}) if llm.enabled else None
        return save('PENDING',point=point,pending=items,llm_advice=advice)

    if resuming and old.get('input_fingerprint') and old['input_fingerprint']!=fingerprint:
        return save('BLOCKED',point='INPUT_CHANGED',error='SRD/case.yaml 已改变，请重新 run；旧答复不自动复用')
    journal=old.get('answers',{}) if resuming else {}
    incoming=answers or {}
    if not isinstance(incoming,dict):
        return save('BLOCKED',point='ANSWERS',error='answers 必须为 JSON 对象')
    values=dict(journal.get('values',{}))
    values.update(incoming.get('values',{}) if 'values' in incoming else
                  {k:v for k,v in incoming.items() if k.startswith(('gear.','shaft.'))})
    deviations={**journal.get('deviations',{}),**incoming.get('deviations',{})}
    geometry={**journal.get('geometry',{}),**incoming.get('geometry',{})}
    state['answers']={'values':values,'deviations':deviations,'geometry':geometry}
    save('P1')
    try:
        assets=_load_assets()
        llm=LlmClient(enabled=not no_llm)
        extracted=docs_parser.parse_case(config.INPUT_DIR/case_id)
        from ..parsers.docs_parser import Item
        for fid,value in values.items():
            part=fid.split('.')[0]
            if part not in ('gear','shaft'):
                raise ValueError(f'未知答复字段：{fid}')
            extracted[part]=[it for it in extracted[part] if it.id!=fid]
            extracted[part].append(Item(fid,fid,value,category='manual',
                                       source={'doc':'answers','section':'恢复答复','input_fingerprint':fingerprint}))
        primary={it.id:it for it in extracted['gear']+extracted['shaft']}
        required=['gear.m','gear.z1','gear.z2','gear.b2','gear.d_bore','gear.hub_l','gear.key_len',
                  'shaft.key1','shaft.key2']+[f'shaft.seg{i}_{a}' for i in range(1,7) for a in ('d','l')]
        missing=[{'id':fid,'part':fid.split('.')[0],'item':fid,'reason':'主参数缺失，需补全'}
                 for fid in required if fid not in primary or primary[fid].value is None]
        if missing:
            return pending(missing)
        import math
        for fid in required:
            value=primary[fid].value
            nums=value if isinstance(value,(tuple,list)) else [value]
            if fid in ('shaft.key1','shaft.key2') and len(nums)!=3:
                raise ValueError(f'{fid} 应为 [宽,高,长]')
            if any(isinstance(n,bool) or not isinstance(n,(float,int)) or not math.isfinite(n) or n<=0 for n in nums):
                raise ValueError(f'{fid} 必须为有限正数')
        for fid in ('gear.hole_n','gear.z1','gear.z2'):
            if fid in primary and (int(primary[fid].value)!=primary[fid].value or primary[fid].value<=0):
                raise ValueError(f'{fid} 必须为正整数')
        for part in ('gear','shaft'):
            (run/'extracted'/f'{part}.json').write_text(json.dumps(
                [it.to_dict() for it in extracted[part]],ensure_ascii=False,indent=1),encoding='utf-8')
        (run/'extracted'/'extracted_raw.json').write_text(json.dumps(
            {p:[it.to_dict() for it in extracted[p]] for p in ('gear','shaft')},ensure_ascii=False,indent=1),encoding='utf-8')
        save('P2')
        derived,checks=calc_derive(primary,assets['constants'])
        (run/'extracted'/'derived.json').write_text(json.dumps(
            {'derived':{k:v.to_dict() for k,v in derived.items()},'cross_checks':checks},ensure_ascii=False,indent=1),encoding='utf-8')
        disp=Dispatcher(assets['template_assets'],LookupEngine(assets['lookup_tables']),assets['verdict_rules'])
        data=disp.dispatch(extracted,derived,checks)
        _apply_case_yaml(data,_load_case_yaml(case_id),log)
        _write_reconciliation(run,data)
        if data['pending']:
            return pending(data['pending'])
        # 所有查表空值都必须转 H3，包括未绑定到图面的完备性项。
        misses=[(part,fid,it) for part in ('gear','shaft') for fid,it in data[part].items()
                if it['category']=='lookup' and (it['value'] is None or it['text'] is None)]
        rag_lines=['# 检索兜底（FR-05）','']
        rag_pending=[]
        if misses:
            retriever=Retriever(assets['lookup_tables'])
            for part,fid,it in misses:
                result=retriever.query(f"{it['item']} {it['source']}")
                structured=[llm.structure_hit(hit['excerpt']) for hit in result['hits'][:3]] if llm.enabled else []
                rag_lines += [f'## {fid}',json.dumps(result,ensure_ascii=False),json.dumps(structured,ensure_ascii=False)]
                rag_pending.append({'part':part,'id':fid,'item':it['item'],'reason':'档位未覆盖；检索候选需人工给出确认值',
                                    'retrieval':result})
        (run/'reports'/'rag_hits.md').write_text('\n'.join(rag_lines),encoding='utf-8')
        if rag_pending:
            return pending(rag_pending,'H3')
        save('P5')
        assertions,assert_ok=run_assertions(data,assets['assertions'],deviations)
        comp_rows,comp_ok=completeness(data,assets['template_assets']['bindings'])
        _write_validation(run,assertions,comp_rows,assert_ok and comp_ok)
        if not assert_ok or not comp_ok:
            return save('BLOCKED',point='H2',assertions_fail=[a for a in assertions if a['status']=='fail'],
                        incomplete=[r for r in comp_rows if r['status']!='ok'])
        tassets=assets['template_assets']
        gaps=unsupported_changes(data,tassets)
        if gaps:
            return save('BLOCKED',point='GEOMETRY_UNSUPPORTED',unsupported=gaps)
        for part in ('gear','shaft'):
            pt=parse_template(config.TEMPLATE_GEAR if part=='gear' else config.TEMPLATE_SHAFT)
            tassets['geo_groups'][part]['_entities']=[{'handle':e.handle,'type':e.type,'data':e.data} for e in pt.entities]
        plan=freeze(data,tassets,run,case_id)
        limit=assets.get('layout_rules',{}).get('g5_follow_threshold_units',20)
        plan_digest=hashlib.sha256(json.dumps(plan['geo_ops'],sort_keys=True).encode()).hexdigest()
        needs_confirm=False
        for op in plan['geo_ops']:
            op['follow_threshold']=limit
            offsets=[abs(n-o) for n,o in zip(op.get('new_bounds',[]),op.get('old_bounds',[]))]
            offsets += [abs(m.get('dy',0)) for m in op.get('dim_follow',[])]
            if offsets and max(offsets)>limit:
                needs_confirm=True
                op['large_move_confirmed']=bool(geometry.get('allow_large_moves') and geometry.get('plan_digest')==plan_digest)
        if needs_confirm and not all(o.get('large_move_confirmed',True) for o in plan['geo_ops']):
            return pending([{'id':'geometry','part':'both','item':'G5 跟随超阈值','reason':'检查 plan_preview 中两张 DXF 后确认',
                             'plan_digest':plan_digest,'preview':'work/plan_preview'}],'H4')
        (run/'extracted'/'update_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=1),encoding='utf-8')
        save('P6')
        client=None
        if engine=='mcp':
            from ..mcp.client import McpClient
            client=McpClient('ezdxf',log_cb=log)
            editor=_McpEditorAdapter(client,run/'work')
        else:
            editor=Editor(run/'work',log_cb=log)
        results={}
        try:
            for part in ('gear','shaft'):
                if client: editor.open(part)
                geo=editor.apply_geo(part,[o for o in plan['geo_ops'] if o['part']==part])
                txt=editor.apply_text(part,[o for o in plan['text_ops'] if o['part']==part])
                results[part]={'geo':geo,'text':txt}
        finally:
            if client: client.close()
        (run/'logs'/'execution.json').write_text(json.dumps(results,ensure_ascii=False,indent=1),encoding='utf-8')
        plan['_applied_by_part']={p:results[p]['text']['applied'] for p in results}
        save('P7')
        delivery=_convert_parts(run,engine,log)
        save('P8')
        q,v,c={},{},{}
        for part in ('gear','shaft'):
            f=run/'work'/f'{part}_final.dxf'
            q[part]=quality(part,f,plan,tassets['value_snapshot'][part],sum(tassets['templates'][part]['ms_stats'].values()))
            v[part]=verify_requirements(part,f,data,tassets['bindings'])
            c[part]=consistency(part,f,plan,tassets['value_snapshot'][part],data)
        accepted=all(q[p]['pass'] and v[p]['pass'] and c[p]['pass'] and delivery[p]['verify']['pass'] for p in q)
        (run/'reports'/'quality.json').write_text(json.dumps({'quality':q,'verify':v,'consistency':c},ensure_ascii=False,indent=1),encoding='utf-8')
        summary={'case_id':case_id,'engine':engine,'llm_mode':'off(--no-llm)' if no_llm else ('enabled' if llm.enabled else 'off'),
                 'delivery_mode':'dwg' if all(d['mode']=='dwg' for d in delivery.values()) else 'dxf_only',
                 'delivery':delivery,'acceptance':{'completeness':comp_ok,'assertions':f"全部通过（{sum(a['status']=='exempt' for a in assertions)} 项具体偏差留痕）",
                     'finalize':{p:q[p]['score'] for p in q},'verify':{p:v[p]['pass'] for p in v},'consistency':{p:c[p]['pass'] for p in c},
                     'delivery_verify':{p:delivery[p]['verify']['pass'] for p in delivery}},'llm_assist':llm.status()}
        stage='DONE' if accepted else 'BLOCKED'
        result=save(stage,**{k:val for k,val in summary.items() if k!='case_id'},point='P9' if accepted else 'P8')
        (run/'reports'/'quality.md').write_text(_md_quality(q,v,c,delivery),encoding='utf-8')
        (run/'reports'/'consistency.md').write_text('# 文本与几何一致性\n\n'+json.dumps(c,ensure_ascii=False,indent=2),encoding='utf-8')
        render_run_page(case_id,run,data,plan,q,v,c,delivery,result)
        from ..report.render import render_index_all
        render_index_all(config.RUNS_DIR,config.OUTPUT_DIR)
        if accepted:
            (run/'pending.json').write_text('[]',encoding='utf-8')
        log(f'运行结束：{stage}')
        return result
    except docs_parser.RejectCaseError as exc:
        return save('REJECTED',point='P1',error=str(exc))
    except Exception as exc:
        log(f"{state['stage']} 失败：{exc}")
        return save('FAILED',point=state['stage'],error=f'{type(exc).__name__}: {exc}')


def _convert_parts(run, engine, log):
    client=None
    if engine=='mcp':
        from ..mcp.client import McpClient
        client=McpClient('com',log_cb=log)
    result={}
    try:
        converter=Converter(log_cb=log)
        for part,name in (('gear','大齿轮'),('shaft','输出轴')):
            dxf,dwg=run/'work'/f'{part}_final.dxf',run/f'{name}.dwg'
            entry=client.call('convert_dwg',dxf=str(dxf),dwg=str(dwg)) if client else converter.convert(dxf,dwg)
            entry['verify']=Converter.verify(dxf,entry)
            result[part]=entry
    finally:
        if client: client.close()
    return result


def convert_case(case_id):
    """仅重跑 P7；沿用冻结 DXF，避免重新解析或出图。"""
    run=config.run_dir(case_id)
    summary=json.loads((run/'run_summary.json').read_text(encoding='utf-8'))
    if 'acceptance' not in summary:
        raise ValueError('尚无完成出图并验收的运行，不能单独转换')
    delivery=_convert_parts(run,summary.get('engine','inline'),lambda m:_log(run,m))
    summary.update(delivery=delivery,delivery_mode='dwg' if all(d['mode']=='dwg' for d in delivery.values()) else 'dxf_only')
    acc=summary['acceptance']
    acc['delivery_verify']={p:d['verify']['pass'] for p,d in delivery.items()}
    ok=all(acc['delivery_verify'].values()) and all(acc['verify'].values()) and all(acc['consistency'].values()) and all(s>=90 for s in acc['finalize'].values())
    summary.update(stage='DONE' if ok else 'BLOCKED',point='P9' if ok else 'P7',updated=time.strftime('%F %T'))
    for name in ('state.json','run_summary.json'):
        (run/name).write_text(json.dumps(summary,ensure_ascii=False,indent=1),encoding='utf-8')
    qa_file=run/'reports'/'quality.json'
    if qa_file.exists():
        qa=json.loads(qa_file.read_text(encoding='utf-8'))
        data={p:json.loads((run/'extracted'/f'final_{p}.json').read_text(encoding='utf-8')) for p in ('gear','shaft')}
        plan=json.loads((run/'extracted'/'update_plan.json').read_text(encoding='utf-8'))
        (run/'reports'/'quality.md').write_text(_md_quality(qa['quality'],qa['verify'],qa['consistency'],delivery),encoding='utf-8')
        render_run_page(case_id,run,data,plan,qa['quality'],qa['verify'],qa['consistency'],delivery,summary)
    return summary


def _load_case_yaml(case_id: str) -> dict:
    f = config.INPUT_DIR / case_id / "case.yaml"
    if not f.exists():
        return {}
    import yaml
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def _apply_case_yaml(data: dict, cfg: dict, log) -> None:
    """U9：designer/course/class_no/student_no → 标题栏静态项覆盖（生成 E2 文本操作）。

    class_no+student_no 注入 #4CA/#A8C 时同时消解 U8 异常文本。
    """
    title = cfg.get("title") or {}
    injected = []
    for part in ("gear", "shaft"):
        table = data[part]
        if title.get("designer") and f"{part}.title_designer" in table:
            it = table[f"{part}.title_designer"]
            it["text"] = str(title["designer"])
            it["value"] = str(title["designer"])
            it["source"] = {**it["source"], "note": "case.yaml 注入（U9）"}
            injected.append(f"{part}.title_designer")
        if title.get("course") and f"{part}.title_course" in table:
            it = table[f"{part}.title_course"]
            it["text"] = str(title["course"])
            it["value"] = str(title["course"])
            it["source"] = {**it["source"], "note": "case.yaml 注入（U9）"}
            injected.append(f"{part}.title_course")
        if title.get("class_no") and title.get("student_no") and f"{part}.abnormal_text" in table:
            text = f"{title['class_no']}|{title['student_no']}"
            it = table[f"{part}.abnormal_text"]
            it["text"] = text
            it["value"] = text
            it["verdict"] = "u9_inject(u8_resolved)"
            it["source"] = {**it["source"], "note": "case.yaml 注入班级/学号，替换异常文本（U8 消解）"}
            injected.append(f"{part}.abnormal_text")
    if injected:
        log(f"U9 标题栏注入：{injected}")


# ── 引擎适配器（MCP 会话 → 与 inline Editor 同接口） ──

class _McpEditorAdapter:
    """经 stdio MCP 会话 A 执行 P6（T1-2 会话层；与 inline 等价）。"""

    def __init__(self, client, work: Path):
        self.c = client
        self.work = Path(work)
        self.work.mkdir(parents=True, exist_ok=True)

    def open(self, part: str):
        self.c.call("drawing_open", part=part, workdir=str(self.work))

    def apply_geo(self, part: str, plan_geo: list[dict]) -> dict:
        if not plan_geo:
            return {"moved_entities": [], "working": str(self.work / f"{part}_working.dxf")}
        return self.c.call("entity_edit_geometry", part=part, plan_geo=plan_geo)

    def apply_text(self, part: str, plan_text: list[dict]) -> dict:
        return self.c.call("cad_batch", part=part, steps=plan_text)


# ── 报告生成 ──

def _write_reconciliation(run: Path, data: dict):
    lines = ["# 三通道对照与差异报告（FR-03，reconciliation.md）", "",
             "| 项 | 通道 | 最终值 | 模板现值 | 裁决 | 来源 |", "|---|---|---|---|---|---|"]
    for part in ("gear", "shaft"):
        for fid, it in data[part].items():
            if it["template"] and it["template"] != it["text"] and it["channel"] == "A":
                lines.append(f"| {part}.{fid} | A | {it['text']} | {it['template']} | 模板修正（A 通道为准） | {json.dumps(it['source'], ensure_ascii=False)} |")
            elif it["channel"] == "B" and it.get("source", {}).get("note"):
                lines.append(f"| {part}.{fid} | B | {it['text']} | {it['template'] or '-'} | 模板为准/差异记录 | {it['source'].get('note', '')} |")
    lines += ["", "## 联动同步（FR-04）", ""]
    for c in data["linked_checks"]:
        lines.append(f"- {'✓' if c['pass'] else '✗'} {c['group']}：{c['detail']}")
    (run / "reports" / "reconciliation.md").write_text("\n".join(lines), encoding="utf-8")


def _write_validation(run: Path, assertions, comp_rows, ok):
    lines = ["# 校验报告（FR-07，validation.md）", "",
             f"**结论：{'全绿放行' if ok else '存在未决项（BLOCKED）'}**", "",
             "## A1~A15 断言", "", "| # | 状态 | 期望 | 实际 | 备注 |", "|---|---|---|---|---|"]
    for a in assertions:
        mark = {"pass": "✓", "exempt": "⊙豁免", "fail": "✗"}[a["status"]]
        lines.append(f"| {a['id']} | {mark} | {a['expect']} | {a['actual']} | {a['note']} |")
    lines += ["", "## 完备性矩阵", "", "| 零件 | 项 | 绑定 | 状态 | 值 | 通道 |", "|---|---|---|---|---|---|"]
    for r in comp_rows:
        lines.append(f"| {r['part']} | {r['id']} | {r['binding']} | {r['status']} | {r.get('value', '')} | {r.get('channel', '')} |")
    (run / "reports" / "validation.md").write_text("\n".join(lines), encoding="utf-8")


def _md_quality(q, v, c, delivery) -> str:
    lines = ["# 质量与一致性报告（FR-10/12，quality.md）", ""]
    for part in q:
        lines += [f"## {part}", "",
                  f"- finalize 得分：**{q[part]['score']}**（阈值 {q[part]['threshold']}，{'通过' if q[part]['pass'] else '未过'}）"]
        for chk in q[part]["checks"]:
            lines.append(f"  - {'✓' if chk['pass'] else '✗'} {chk['check']}（{chk['weight']} 分）{chk['note']}")
        lines.append(f"- verify 实测：{'通过' if v[part]['pass'] else '未过'}")
        for r in v[part]["results"]:
            lines.append(f"  - {'✓' if r['found_on_drawing'] else '✗'} {r['item']} = {r['expect']}")
        lines.append(f"- 文本一致性：{'diff=0 通过' if c[part]['pass'] else '存在差异'}")
        lines.append(f"- 交付：{delivery[part]['mode']}（{delivery[part]['note']}）")
        lines.append("")
    return "\n".join(lines)
