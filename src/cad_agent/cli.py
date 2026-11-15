# -*- coding: utf-8 -*-
"""cad-agent CLI（Q1：CLI 内核 + Web 预览为静态页）。

命令：
  build                       构建期：输入迁移 + 资产提取 + 规则库（B0~B3）
  run --case CASE             运行期 P1~P9（manual 缺失→PENDING 中断 H1）
  resume --case CASE --answers answers.json   中断恢复（H1/H2/H3）
  spike                       M2.5 几何更新 spike（T2.5-1~3）
  freeze --case CASE          金样例基准冻结（T5-3）
  regress --case CASE         金样例回归（FR-13，--no-llm 见 run_summary）
  inspect [--case CASE]       查看状态/资产/环境
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, config


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def cmd_build(args):
    from .builder.build import build
    rep = build()
    print("== 构建期完成（B1 资产 + B2 规则库）==")
    for part in ("gear", "shaft"):
        cov = rep[f"geo_coverage_{part}"]
        print(f"  {part}: 归组覆盖 {cov['grouped']}/{cov['entities_ms']} = {cov['coverage']}")
    probs = rep["template_assets"]["binding_verification_problems"]
    print(f"  绑定对账问题: {len(probs)}")
    for p in probs:
        print(f"    - {p}")
    print(f"  报告: {config.ASSETS_DIR / 'build_report.md'}")


def cmd_run(args):
    from .core.runner import run_case
    summary = run_case(args.case, answers=getattr(args, "answers", None),
                       engine=getattr(args, "engine", "inline"),
                       no_llm=getattr(args, "no_llm", None),resume=getattr(args,'resume',False))
    if summary.get("stage") == "PENDING":
        print(f"== {summary.get('point','H1')} 中断 ==")
        for p in summary["pending"]:
            print(f"  - [{p['part']}] {p['id']} {p['item']}: {p['reason']}")
        print(f"  答复后恢复: cad-agent resume --case {args.case} --answers answers.json")
        sys.exit(3)
    elif summary.get("stage") == "REJECTED":
        print(f"== 算例拒收（U13）== {summary['error']}")
        sys.exit(2)
    elif summary.get("stage") == "BLOCKED":
        print(f"== {summary.get('point','H2')} 未通过 == 见 state.json / reports")
        sys.exit(3)
    elif summary.get('stage') == 'FAILED':
        print(f"== {summary.get('point')} 执行失败 == {summary.get('error')}")
        sys.exit(4)
    else:
        acc = summary["acceptance"]
        print(f"== 完成 {args.case}（engine={summary['engine']}, llm={summary['llm_mode']}）==")
        print(f"  交付: {summary['delivery_mode']}")
        print(f"  finalize: {acc['finalize']}  verify: {acc['verify']}  consistency: {acc['consistency']}")


def cmd_resume(args):
    from .core.runner import run_case
    answers = {}
    if args.answers:
        answers = json.loads(open(args.answers, encoding="utf-8").read())
    cmd_run(argparse.Namespace(case=args.case, answers=answers,
                               engine=getattr(args, "engine", "inline"),
                               no_llm=getattr(args, "no_llm", None),resume=True))


def cmd_spike(args):
    from .builder.spike_runner import run_spike
    r = run_spike()
    print("== M2.5 spike ==")
    for it in r["items"]:
        print(f"  {it['id']}: {'✓' if it.get('pass') else '✗'}")
    print(f"  G5 阈值: {r['g5_threshold']['auto_follow_max_units']} 单位（{r['g5_threshold']['test_big']}）")
    print(f"  报告: {config.OUTPUT_DIR / 'spike' / 'spike_report.md'}")
    if not r.get('pass',False):
        sys.exit(4)


def cmd_freeze(args):
    from .qa.quality import freeze_baseline
    bdir = freeze_baseline(args.case, config.RUNS_DIR, config.BASELINE_DIR)
    print(f"== 基准冻结 == {bdir}")


def cmd_regress(args):
    from .qa.quality import regress
    from .core.runner import run_case
    summary=run_case(args.case,engine=getattr(args,'engine','inline'),no_llm=args.no_llm)
    if summary.get('stage')!='DONE':
        _print_json(summary)
        sys.exit(5)
    r = regress(args.case, config.RUNS_DIR, config.BASELINE_DIR)
    tag = "（已禁用 LLM 并重新运行 P1~P9）" if args.no_llm else ""
    print(f"== 回归 {args.case} {'✓ diff=0' if r['pass'] else '✗ 存在差异'} {tag}==")
    for part, pr in r["parts"].items():
        print(f"  {part}: {'✓' if pr['pass'] else '✗'} 文本={pr.get('text_diffs', '')} 几何={pr.get('geometry_diff', '')}")
    (config.run_dir(args.case)/'reports'/'regression.json').write_text(json.dumps(r,ensure_ascii=False,indent=1),encoding='utf-8')
    if not r["pass"]:
        sys.exit(5)


def cmd_signoff(args):
    from .builder.signoff import apply_signoff, show_pending
    data = json.loads(open(args.file, encoding="utf-8").read())
    rec = apply_signoff(data, by=args.by)
    print("== 会签完成 ==")
    for r in rec["applied"]:
        print(f"  {r['hb']} {r['id']}: {r['status']} ({r.get('decision', '')})")
    for r in rec["unknown"]:
        print(f"  ⚠ 未识别项: {r}")
    print(f"  记录: {config.ASSETS_DIR / 'signoff_record.md'}")


def cmd_convert(args):
    from .core.runner import convert_case
    result=convert_case(args.case)
    _print_json(result)
    if result['stage']!='DONE':
        sys.exit(4)


def cmd_rag(args):
    from .core.lookup import LookupEngine
    from .rag.retriever import Retriever
    assets = _load_assets_quiet()
    r = Retriever(assets["lookup_tables"])
    res = r.query(args.query, tau=args.tau)
    _print_json(res)


def _load_assets_quiet():
    need = ["template_assets.json", "formulas.json", "lookup_tables.json", "constants.json",
            "linked_map.json", "assertions.json", "verdict_rules.json"]
    return {n[:-5]: json.loads((config.ASSETS_DIR / n).read_text(encoding="utf-8")) for n in need}


def cmd_inspect(args):
    print(f"cad-agent {__version__}")
    print(f"根目录: {config.ROOT}")
    print(f"模板: {config.TEMPLATE_GEAR.exists()} / {config.TEMPLATE_SHAFT.exists()}")
    assets = sorted(p.name for p in config.ASSETS_DIR.glob("*.json")) if config.ASSETS_DIR.exists() else []
    print(f"资产: {assets}")
    if config.RUNS_DIR.exists():
        for r in sorted(config.RUNS_DIR.iterdir()):
            sf = r / "state.json"
            st = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
            print(f"  run {r.name}: {st.get('stage', '?')}")
    if args.case:
        s = config.RUNS_DIR / args.case / "run_summary.json"
        if s.exists():
            _print_json(json.loads(s.read_text(encoding="utf-8")))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cad-agent", description="减速器 CAD 自动出图流水线")
    ap.add_argument("--version", action="version", version=f"cad-agent {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="构建期：资产提取+规则库").set_defaults(func=cmd_build)
    p = sub.add_parser("run", help="运行期 P1~P9")
    p.add_argument("--case", required=True)
    p.add_argument("--engine", choices=["inline", "mcp"], default="inline",
                   help="inline=进程内 ezdxf（默认）；mcp=stdio MCP 双会话")
    p.add_argument("--no-llm", action="store_true", help="禁用 LLM 辅助位（FR-14/R-4 回归）")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("resume", help="中断恢复")
    p.add_argument("--case", required=True)
    p.add_argument("--answers", default="")
    p.add_argument("--engine", choices=["inline", "mcp"], default=None)
    p.add_argument("--no-llm", action="store_true",default=None)
    p.set_defaults(func=cmd_resume)
    sub.add_parser("spike", help="M2.5 几何更新 spike").set_defaults(func=cmd_spike)
    p = sub.add_parser("freeze", help="基准冻结")
    p.add_argument("--case", default=config.GOLD_CASE)
    p.set_defaults(func=cmd_freeze)
    p = sub.add_parser("regress", help="金样例回归")
    p.add_argument("--engine",choices=['inline','mcp'],default='inline')
    p.add_argument("--case", default=config.GOLD_CASE)
    p.add_argument("--no-llm", action="store_true", help="无 LLM 模式回归（FR-14）")
    p.set_defaults(func=cmd_regress)
    p = sub.add_parser('convert',help='仅重跑已冻结图纸的 P7 转换')
    p.add_argument('--case',required=True)
    p.set_defaults(func=cmd_convert)
    p = sub.add_parser("signoff", help="构建期会签（HB1/HB2/HB3）")
    p.add_argument("--file", required=True, help="会签 JSON 文件（见 README）")
    p.add_argument("--by", default="", help="签署人")
    p.set_defaults(func=cmd_signoff)
    p = sub.add_parser("rag", help="向量检索直查（FR-05）")
    p.add_argument("--query", required=True)
    p.add_argument("--tau", type=float, default=None, help="覆盖阈值 τ")
    p.set_defaults(func=cmd_rag)
    p = sub.add_parser("inspect", help="状态检查")
    p.add_argument("--case", default="")
    p.set_defaults(func=cmd_inspect)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
