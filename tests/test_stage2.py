# -*- coding: utf-8 -*-
"""阶段二功能测试（可独立运行：python tests/test_stage2.py）。

覆盖：U13 异构拒收 / 会签机制 / --no-llm mock / layout_rules / U9 注入。
"""
import json
import shutil
import sys
import io
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

fails = []


def check(name, ok, note=""):
    print(f"  {'✓' if ok else '✗'} {name} {note}")
    if not ok:
        fails.append(name)


print("== T1 U13 异构拒收 ==")
from cad_agent.parsers import docs_parser  # noqa: E402
from cad_agent import config  # noqa: E402
try:
    docs_parser.parse_case(config.INPUT_DIR / "case004invalid")
    check("case004invalid 应被拒收", False)
except docs_parser.RejectCaseError as e:
    check("case004invalid 拒收（RejectCaseError）", "第五部分" in str(e))

print("== T2 会签机制（临时资产目录演练） ==")
from cad_agent.builder.signoff import apply_signoff, show_pending  # noqa: E402
tmp = Path(tempfile.mkdtemp(prefix="cad_signoff_"))
for f in ("verdict_rules.json", "lookup_tables.json", "layout_rules.json"):
    shutil.copyfile(config.ASSETS_DIR / f, tmp / f)
rec = apply_signoff({
    "HB1": {"U0": "accept", "U1": "accept(按清单4.1值)", "U2": "keep_template",
            "U6": "accept", "U8": "keep", "U15": "accept"},
    "HB1_conflicts": {"C4": "accept", "C5": "accept"},
    "HB2": {"key_slot": True, "fit_tolerance": True, "gear_precision": True,
            "center_distance_tol": True, "bearing_6206": True},
    "HB3": {"C4": "accept", "C5": "accept"},
}, by="测试署名", assets_dir=tmp)
rules = json.loads((tmp / "verdict_rules.json").read_text(encoding="utf-8"))
check("HB1 六项签署", all(v["status"] == "signed" for v in rules["u_signoffs"].values()))
check("HB2 五表逐行 signed", all(r.get("row_signed") for t in
      [json.loads((tmp / "lookup_tables.json").read_text(encoding="utf-8"))[n]
       for n in ("key_slot", "fit_tolerance")] for r in t["rows"]))
layout = json.loads((tmp / "layout_rules.json").read_text(encoding="utf-8"))
check("HB3 属性判定签署", all("测试署名" in layout["attribute_verdicts"][k]["hb3_signed"]
                             for k in ("C4", "C5")))
check("签署记录落盘", (tmp / "signoff_record.md").exists())
shutil.rmtree(tmp, ignore_errors=True)

print("== T3 layout_rules.json 独立交付 ==")
lr = config.ASSETS_DIR / "layout_rules.json"
check("文件存在", lr.exists())
if lr.exists():
    d = json.loads(lr.read_text(encoding="utf-8"))
    check("含 G5 阈值/属性判定/绑定摘要/U9 注入位",
          all(k in d for k in ("g5_follow_threshold_units", "attribute_verdicts",
                               "bindings_digest", "u9_injectable_handles")))

print("== T4 U9 注入产物（case002变体） ==")
fg = config.RUNS_DIR / "case002变体" / "extracted" / "final_gear.json"
if fg.exists():
    g = json.loads(fg.read_text(encoding="utf-8"))
    check("设计者注入", g.get("gear.title_designer", {}).get("text") == "张三")
    check("班级|学号注入（U8 消解）",
          "飞制2401|2024010101" == g.get("gear.abnormal_text", {}).get("text", ""))
else:
    check("case002 变体产物存在（先 cad-agent run --case case002变体）", False)

print("== T5 mock LLM R-4 门禁 ==")
import os  # noqa: E402
os.environ["CAD_AGENT_LLM_MOCK"] = "1"
from cad_agent.llm.advisor import LlmClient  # noqa: E402
llm = LlmClient()
out = llm.structure_hit("某表内容")
check("mock 启用且标记需人工确认", llm.enabled and out.get("needs_human_confirm") is True)
os.environ["CAD_AGENT_LLM_MOCK"] = "0"
check("--no-llm 强制关闭", LlmClient(enabled=False).enabled is False)

print()
if fails:
    print(f"失败 {len(fails)} 项: {fails}")
    sys.exit(1)
print("阶段二功能测试全部通过")
