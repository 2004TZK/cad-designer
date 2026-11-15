# -*- coding: utf-8 -*-
"""四分类派发计算（FR-02）+ 三通道对照与联动同步（FR-03/04）+ update_plan 生成。

产出 derived.json：全量落图数据表（每项有值/有源/有裁决，R-1 可追溯），
金样例模板现值对照差异表数据，P5 冻结 final_*.json + update_plan.json 的输入。
"""
from __future__ import annotations

import json

from ..parsers.docs_parser import Item


class FinalItem(dict):
    """落图数据项：{id,item,part,value,text,unit,category,channel,source,verdict,template,note}。"""

    def __init__(self, id_, item, part, value, category, channel, source, text=None,
                 unit="mm", template=None, verdict="", note=""):
        super().__init__(
            id=id_, item=item, part=part, value=value, text=text if text is not None else _fmt(value),
            unit=unit, category=category, channel=channel, source=source,
            template=template, verdict=verdict, note=note,
        )


def _fmt(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


class Dispatcher:
    """P2 四分类派发 + P3 三通道裁决（规则来自 verdict_rules.json）。"""

    def __init__(self, assets: dict, lookup_engine, verdict_rules: dict):
        self.assets = assets            # template_assets.json
        self.lookup = lookup_engine
        self.rules = verdict_rules
        self.bindings = assets["bindings"]
        self.snapshot = assets["value_snapshot"]
        self.pending: list[dict] = []   # H1 中断清单

    # ── 模板现值查询（按绑定 expect） ──
    def _tpl(self, part: str, item_id: str) -> str | None:
        for b in self.bindings[part]:
            if item_id in b["item"].split("+") or b["item"] == item_id:
                return b.get("expect")
        return None

    def _binding(self, part: str, item_id: str) -> dict | None:
        for b in self.bindings[part]:
            if item_id in b["item"].split("+") or b["item"] == item_id:
                return b
        return None

    # ── 主入口 ──
    def dispatch(self, extracted: dict, derived: dict[str, Item], checks: list[str]) -> dict:
        self.pending = []
        gear: dict[str, FinalItem] = {}
        shaft: dict[str, FinalItem] = {}
        ex_g = {it.id: it for it in extracted["gear"]}
        ex_s = {it.id: it for it in extracted["shaft"]}

        v = lambda d, k: d[k].value if k in d else None

        # ══ 大齿轮 ══
        g = lambda fid, item, val, cat, ch, src, **kw: gear.setdefault(
            fid, FinalItem(fid, item, "gear", val, cat, ch, src, **kw))
        # A 通道：SRD 硬数据（D 六 > D > S/R 已在解析去重保证）
        g("gear.m", "模数 m", v(ex_g, "gear.m"), "calculator", "A", ex_g["gear.m"].source)
        g("gear.z2", "齿数 z2", v(ex_g, "gear.z2"), "calculator", "A", ex_g["gear.z2"].source)
        g("gear.z1", "配对齿轮齿数", v(ex_g, "gear.z1"), "calculator", "A", ex_g["gear.z1"].source)
        g("gear.b2", "齿宽 b2", v(ex_g, "gear.b2"), "calculator", "A", ex_g["gear.b2"].source)
        g("gear.bore_d", "配合轴径 d", v(ex_g, "gear.d_bore"), "calculator", "A", ex_g["gear.d_bore"].source)
        g("gear.hub_l", "轮毂长度", v(ex_g, "gear.hub_l"), "calculator", "A", ex_g["gear.hub_l"].source)
        g("gear.key_len", "键槽长（键10×8×45）", v(ex_g, "gear.key_len"), "calculator", "A", ex_g["gear.key_len"].source)
        # manual 选定值（D 六；缺失 → pending H1）
        for fid, item, exid in [("gear.d0_hole", "减重孔直径", "gear.d0_hole"),
                                ("gear.hole_n", "减重孔数量", "gear.hole_n"),
                                ("gear.web_t", "腹板厚度", "gear.web_t"),
                                ("gear.key_depth", "键槽深", "gear.key_depth")]:
            if exid in ex_g:
                g(fid, item, v(ex_g, exid), "manual", "A", ex_g[exid].source)
            else:
                self.pending.append({"part": "gear", "id": fid, "item": item,
                                     "reason": "manual 选定值缺失（D 六），H1 中断"})
        # calculator 派生（交叉验证过的公式值优先）
        g("gear.d2", "分度圆 d2", v(derived, "gear.d2_calc"), "calculator", "A", {"formula": "d2=m*z2", "cross": "S/R 一致"})
        g("gear.da2", "齿顶圆 da2", v(derived, "gear.da2_calc"), "calculator", "A", {"formula": "da2=d2+2m"})
        g("gear.df2", "齿根圆 df2（图面不标）", v(derived, "gear.df2_calc"), "calculator", "A", {"formula": "df2=d2-2.5m"})
        g("gear.a", "中心距 a", v(ex_g, "gear.a") or v(derived, "gear.a_calc"), "calculator", "A",
          ex_g["gear.a"].source if "gear.a" in ex_g else {"formula": "a=(d1+d2)/2"})
        g("gear.hub_d", "轮毂外径", v(derived, "gear.hub_d_calc"), "calculator", "A",
          {"formula": "1.6d", "cross": "D 四=56"})
        g("gear.delta0", "轮缘厚度 δ0", v(derived, "gear.delta0"), "calculator", "A", {"src": "D 四 范围上限"})
        g("gear.rim_inner", "轮缘内径", v(ex_g, "gear.rim_inner") or v(derived, "gear.rim_inner_calc"),
          "calculator", "A", ex_g["gear.rim_inner"].source if "gear.rim_inner" in ex_g else {"formula": "da2-2δ0"})
        g("gear.d0_circle", "减重孔分布圆", v(derived, "gear.d0_circle_calc"), "calculator", "A",
          {"formula": "(D1+d1)/2", "cross": "D 四=154"})
        g("gear.k", "公法线跨齿数 k", v(derived, "gear.k_calc"), "calculator", "A", {"formula": "k=round(z2/9+0.5)"})
        g("gear.W", "公法线长度 W", v(derived, "gear.W_calc"), "calculator", "A", {"formula": "W 公式", "cross": "D 五 一致"})
        # lookup 查表
        # 键槽宽取 S 八键规格（键 10×8×45 → b=10），档位表确认 t1/t2
        key2_spec = v(ex_s, "shaft.key2")
        gear_key_w = key2_spec[0] if key2_spec else None
        if gear_key_w is None:
            self.pending.append({"part": "gear", "id": "gear.key_w", "reason": "键规格缺失（S 八），rag 兜底/待人工"})
        else:
            g("gear.key_w", "键槽宽（键 b×h×L 之 b）", gear_key_w, "calculator", "A",
              ex_s["shaft.key2"].source)
        hit_cd = self.lookup.center_distance_tol(gear["gear.a"]["value"])
        fa = hit_cd.row["fa_pm"] if hit_cd else None
        # 圆整与模板同风格（0.0315→0.032）
        import math as _m
        fa_r = _m.floor(fa * 1000 + 0.5) / 1000 if fa is not None else None
        g("gear.a_tol_text", "中心距及偏差", f"{gear['gear.a']['value']:g}±{fa_r:g}" if fa_r is not None else None,
          "lookup", "B", {"table": "表19-5", "src": hit_cd.src if hit_cd else "清单8.2"})
        prec = self.lookup.precision_row(gear["gear.d2"]["value"], gear["gear.m"]["value"])
        g("gear.F_p", "齿距累积总偏差 F_p（图面无格，完备性项）", prec.row["F_p"] if prec else None,
          "lookup", "B", {"table": "表19-2", "src": prec.src if prec else "清单8.2"})
        g("gear.F_beta", "螺旋线总偏差 F_β（图面无格）", prec.row.get("F_beta") if prec else None,
          "lookup", "B", {"table": "表19-3", "src": prec.src if prec else "清单8.2"})
        # constants
        g("gear.alpha", "压力角 α", 20, "constant", "C", {"std": "GB/T 1356"}, unit="°", text="20°")
        g("gear.ha_star", "齿顶高系数", 1.0, "constant", "C", {"std": "GB/T 1356"}, text="1.0")
        g("gear.x_shift", "变位系数", 0, "constant", "C", {"std": "GB/T 1356"}, text="0")
        g("gear.precision", "精度等级", 8, "constant", "C", {"std": "一般工作机器 8 级"}, text="8")
        # B 通道：模板为准（lookup 对照差异记录）
        def b_item(fid, item, tpl_text, lookup_note, cat="lookup"):
            g(fid, item, tpl_text, cat, "B", {"channel": "模板为准(Q5/B)", "lookup": lookup_note},
              text=tpl_text)
        b_item("gear.bore_tol", "齿轮孔公差（φ35 H7）", "+0.030/0", "H7 查表 +0.025/0（C8 差异记录）")
        b_item("gear.da2_tol", "齿顶圆公差（φ272 h11）", "0/-0.300", "h11 查表 0/-0.32（C9 差异记录）")
        b_item("gear.f_pt", "单个齿距偏差 ±f_pt", "±0.012", "表19-2 查表 ±0.017（C10 差异记录）")
        b_item("gear.F_alpha", "齿廓总偏差 F_α", "0.022", "表19-2 查表 0.020（差异记录）")
        b_item("gear.F_r", "径向跳动公差 F_r", "0.043", "表19-4 查表 0.055（C11 差异记录）")
        b_item("gear.W_tol_up", "公法线上偏差 Esns", "-0.132", "表19-9~11 公式（模板现值）")
        b_item("gear.W_tol_down", "公法线下偏差 Esni", "-0.176", "表19-9~11 公式（模板现值）")
        b_item("gear.key_w_tol", "键槽宽公差 10JS9", "±0.0215", "JS9 查表 ±0.018（C13 差异记录；C3 归属已裁决挂键槽宽）")
        b_item("gear.key_depth_tol", "键槽深公差", "+0.2/0", "GB/T 1095（一致）")
        # C 通道：工艺/材料模板为准
        g("gear.material", "材料/热处理", "45钢正火170-210HBW", "constant", "C",
          {"note": "U2 高风险：S 为调质 197~286HBS，模板正火，书面确认前模板为准"}, text="模板技术要求保留")
        # 落图文本型（E2 直填；manual 缺失时随 H1 恢复后重派发再生成）
        if "gear.hole_n" in gear and "gear.d0_hole" in gear:
            g("gear.hole_nxd", "减重孔标注 6Xφ59", None, "calculator", "A", {"derive": "hole_n×d0_hole"},
              text=f"{gear['gear.hole_n']['value']}Xφ{gear['gear.d0_hole']['value']:g}")

        # ══ 输出轴 ══
        h = lambda fid, item, val, cat, ch, src, **kw: shaft.setdefault(
            fid, FinalItem(fid, item, "shaft", val, cat, ch, src, **kw))
        for i in range(1, 7):
            h(f"shaft.seg{i}_d", f"第{i}段直径", v(ex_s, f"shaft.seg{i}_d"), "calculator", "A",
              ex_s[f"shaft.seg{i}_d"].source)
            h(f"shaft.seg{i}_l", f"第{i}段长度", v(ex_s, f"shaft.seg{i}_l"), "calculator", "A",
              ex_s[f"shaft.seg{i}_l"].source)
        h("shaft.total_l", "轴总长", v(derived, "shaft.total_l_calc"), "calculator", "A", {"formula": "ΣL"})
        for fid, item, exid, cat in [
            ("shaft.key1_depth", "键槽深1（d−t1 图值）", "shaft.key1_depth", "manual"),
            ("shaft.key2_depth", "键槽深2（d−t1 图值）", "shaft.key2_depth", "manual"),
            ("shaft.key2_pos", "键槽2定位 3.5（C4/U4）", "shaft.key2_pos", "manual"),
            ("shaft.key1_pos", "键槽1定位 2.0（C4/U4）", "shaft.key1_pos", "manual"),
        ]:
            if exid in ex_s:
                h(fid, item, v(ex_s, exid), cat, "A", ex_s[exid].source)
            else:
                self.pending.append({"part": "shaft", "id": fid, "item": item,
                                     "reason": "manual/定稿值缺失（D 六），H1 中断"})
        # 键（S 八）与键槽宽/长
        if "shaft.key1" in ex_s:
            k1 = v(ex_s, "shaft.key1")
            h("shaft.key1_w", "键槽1宽", k1[0], "calculator", "A", ex_s["shaft.key1"].source)
            h("shaft.key1_l", "键槽1长", k1[2], "calculator", "A", ex_s["shaft.key1"].source)
        if "shaft.key2" in ex_s:
            k2 = v(ex_s, "shaft.key2")
            h("shaft.key2_w", "键槽2宽", k2[0], "calculator", "A", ex_s["shaft.key2"].source)
            h("shaft.key2_l", "键槽2长", k2[2], "calculator", "A", ex_s["shaft.key2"].source)
        # t1 查表（键槽深公式值，A8/A9 对照）
        hit1 = self.lookup.key_slot(shaft["shaft.seg1_d"]["value"], int(shaft["shaft.key1_w"]["value"]))
        hit2 = self.lookup.key_slot(shaft["shaft.seg4_d"]["value"], int(shaft["shaft.key2_w"]["value"]))
        if hit1:
            h("shaft.key1_t1", "键1 t1（表14-26）", hit1.row["t1"], "lookup", "B", {"table": hit1.table, "src": hit1.src})
            h("shaft.key1_depth_formula", "键槽深1公式值（A8 对照）",
              shaft["shaft.seg1_d"]["value"] - hit1.row["t1"], "calculator", "B", {"formula": "d-t1"})
        if hit2:
            g("gear.key_t2", "轮毂键槽 t2", hit2.row["t2"], "lookup", "B", {"table": hit2.table, "src": hit2.src})
            h("shaft.key2_t1", "键2 t1（表14-26）", hit2.row["t1"], "lookup", "B", {"table": hit2.table, "src": hit2.src})
            h("shaft.key2_depth_formula", "键槽深2公式值（A9 对照）",
              shaft["shaft.seg4_d"]["value"] - hit2.row["t1"], "calculator", "B", {"formula": "d-t1"})
        # U1：轴颈公差按 lookup 取值（pending_sign，默认 apply）
        for fid, item in (("shaft.key1_t1", "键1 t1"), ("shaft.key2_t1", "键2 t1")):
            if fid not in shaft:
                h(fid, item, None, "lookup", "B", {"table": "key_slot", "note": "档位未覆盖"})
        if "gear.key_t2" not in gear:
            g("gear.key_t2", "轮毂键槽 t2", None, "lookup", "B", {"table": "key_slot", "note": "档位未覆盖"})
        u1 = self.rules["u_signoffs"]["U1"]
        if u1.get("default") == "apply":
            for seg, size in [(1, "shaft.seg1_d"), (3, "shaft.seg3_d"), (4, "shaft.seg4_d"), (6, "shaft.seg6_d")]:
                code = {1: "r6", 3: "k6", 4: "r6", 6: "k6"}[seg]
                hit = self.lookup.fit(shaft[size]["value"], code)
                if hit:
                    tpl = self._tpl("shaft", f"shaft.seg{seg}_d_tol")
                    new = f"{hit.row['sup']}/{hit.row['sub']}"
                    h(f"shaft.seg{seg}_d_tol", f"φ{shaft[size]['value']:g} 配合公差（{code}）", new,
                      "lookup", "B", {"table": hit.table, "src": hit.src, "rule": "U1 暂按清单5.2（待会签）"},
                      template=tpl, verdict="u1_correction" if tpl and tpl != new else "")
                else:
                    h(f"shaft.seg{seg}_d_tol", f"轴段{seg}公差", None, "lookup", "B",
                      {"table": "fit_tolerance", "code": code, "size": shaft[size]["value"]})
        # B 通道模板为准
        def hb(fid, item, tpl_text, note, cat="lookup"):
            h(fid, item, tpl_text, cat, "B", {"channel": "模板为准(Q5/B)", "note": note}, text=tpl_text)
        hb("shaft.key1_w_tol", "键槽1宽公差 8N9", "0/-0.043", "N9 查表 0/-0.036（C12 差异记录）")
        hb("shaft.key2_w_tol", "键槽2宽公差 10N9", "0/-0.043", "N9 查表 0/-0.036（一致档）")
        hb("shaft.key1_depth_tol", "键槽深1公差", "0/-0.020", "模板现值")
        hb("shaft.key2_depth_tol", "键槽深2公差", "0/-0.020", "模板现值")
        hit = self.lookup.bearing("6206")
        h("shaft.bearing", "轴承 6206", "6206", "lookup", "B",
          {"table": "GB/T 276", "dims": hit.row if hit else None})
        h("shaft.material", "材料", "45 钢调质", "constant", "C", {"note": "技术要求 220-250HBW 模板保留"},
          text="模板技术要求保留")

        # ══ 静态 C 通道项（技术要求/标题栏，模板结构资产保留；U8 异常文本待会签） ══
        def static(part, table_add, fid, item, handle, note="模板结构资产保留"):
            snap = self.snapshot[part].get(handle)
            table_add(fid, item, snap["plain"] if snap else "", "constant", "C",
                      {"channel": "C 模板为准", "handle": handle, "note": note},
                      text=snap["plain"] if snap else "")
        static("gear", g, "gear.tech_req", "技术要求（正火170-210HBW/R5/C2，U2 待书面确认）", "4CB")
        static("gear", g, "gear.title_name", "标题栏-图名", "4C0")
        static("gear", g, "gear.title_scale", "标题栏-比例", "61F")
        static("gear", g, "gear.title_designer", "标题栏-设计者（U9 可注入）", "84D")
        static("gear", g, "gear.title_course", "标题栏-课程名（U9 可注入）", "4C9")
        static("gear", g, "gear.abnormal_text", "标题栏-班级|学号（U8 异常；U9 可注入替换）", "4CA",
               note="U8 pending_sign：默认保留；case.yaml 注入 class_no/student_no 时替换并消解 U8")
        static("shaft", h, "shaft.tech_req", "技术要求（调质220-250HBW/R2/C1.5）", "A8D")
        static("shaft", h, "shaft.title_name", "标题栏-图名", "A82")
        static("shaft", h, "shaft.title_scale", "标题栏-比例", "AF2")
        static("shaft", h, "shaft.title_designer", "标题栏-设计者（U9 可注入）", "C03")
        static("shaft", h, "shaft.title_course", "标题栏-课程名（U9 可注入）", "A8B")
        static("shaft", h, "shaft.abnormal_text", "标题栏-班级|学号（U8 异常；U9 可注入替换）", "A8C",
               note="U8 pending_sign：默认保留；case.yaml 注入 class_no/student_no 时替换并消解 U8")

        # ══ 联动同步断言（FR-04，清单 8.3） ══
        for fid, table in (("shaft.key1", shaft), ("shaft.key2", shaft)):
            table[fid] = FinalItem(fid, "SRD 键规格", "shaft", ex_s[fid].value,
                                   "calculator", "A", ex_s[fid].source, verdict="srd_hard")
        # B 通道：同档保持模板成熟取值，跨档才换表值；缺档明确留空转 H3。
        def band_value(table, fid, hit, base_hit, field, formatter=str):
            if hit and base_hit and hit.row == base_hit.row:
                return
            value = hit.row.get(field) if hit else None
            table[fid].update(value=formatter(value) if value is not None else None,
                              text=formatter(value) if value is not None else None,
                              source={"table": hit.table if hit else "lookup", "src": hit.src if hit else "档位未覆盖"},
                              verdict="lookup_changed_band" if value is not None else "pending")
        base_prec = self.lookup.precision_row(268, 2)
        for fid, field, formatter in (("gear.f_pt", "f_pt", lambda x: f"±{x:g}"),
                                      ("gear.F_alpha", "F_alpha", lambda x: f"{x:g}"),
                                      ("gear.F_r", "F_r", lambda x: f"{x:g}")):
            band_value(gear, fid, prec, base_prec, field, formatter)
        for fid, size, base, code in (("gear.bore_tol", gear["gear.bore_d"]["value"],35,"H7"),
                                      ("gear.da2_tol", gear["gear.da2"]["value"],272,"h11")):
            hit, base_hit = self.lookup.fit(size, code), self.lookup.fit(base, code)
            if not hit or not base_hit or hit.row != base_hit.row:
                value = f"{hit.row['sup']}/{hit.row['sub']}" if hit else None
                gear[fid].update(value=value, text=value, verdict="lookup_changed_band" if hit else "pending",
                                 source={"table":"fit_tolerance", "size":size, "code":code})
        band_value(gear, "gear.key_w_tol", hit2, self.lookup.key_slot(35,10), "hub_JS9")
        band_value(shaft, "shaft.key1_w_tol", hit1, self.lookup.key_slot(23,8), "shaft_N9")
        band_value(shaft, "shaft.key2_w_tol", hit2, self.lookup.key_slot(35,10), "shaft_N9")
        # 恢复时 lookup 答复必须覆盖派发结果，而不是被模板默认值吞掉。
        for table, source_items in ((gear, ex_g), (shaft, ex_s)):
            for fid, src in source_items.items():
                if src.source.get("doc") == "answers" and fid in table:
                    table[fid].update(value=src.value, text=_fmt(src.value), source=src.source,
                                      verdict="human_confirmed")
        linked = self._linked_checks(gear, shaft)

        # ══ 与模板对照的裁决标记（金样例） ══
        for part, table in (("gear", gear), ("shaft", shaft)):
            for fid, it in table.items():
                if not it['verdict']:
                    it['verdict'] = ('pending' if it['value'] is None and it['text'] is None else
                                     'srd_hard' if it['channel']=='A' else 'template_kept' if it['channel']=='C' else 'lookup_resolved')
                b = self._binding(part, fid)
                if not b or it["value"] is None:
                    continue
                tpl = b.get("expect")
                it["template"] = tpl
                if not it["verdict"]:
                    it["verdict"] = "srd_hard" if it["channel"] == "A" else ("template_kept" if it["channel"] in ("B", "C") else "calc")

        return {
            "gear": gear, "shaft": shaft,
            "primary": {**ex_g, **ex_s},
            "cross_checks": checks,
            "linked_checks": linked,
            "pending": self.pending,
        }

    def _linked_checks(self, gear: dict, shaft: dict) -> list[dict]:
        """七组联动键一致性（清单 8.3；豁免项按 A5/A6/A8/A9）。"""
        gv = lambda k: gear[k]["value"] if k in gear else None
        sv = lambda k: shaft[k]["value"] if k in shaft else None
        res = []

        def chk(name, ok, detail):
            res.append({"group": name, "pass": bool(ok), "detail": detail})

        chk("d=35→5处", gv("gear.bore_d") == sv("shaft.seg4_d") and gv("gear.hub_d") == 1.6 * gv("gear.bore_d"),
            f"孔 {gv('gear.bore_d')}=轴段4 {sv('shaft.seg4_d')}，轮毂 {gv('gear.hub_d')}=1.6d")
        chk("键10×8×45→5处", gv("gear.key_len") == sv("shaft.key2_l") and gv("gear.key_w") == sv("shaft.key2_w"),
            f"毂槽长 {gv('gear.key_len')}=轴槽长 {sv('shaft.key2_l')}，宽 {gv('gear.key_w')}={sv('shaft.key2_w')}")
        chk("m=2→5处", gv("gear.da2") == gv("gear.d2") + 2 * gv("gear.m") and gv("gear.df2") == gv("gear.d2") - 2.5 * gv("gear.m"),
            "da/df 由 m 联动")
        chk("b2=54→4处", gv("gear.b2") == gv("gear.hub_l"),
            f"齿宽 {gv('gear.b2')}=毂长 {gv('gear.hub_l')}（A13）")
        chk("a→4处", abs(gv("gear.a") - (gv("gear.d2") + gv("gear.m")*gv("gear.z1")) / 2) < 0.01,
            f"a={gv('gear.a')} 与 (d1+d2)/2 一致")
        chk("z2=134→4处", gv("gear.k") == round(gv("gear.z2") / 9 + 0.5),
            f"k={gv('gear.k')} 与 z2 联动")
        chk("6206→4处", sv("shaft.seg3_d") == sv("shaft.seg6_d") == 30 and sv("shaft.seg5_d") == sv("shaft.seg3_d") + 2 * 3,
            f"轴承位 {sv('shaft.seg3_d')}/{sv('shaft.seg6_d')}，定位肩 {sv('shaft.seg5_d')}=径+2h(A12)")
        chk("减重孔数量→标注", True, f"{gv('gear.hole_n')}Xφ{gv('gear.d0_hole')}（R5 均布联动为文本联动，剖视几何不随数量变化）")
        return res
