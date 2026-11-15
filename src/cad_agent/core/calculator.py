"""SRD 主参数派生和独立来源交叉验证。"""
from __future__ import annotations

import math
from ..parsers.docs_parser import Item


def inv_alpha(alpha_deg: float) -> float:
    a = math.radians(alpha_deg)
    return math.tan(a) - a


def derive(primary: dict[str, Item], constants: dict) -> tuple[dict[str, Item], list[dict]]:
    g = lambda key: primary[key].value if key in primary else None
    out, checks = {}, []

    def put(key, value, formula, unit="mm"):
        out[key] = Item(key, key, value, unit, category="calculator",
                        source={"formula": formula}, channel_hint="A")

    def check(key, expected, tol=0.011):
        actual = g(key)
        if actual is not None:
            checks.append({"id": key, "actual": actual, "expect": expected,
                           "pass": math.isclose(actual, expected, rel_tol=1e-9, abs_tol=tol),
                           "source": primary[key].source})

    m, z1, z2 = g("gear.m"), g("gear.z1"), g("gear.z2")
    alpha = g("gear.alpha") if g("gear.alpha") is not None else constants["alpha_deg"]
    if m is not None and z1 is not None and z2 is not None:
        d1, d2 = m * z1, m * z2
        for key, value, formula in (
            ("gear.d1", d1, "m*z1"), ("gear.d2_calc", d2, "m*z2"),
            ("gear.da2_calc", d2 + 2*m, "d2+2m"),
            ("gear.df2_calc", d2 - 2.5*m, "d2-2.5m"),
            ("gear.a_calc", (d1+d2)/2, "(d1+d2)/2"),
        ):
            put(key, value, formula)
        for key, value in (("gear.d1", d1), ("gear.d2", d2), ("gear.da2", d2+2*m),
                           ("gear.df2", d2-2.5*m), ("gear.a", (d1+d2)/2)):
            check(key, value)
        k = int(round(z2/9 + .5))
        W = round(m*math.cos(math.radians(alpha))*(math.pi*(k-.5)+z2*inv_alpha(alpha)), 2)
        put("gear.k_calc", k, "round(z2/9+0.5)", "齿")
        put("gear.W_calc", W, "m*cos(alpha)*(pi*(k-0.5)+z2*inv(alpha))")
        check("gear.k", k)
        check("gear.W", W)
        rng = g("gear.delta0_range")
        delta = max(rng) if isinstance(rng, (list, tuple)) and rng else None
        if delta is None and g("gear.rim_inner") is not None:
            delta = (d2+2*m-g("gear.rim_inner"))/2
        if delta is not None:
            put("gear.delta0", delta, "D四范围上限；缺省时由定稿轮缘内径反算")
            put("gear.rim_inner_calc", d2+2*m-2*delta, "da2-2*delta0")
    if g("gear.d_bore") is not None:
        hub = round(1.6*g("gear.d_bore"), 8)
        put("gear.hub_d_calc", hub, "1.6*d")
        check("gear.hub_d", hub)
        rim = g("gear.rim_inner")
        if rim is None and "gear.rim_inner_calc" in out:
            rim = out["gear.rim_inner_calc"].value
        if rim is not None:
            put("gear.d0_circle_calc", (rim+hub)/2, "(rim_inner+hub_d)/2")
            put("gear.d0_hole_formula", (rim-hub)/4, "(rim_inner-hub_d)/4")
            check("gear.d0_circle", (rim+hub)/2)
    lengths = [g(f"shaft.seg{i}_l") for i in range(1,7)]
    if all(v is not None for v in lengths):
        put("shaft.total_l_calc", round(sum(lengths), 8), "sum(seg_l)")
    if g("shaft.d_min") is not None:
        put("shaft.seg1_d_calc", g("shaft.d_min")*1.05, "d_min*1.05")
    return out, checks
