# -*- coding: utf-8 -*-
"""静态预览页渲染（FR-11 / T6-1，Q10：静态 HTML，FastAPI+Vue 留 V2）。"""
from __future__ import annotations

import json
from pathlib import Path


def render_run_page(case_id, run: Path, data, plan, q, v, c, delivery, summary):
    run = Path(run)

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows = []
    for part in ("gear", "shaft"):
        for fid, it in data[part].items():
            diff = "" if it["template"] in (None, it["text"]) else \
                f'<span class="chg">{esc(it["template"])} → {esc(it["text"])}</span>'
            rows.append(
                f"<tr><td>{part}</td><td>{esc(fid)}</td><td>{esc(it['item'])}</td>"
                f"<td>{it['category']}</td><td>{it['channel']}</td>"
                f"<td>{esc(it['text'])}</td><td>{diff or esc(it['template'] or '-')}</td>"
                f"<td>{esc(it['verdict'])}</td><td>{esc(json.dumps(it['source'], ensure_ascii=False))[:80]}</td></tr>")

    ta = "".join(
        f"<tr><td>{op['handle']}</td><td>{op['part']}</td><td>{op['op']}</td>"
        f"<td>{esc(op['old_plain'])}</td><td>{esc(op['new_plain'])}</td></tr>"
        for op in plan["text_ops"]) or "<tr><td colspan=5>（无 — 金样例几何/文本零变更项之外无操作）</td></tr>"

    acc = summary["acceptance"]
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>{esc(case_id)} 运行报告</title><style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:24px;color:#222}}
h1{{border-bottom:2px solid #345}} table{{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}}
td,th{{border:1px solid #bbb;padding:4px 6px;text-align:left}} th{{background:#eef}}
.chg{{color:#b00;font-weight:600}} .ok{{color:#080;font-weight:700}} .bad{{color:#c00;font-weight:700}}
.badge{{display:inline-block;padding:2px 10px;border-radius:10px;background:#345;color:#fff;margin-right:8px}}
</style></head><body>
<h1>{esc(case_id)} · 出图流水线运行报告</h1>
<p class="{'ok' if summary['stage']=='DONE' else 'bad'}">运行状态：{summary['stage']}</p>
<p><span class="badge">交付 {summary['delivery_mode']}</span>
<span class="badge">finalize {acc['finalize']['gear']}/{acc['finalize']['shaft']}</span>
<span class="badge">verify {'✓' if all(acc['verify'].values()) else '✗'}</span>
<span class="badge">consistency {'✓' if all(acc['consistency'].values()) else '✗'}</span>
<span class="badge">断言 {esc(acc['assertions'])}</span>
<span class="badge">LLM {esc(summary['llm_assist']['note'])[:40]}</span></p>

<h2>交付物</h2><table><tr><th>零件</th><th>模式</th><th>路径</th><th>说明</th></tr>
{''.join(f"<tr><td>{p}</td><td>{d['mode']}</td><td>{esc(d['path'])}</td><td>{esc(d['note'])}</td></tr>" for p, d in delivery.items())}</table>

<h2>文本替换（update_plan → E1~E5/G4）</h2>
<table><tr><th>handle</th><th>零件</th><th>操作</th><th>旧值</th><th>新值</th></tr>{ta}</table>

<h2>落图数据表（三通道 + 来源留痕 R-1）</h2>
<table><tr><th>零件</th><th>项 id</th><th>图面项目</th><th>四分类</th><th>通道</th><th>最终值</th><th>模板现值</th><th>裁决</th><th>来源</th></tr>
{''.join(rows)}</table>

<h2>报告文件</h2><ul>
<li><a href="reconciliation.md">reconciliation.md（对照与差异）</a></li>
<li><a href="rag_hits.md">rag_hits.md（检索兜底）</a></li>
<li><a href="validation.md">validation.md（断言+完备性）</a></li>
<li><a href="quality.md">quality.md（质量+一致性）</a></li>
<li><a href="consistency.md">consistency.md（文本一致性明细）</a></li>
<li><a href="../run_summary.json">run_summary.json</a></li>
<li><a href="../extracted/update_plan.json">update_plan.json</a></li></ul>
<p><i>生成时间 {esc(summary['updated'])} · 减速器 CAD 自动出图流水线 MVP</i></p></body></html>"""
    (run / "reports" / "index.html").write_text(html, encoding="utf-8")


def render_index_all(runs_dir: Path, out: Path):
    import os
    from urllib.parse import quote
    links = "".join(
        f"<li><a href='{quote(Path(os.path.relpath(p / 'reports' / 'index.html', out)).as_posix())}'>{p.name}</a></li>"
        for p in sorted(Path(runs_dir).iterdir()) if (p / "reports" / "index.html").exists())
    (Path(out) / "index.html").write_text(
        f"<!DOCTYPE html><meta charset='utf-8'><title>算例总览</title><h1>算例总览</h1><ul>{links}</ul>",
        encoding="utf-8")
