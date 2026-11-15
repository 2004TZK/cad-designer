# 减速器 CAD 自动出图流水线（cad-agent）

> 2026-11-14 代码审查修订：当前支持范围、已修复问题和未完成项见
> [代码审查与修复记录](docs/代码审查与修复记录.md)。原任务状态表中的“全部完成”不能替代实际验收。

「同格式 SRD 文档组 → 大齿轮+输出轴两张工程图」的可复刻流水线。
输入一组减速器设计文档（说明书 S / 取数报告 R / 绘图数据 D），自动提取绘图数据，
经查表换档、联动同步、尺寸链校验，基于总模板生成 CAD 工程图（.dwg）。

**流水线资产与算例数据分离**：`assets/`（模板结构资产/规则库/基准集）一次构建跨算例复用；
`output/runs/{case_id}/`（提取表/报告/中间 DXF/DWG）每算例一份。

## 快速开始

```bash
pip install -e .            # 基础（ezdxf/numpy/pyyaml）
pip install -e .[com]       # +DWG 转换（pywin32，需本机 AutoCAD）
pip install -e .[rag]       # +向量检索（torch/FlagEmbedding，bge-m3）
pip install -e .[llm]       # +LLM 辅助位（openai SDK；需 DEEPSEEK_API_KEY）

cad-agent build                          # 构建期：模板资产提取 + 规则库
cad-agent run --case case001绞车          # 运行期 P1~P9（金样例）
cad-agent run --case case002变体          # 换算例冒烟（含 U9 标题栏注入）
cad-agent run --case case001绞车 --engine mcp      # 经 stdio MCP 双会话执行（等价）
cad-agent run --case case001绞车 --no-llm          # 无 LLM 模式（FR-14 回归）
cad-agent spike                          # M2.5 几何更新 spike
cad-agent freeze / regress               # 基准冻结 / 金样例回归（diff=0）
cad-agent rag --query "表19-2 齿距累积总偏差"       # 向量检索直查
cad-agent signoff --file signoff.json --by 签署人   # 构建期会签（HB1/HB2/HB3）
cad-agent inspect                        # 状态巡检
```

## 算例

| 算例 | 用途 |
|---|---|
| `input/case001绞车/` | 金样例（需求文档 3.2 全表基准；regress 基准源） |
| `input/case002变体/` | 换算例冒烟：减重孔 6→4、直径 59→52（G1 几何）、轴段4 52→56、case.yaml 标题栏注入（U9） |
| `input/case003pending/` | H1 中断→答复→resume 演示（manual 选定值缺失） |
| `input/case004invalid/` | U13 异构拒收负向用例（第五部分缺失） |

新算例：复制同构 SRD 三件套到 `input/{case_id}/`，可选 `case.yaml`：

```yaml
title:
  designer: 张三
  course: 机械设计课程设计
  class_no: 飞制2401
  student_no: 2024010101
```

## 会签（构建期人工裁决落盘）

`cad-agent signoff --file signoff.json --by 姓名`，signoff.json 结构：

```json
{
  "HB1": {"U0": "accept", "U1": "accept(按清单4.1值)", "U2": "keep_template",
           "U6": "accept", "U8": "keep", "U15": "accept"},
  "HB1_conflicts": {"C4": "accept", "C5": "accept"},
  "HB2": {"key_slot": true, "fit_tolerance": true, "gear_precision": true,
           "center_distance_tol": true, "bearing_6206": true},
  "HB3": {"C4": "accept", "C5": "accept"}
}
```

签署记录落 `assets/signoff_record.md`；待签状态可用 `tests/test_stage2.py` 的 show_pending 或
inspect 查看（当前全部 pending_sign，取值按需求文档建议处置默认执行）。

## 交付物

- `output/runs/{case_id}/大齿轮.dwg、输出轴.dwg`（COM SaveAs；COM/ODA 双失败时 DXF 保底 delivery_mode=dxf_only）
- `output/runs/{case_id}/extracted/`（提取表/派生表/final 表/update_plan.json）
- `output/runs/{case_id}/reports/`（index.html / validation / quality / reconciliation / rag_hits）
- `assets/`（template_assets / formulas / lookup_tables / constants / linked_map / assertions / verdict_rules / layout_rules + baseline 基准集）

## 架构与文档

四份设计文档见仓库根：需求文档 / 工作流程与架构 / 改造方案 / 任务拆分（§14 为逐任务实施状态）。
红线：R-1 数值可追溯 · R-2 结构资产零变更 · R-3 几何变更白名单 · R-4 LLM 不入自动落图通道。

## 测试

```bash
python -m unittest discover -s tests -p test_review.py -v  # 真实DXF/隔离算例/故障注入，无需COM或API
python tests/test_gold.py     # 金样例 39 项断言 + 几何零变更 + DWG 齐备
python tests/test_stage2.py   # U13 拒收 / 会签机制 / U9 注入 / mock LLM / layout_rules
tools/calibrate_tau.py        # U5 τ 标定 + U11 bge-m3 同构验证
```

`cad-agent regress --no-llm` 现在会真正重新执行 P1~P9，再比较文本与几何。
`cad-agent convert --case case001绞车` 只重跑已冻结图纸的转换，并更新交付报告。
PowerShell 中可设 `$env:CAD_AGENT_DXF_ONLY='1'` 跳过 COM/ODA、直接生成同名中文 DXF；
撤销该变量后恢复 DWG 优先路径。ODA 可通过 `CAD_AGENT_ODA_CONVERTER` 指定可执行文件。

本机可用解释器为 `D:\Python\python3.13\python.exe`；PATH 中默认 Anaconda Python 未安装 ezdxf。
如直接运行报缺包，请使用已安装本项目的解释器。
