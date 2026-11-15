"""跨算例尺寸链检查；豁免绑定具体公式值和图值。"""
import math
from .calculator import inv_alpha


def _close(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a,b))
    if isinstance(a, (int,float)) and isinstance(b, (int,float)):
        return math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-9,abs_tol=.011)
    return a is not None and a == b


def run_assertions(data, assertions, decisions=None):
    gv = lambda k: data['gear'].get('gear.'+k, {}).get('value')
    sv = lambda k: data['shaft'].get('shaft.'+k, {}).get('value')
    # 兼容旧资产格式，但绝不按 assertion ID 无条件放行其他偏差。
    known = {'A5': (49,59), 'A6': (38.3,39), 'A8': (19,19.5), 'A9': (30,31)}
    exemptions = {e['assertion']:e for e in assertions.get('exemptions', [])}
    decisions = decisions or {}
    rows = []

    def rec(aid, expected, actual, note=''):
        status = 'pass' if _close(expected,actual) else 'fail'
        ex = exemptions.get(aid)
        if status == 'fail' and ex:
            pair = (ex.get('expected'), ex.get('actual')) if 'expected' in ex else known.get(aid)
            if pair and _close(expected,pair[0]) and _close(actual,pair[1]):
                status, note = 'exempt', ex['reason']
        decision = decisions.get(aid, {})
        if (status == 'fail' and isinstance(decision,dict) and decision.get('reason')
                and _close(expected,decision.get('expect')) and _close(actual,decision.get('actual'))):
            status, note = 'exempt', '人工裁决：'+decision['reason']
        rows.append(dict(id=aid,status=status,expect=expected,actual=actual,note=note))

    def check(aid, expected, actual):
        try:
            rec(aid, expected(), actual())
        except (TypeError, ValueError, KeyError, ZeroDivisionError):
            rows.append(dict(id=aid,status='fail',expect='完整有效的公式输入',actual=None,note='缺失或无效输入'))

    check('A1', lambda:gv('d2')+2*gv('m'), lambda:gv('da2'))
    check('A2', lambda:gv('d2')-2.5*gv('m'), lambda:gv('df2'))
    check('A3', lambda:gv('da2')-2*gv('delta0'), lambda:gv('rim_inner'))
    check('A4', lambda:(gv('rim_inner')+gv('hub_d'))/2, lambda:gv('d0_circle'))
    check('A5', lambda:(gv('rim_inner')-gv('hub_d'))/4, lambda:gv('d0_hole'))
    check('A6', lambda:gv('bore_d')+gv('key_t2'), lambda:gv('key_depth'))
    check('A7', lambda:sum(sv(f'seg{i}_l') for i in range(1,7)), lambda:sv('total_l'))
    check('A8', lambda:sv('seg1_d')-sv('key1_t1'), lambda:sv('key1_depth'))
    check('A9', lambda:sv('seg4_d')-sv('key2_t1'), lambda:sv('key2_depth'))
    check('A10', lambda:[sv('key1')[2],sv('key2')[2]], lambda:[sv('key1_l'),sv('key2_l')])
    check('A11', lambda:[data['shaft']['shaft.bearing']['source']['dims']['d']]*2,
          lambda:[sv('seg3_d'),sv('seg6_d')])
    # V1 固定 6206 和定位肩高3的结构约束；改变结构另列能力检查。
    check('A12', lambda:sv('seg3_d')+2*3, lambda:sv('seg5_d'))
    check('A13', lambda:gv('b2'), lambda:gv('hub_l'))
    check('A14', lambda:round(gv('z2')/9+.5), lambda:gv('k'))
    check('A15', lambda:round(gv('m')*math.cos(math.radians(gv('alpha')))*(
        math.pi*(gv('k')-.5)+gv('z2')*inv_alpha(gv('alpha'))),2), lambda:gv('W'))
    for check_row in data.get('cross_checks',[]):
        if isinstance(check_row,dict):
            rec('SRD:'+check_row['id'],check_row['expect'],check_row['actual'],'SRD 与公式交叉验证')
    for link in data.get('linked_checks',[]):
        # 联动本身不得豁免，修正输入后重新计算。
        rows.append(dict(id='LINK:'+link['group'], status='pass' if link['pass'] else 'fail',
                         expect=True, actual=link['pass'], note=link['detail']))
    return rows, all(r['status'] != 'fail' for r in rows)
