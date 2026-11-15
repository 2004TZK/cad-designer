# -*- coding: utf-8 -*-
"""DXF→DWG 转换器（FR-09 / T4-4）。

优先级：COM SaveAs（本机 AutoCAD，Q3）→ ODA File Converter CLI（回退）→
DXF 保底交付（V1.2：delivery_mode=dxf_only，降级提示，P7 可单独重跑）。
"""
from __future__ import annotations

import subprocess
import os
import shutil
import tempfile
from pathlib import Path

from .. import config


class Converter:
    def __init__(self, log_cb=print):
        self.log = log_cb

    # ── COM 链路 ──
    def try_com(self, dxf: Path, dwg: Path) -> bool:
        self._close_stale(dxf, dwg)  # R2：清理本工程遗留的占用文档
        try:
            import win32com.client  # pywin32（extras: com）
        except ImportError:
            self.log("[converter] pywin32 未安装（pip install cad-agent[com]），COM 链路跳过")
            return False
        try:
            acad = win32com.client.Dispatch("AutoCAD.Application")
            acad.Visible = False
            # COM 按进程自身工作目录解析相对路径 → 必须传绝对路径
            d = acad.Documents.Open(str(Path(dxf).resolve()))
            # SaveAs 格式枚举：ac2018_dwg=64（AC1032，与模板一致）→ 低版本回退
            last_err = None
            for fmt in (64,):
                try:
                    d.SaveAs(str(Path(dwg).resolve()), fmt)
                    last_err = None
                    break
                except Exception as e2:
                    last_err = e2
            d.Close(False)
            if last_err:
                raise last_err
            return dwg.exists()
        except Exception as exc:  # COM 独占/未装/License 等（R2/U3）
            self.log(f"[converter] COM 失败: {exc}")
            return False

    # ── ODA 回退 ──
    def try_oda(self, dxf: Path, dwg: Path) -> bool:
        oda = os.environ.get('CAD_AGENT_ODA_CONVERTER',config.ODA_CONVERTER)
        if not oda or not Path(oda).exists():
            self.log("[converter] ODA File Converter 未配置/未安装，回退链路跳过")
            return False
        try:
            with tempfile.TemporaryDirectory(prefix='oda_',dir=dwg.parent) as tmp:
                out_dir=Path(tmp)
                subprocess.run([oda, str(dxf.parent.resolve()), str(out_dir.resolve()),
                                'ACAD2018','DWG','0','1',dxf.name],check=True,timeout=120)
                result=out_dir/dxf.with_suffix('.dwg').name
                if result.exists():
                    shutil.copyfile(result,dwg)
                    return True
            return False
        except Exception as exc:
            self.log(f"[converter] ODA 失败: {exc}")
            return False

    def convert(self, dxf: Path, dwg: Path) -> dict:
        """返回 {mode: dwg|dxf_only, path, note}。"""
        dxf, dwg = Path(dxf), Path(dwg)
        dwg.parent.mkdir(parents=True,exist_ok=True)
        dxf_only=os.environ.get('CAD_AGENT_DXF_ONLY')=='1'
        if not dxf_only and self.try_com(dxf, dwg):
            return {"mode": "dwg", "path": str(dwg), "note": "COM SaveAs"}
        if not dxf_only and self.try_oda(dxf, dwg):
            return {"mode": "dwg", "path": str(dwg), "note": "ODA 回退"}
        # V1.2：双失败 → DXF 保底交付（不阻塞 P8/P9）
        self.log(f"[converter] COM/ODA 双失败 → DXF 保底交付: {dxf.name}")
        target=dwg.with_suffix('.dxf')
        if target.resolve()!=dxf.resolve():
            shutil.copyfile(dxf,target)
        return {"mode": "dxf_only", "path": str(target),
                "note": "DWG 转换不可用（COM/ODA 双失败），DXF 保底交付；环境修复后可单独重跑 P7"}

    # ── 回读验证（P7 门禁） ──
    @staticmethod
    def verify(dxf: Path, result: dict) -> dict:
        import ezdxf
        src = ezdxf.readfile(str(dxf))
        n_src = sum(1 for _ in src.modelspace())
        target = result["path"]
        if result["mode"] == "dwg":
            # 实体计数一致验证：COM 打开 DWG 读回（可用时），否则文件存在性
            n_dwg = Converter._com_entity_count(Path(target).resolve())
            if n_dwg is not None:
                return {"pass": n_dwg == n_src, "entities_src": n_src, "entities_dwg": n_dwg,
                        "note": "COM 打开 DWG 回读实体计数比对"}
            return {"pass": False, "entities_src": n_src,
                    "note": "DWG 回读不可用，未验证；不能以文件存在代替保真校验"}
        try:
            from ..qa.snapshot import drawing_snapshot,snapshot_diff
            diff=snapshot_diff(drawing_snapshot(src),drawing_snapshot(ezdxf.readfile(target)))
            return {'pass':not diff,'entities_src':n_src,'diff':diff,'note':'交付 DXF 完整回读比对'}
        except (OSError,ezdxf.DXFError) as exc:
            return {'pass':False,'note':str(exc)}

    @staticmethod
    def _com_entity_count(dwg: Path) -> int | None:
        try:
            import win32com.client
            acad = win32com.client.Dispatch("AutoCAD.Application")
            acad.Visible = False
            d = acad.Documents.Open(str(dwg), True)  # 只读
            n = d.ModelSpace.Count
            d.Close(False)
            return int(n)
        except Exception:
            return None

    @staticmethod
    def _close_stale(*paths: Path):
        """关闭本工程路径下被 AutoCAD 占用的文档（R2 独占自愈；不动其他会话文档）。"""
        try:
            import win32com.client
            acad = win32com.client.Dispatch("AutoCAD.Application")
            targets = {str(Path(p).resolve()).lower() for p in paths if p.exists()}
            for i in range(acad.Documents.Count - 1, -1, -1):
                d = acad.Documents.Item(i)
                try:
                    name = str(d.FullName).lower()
                except Exception:
                    continue
                if name in targets:
                    d.Close(False)
        except Exception:
            pass
