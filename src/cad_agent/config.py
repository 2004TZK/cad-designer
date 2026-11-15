# -*- coding: utf-8 -*-
"""全局路径与常量配置。

流水线资产与算例数据分离（需求文档 1.1）：
- assets/  流水线资产（构建期产出，运行期只读）
- input/{case_id}/   算例输入（SRD×3 + case.yaml）
- output/runs/{case_id}/  算例产物（6.1/6.2）
"""
from __future__ import annotations

from pathlib import Path

# 项目根（src/cad_agent/config.py → 上溯三级）
ROOT = Path(__file__).resolve().parents[2]

# ── 输入资源 ────────────────────────────────────────────────
DWG_DIR = ROOT / "dwg"                # 总模板（只读，永不被写）
TEMPLATE_GEAR = DWG_DIR / "大齿轮.dxf"
TEMPLATE_SHAFT = DWG_DIR / "输出轴.dxf"
DOCS_DIR = ROOT / "docs"              # 清单 + 金样例 SRD 原始档案
DATA_LIST = DOCS_DIR / "大齿轮与输出轴绘图数据清单.md"
VECTORS_DIR = ROOT / "vectors"        # bge-m3 向量库（MVP 未启用）

# ── 流水线资产（构建期产出） ─────────────────────────────────
ASSETS_DIR = ROOT / "assets"
BASELINE_DIR = ASSETS_DIR / "baseline"  # regress 基准集（T5-3 冻结）

# ── 算例输入/输出 ───────────────────────────────────────────
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
RUNS_DIR = OUTPUT_DIR / "runs"

# 金样例
GOLD_CASE = "case001绞车"

# SRD 三文档文件名（B1 格式同构约束）
S_FILE = "一级减速器(含开式齿轮)设计说明书.txt"
R_FILE = "减速器CAD取数报告.txt"
D_FILE = "减速器绘图数据.txt"

# ── 环境开关（MVP 默认值，见任务拆分 U 项追踪） ────────────────
# FR-09：COM 不可用回退 ODA，双失败 DXF 保底（delivery_mode=dwg|dxf_only）
ODA_CONVERTER = ""   # ODA FileConverter 路径；空=未安装（本机实测无）
# FR-14：LLM 辅助位密钥（env）；未配置则辅助位整体关闭（U16/R-4）
DEEPSEEK_API_KEY = ""
# FR-05：bge-m3 模型路径（U11/U5 未闭环，MVP 检索走清单 8.2 兜底）
BGE_MODEL_DIR = Path("D:/CODE/bge/models/bge-m3")


def run_dir(case_id: str) -> Path:
    return RUNS_DIR / case_id


def ensure_run_tree(case_id: str) -> Path:
    """创建算例产物目录树（6.2 中间产物布局）。"""
    d = run_dir(case_id)
    for sub in ("extracted", "reports", "logs", "work"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d
