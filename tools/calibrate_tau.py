# -*- coding: utf-8 -*-
"""U5 检索阈值 τ 标定（清单 8.2 做 ground truth）+ U11 同构验证报告。"""
import json
import sys
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from cad_agent.rag.retriever import Retriever  # noqa: E402
from cad_agent import config  # noqa: E402

# ground truth：清单 8.2 本档行（键值对为对应 chunk 中应出现的关键词）
CASES = [
    {"query": "表19-2 齿距累积总偏差 F_p 单个齿距偏差 f_pt 齿廓总偏差 8级",
     "expect_chunk_contains": ["F_p", "19-2"]},
    {"query": "表14-26 平键键槽 剖面尺寸 t1 t2 轴槽宽 b 10 毂槽 JS9",
     "expect_chunk_contains": ["14-26"]},
    {"query": "表18-3 孔的极限偏差 H7 +0.025 上偏差 下偏差",
     "expect_chunk_contains": ["18-3"]},
    {"query": "表19-5 中心距极限偏差 fa 齿轮副",
     "expect_chunk_contains": ["19-5"]},
    {"query": "表19-4 径向跳动公差 Fr 值",
     "expect_chunk_contains": ["19-4"]},
    {"query": "表19-8 齿顶圆 公差 0.1m_n IT11",
     "expect_chunk_contains": ["19-8"]},
]

r = Retriever()
print("后端:", "bge-m3" if r.vector_ready() else "lexical_fallback")

iso = None
if r.vector_ready():
    iso = r.verify_isomorphism()
    print("U11 同构:", json.dumps(iso, ensure_ascii=False))
    if not iso["pass"]:
        print("!! 同构不达标，检查模型/库版本")
        sys.exit(2)

cal = r.calibrate_tau(CASES)
n_ok = cal["n_correct"]
print(f"标定结果: τ={cal['tau']}（{n_ok}/{cal['n_cases']} 命中 ground truth）")
for row in cal["rows"]:
    print(f"  - {row['query'][:24]}… top={row['top_score']} 命中={row['expected_found']}")

md = ["# 检索阈值标定与同构验证报告（U5/U11，T4-2/T1-4）", "",
      f"- 后端：{cal['backend']}", f"- **τ = {cal['tau']}**（ground truth 命中 {n_ok}/{cal['n_cases']}）",
      "", "| 查询 | top 分 | 命中 ground truth |", "|---|---|---|"]
md += [f"| {row['query'][:40]} | {row['top_score']} | {'✓' if row['expected_found'] else '✗'} |" for row in cal["rows"]]
if iso:
    md += ["", "## U11 同构验证（重编码 vs 建库向量）", "",
           "| chunk | cos | 通过(>0.99) |", "|---|---|---|"]
    md += [f"| {x['chunk_id']} | {x['cos']} | {'✓' if x['pass'] else '✗'} |" for x in iso["rows"]]
md += ["", "> 命中值采信仍须与清单 8.2 交叉/人工确认（R-4/FR-05）。"]
out = config.ASSETS_DIR / "tau_calibration.md"
out.write_text("\n".join(md), encoding="utf-8")
print(f"报告: {out}")
