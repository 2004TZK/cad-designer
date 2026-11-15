"""代码审查回归：真实 DXF、故障注入、恢复和双引擎；产物仅写临时目录。"""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import ezdxf
from cad_agent import config
from cad_agent.core.runner import run_case, _load_assets, convert_case
from cad_agent.core.lookup import LookupEngine
from cad_agent.core.calculator import derive
from cad_agent.core.dispatcher import Dispatcher
from cad_agent.core.checks import run_assertions
from cad_agent.core.geometry import shift_shaft
from cad_agent.mcp.editor import Editor, EditorError
from cad_agent.parsers.docs_parser import parse_case
from cad_agent.qa.quality import regress, freeze_baseline, quality
from cad_agent.qa.snapshot import drawing_snapshot, snapshot_diff


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='review_',dir=config.ROOT/'_tmp_render')
        cls.root=Path(cls.tmp.name)
        cls.original_input=config.INPUT_DIR
        shutil.copytree(config.INPUT_DIR,cls.root/'input')
        cls.paths=patch.multiple(config,INPUT_DIR=cls.root/'input',
            OUTPUT_DIR=cls.root/'output',RUNS_DIR=cls.root/'output/runs')
        cls.paths.start()
        cls.env=patch.dict(os.environ,{'CAD_AGENT_DXF_ONLY':'1','CAD_AGENT_LLM_MOCK':'0'})
        cls.env.start()
        cls.assets=_load_assets()
        cls.gold=run_case(config.GOLD_CASE,no_llm=True)
        if cls.gold['stage']!='DONE':
            raise AssertionError(cls.gold)
        cls.baseline=cls.root/'baseline'
        freeze_baseline(config.GOLD_CASE,config.RUNS_DIR,cls.baseline)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop(); cls.paths.stop(); cls.tmp.cleanup()

    def clone(self,name,source=None):
        dst=config.INPUT_DIR/name
        shutil.copytree(self.original_input/(source or config.GOLD_CASE),dst)
        return dst

    def dispatch(self):
        extracted=parse_case(config.INPUT_DIR/config.GOLD_CASE)
        primary={i.id:i for p in ('gear','shaft') for i in extracted[p]}
        derived,checks=derive(primary,self.assets['constants'])
        return Dispatcher(self.assets['template_assets'],LookupEngine(self.assets['lookup_tables']),
                          self.assets['verdict_rules']).dispatch(extracted,derived,checks)

    def test_gold_and_concrete_exemptions(self):
        data=self.dispatch()
        rows,ok=run_assertions(data,self.assets['assertions'])
        self.assertTrue(ok)
        self.assertEqual({r['id'] for r in rows if r['status']=='exempt'},{'A5','A6','A8','A9'})
        self.assertTrue(all(self.gold['acceptance']['delivery_verify'].values()))

    def test_new_deviation_not_blanket_exempt(self):
        data=self.dispatch(); data['gear']['gear.d0_hole']['value']=500
        rows,ok=run_assertions(data,self.assets['assertions'])
        self.assertFalse(ok)
        self.assertEqual(next(r['status'] for r in rows if r['id']=='A5'),'fail')

    def test_dynamic_W_and_key_lengths(self):
        data=self.dispatch(); data['gear']['gear.W']['value']=90
        rows,ok=run_assertions(data,self.assets['assertions'])
        self.assertFalse(ok)
        import math
        from cad_agent.core.calculator import inv_alpha
        data=self.dispatch()
        data['gear']['gear.m']['value']=2.5
        data['gear']['gear.W']['value']=round(2.5*math.cos(math.radians(20))*(math.pi*14.5+134*inv_alpha(20)),2)
        rows,_=run_assertions(data,self.assets['assertions'])
        self.assertEqual(next(r['status'] for r in rows if r['id']=='A15'),'pass')
        data=self.dispatch(); data['shaft']['shaft.key1']['value']=(8,7,48)
        data['shaft']['shaft.key1_l']['value']=48
        rows,ok=run_assertions(data,self.assets['assertions'])
        self.assertEqual(next(r['status'] for r in rows if r['id']=='A10'),'pass')

    def test_lookup_all_indices_and_fractional_center_distance(self):
        lookup=LookupEngine(self.assets['lookup_tables'])
        self.assertIsNone(lookup.precision_row(268,4))
        self.assertIsNone(lookup.center_distance_tol(161,'5'))
        self.assertIsNotNone(lookup.precision_row(280,2.5))

    def test_cross_source_mismatch_blocks(self):
        case=self.clone('cross_source')
        p=case/config.D_FILE
        import re
        s,count=re.subn(r'(大齿轮分度圆\s+d2\s*=\s*)268',r'\g<1>269',p.read_text(encoding='utf-8'))
        self.assertEqual(count,1)
        p.write_text(s,encoding='utf-8')
        r=run_case('cross_source',no_llm=True)
        self.assertEqual(r['stage'],'BLOCKED',r)
        self.assertTrue(any(x['id']=='SRD:gear.d2' for x in r['assertions_fail']))

    def test_resume_accumulates_answers_and_archives_them(self):
        case=self.clone('partial','case003pending')
        p=case/config.D_FILE
        s=p.read_text(encoding='utf-8')
        import re
        s=re.sub(r'^.*减重孔数量.*$', '',s,flags=re.M)
        p.write_text(s,encoding='utf-8')
        r=run_case('partial',no_llm=True)
        self.assertEqual(r['stage'],'PENDING',r)
        r=run_case('partial',answers={'gear.d0_hole':59},no_llm=True)
        self.assertEqual(r['stage'],'PENDING',r)
        r=run_case('partial',answers={'gear.hole_n':6},no_llm=True)
        self.assertEqual(r['stage'],'DONE',r)
        raw=json.loads((config.RUNS_DIR/'partial/extracted/gear.json').read_text(encoding='utf-8'))
        self.assertEqual(next(i for i in raw if i['id']=='gear.d0_hole')['source']['doc'],'answers')

    def test_resume_rejects_changed_input(self):
        case=self.clone('changed','case003pending')
        run_case('changed',no_llm=True)
        p=case/config.D_FILE; p.write_text(p.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        r=run_case('changed',answers={'gear.d0_hole':59})
        self.assertEqual(r['point'],'INPUT_CHANGED')

    def test_variant_inline_mcp_equivalence(self):
        self.clone('variant_inline','case002变体'); self.clone('variant_mcp','case002变体')
        answers={'deviations':{'A5':{'expect':49,'actual':52,'reason':'测试用例指定变体值'}}}
        for name,engine in (('variant_inline','inline'),('variant_mcp','mcp')):
            r=run_case(name,answers=answers,no_llm=True,engine=engine)
            self.assertEqual(r['stage'],'DONE',r)
        for part in ('gear','shaft'):
            a=ezdxf.readfile(str(config.RUNS_DIR/'variant_inline/work'/f'{part}_final.dxf'))
            b=ezdxf.readfile(str(config.RUNS_DIR/'variant_mcp/work'/f'{part}_final.dxf'))
            self.assertFalse(snapshot_diff(drawing_snapshot(a),drawing_snapshot(b)))
            handle='4CA' if part=='gear' else 'A8C'
            self.assertEqual(a.entitydb[handle].plain_text(),'飞制2401|2024010101')
        gear=ezdxf.readfile(str(config.RUNS_DIR/'variant_inline/work/gear_final.dxf'))
        tpl=ezdxf.readfile(str(config.TEMPLATE_GEAR))
        # 上下孔边必须镜像，不能一起向同方向平移。
        group=self.assets['template_assets']['geo_groups']['gear']['groups']['GG-2']['entities']
        ys=[gear.entitydb[h].dxf.start.y for h,r in group.items() if r=='hole_edge']
        self.assertAlmostEqual(sum(ys)/len(ys),148.5,places=5)

    def test_geometry_mutation_detected_without_count_change(self):
        name='tampered'; self.clone(name)
        self.assertEqual(run_case(name,no_llm=True)['stage'],'DONE')
        freeze_baseline(name,config.RUNS_DIR,self.baseline)
        f=config.RUNS_DIR/name/'work/gear_final.dxf'
        doc=ezdxf.readfile(str(f)); line=next(iter(doc.modelspace().query('LINE')))
        line.dxf.start=(line.dxf.start.x+2,line.dxf.start.y,0); doc.saveas(str(f))
        self.assertFalse(regress(name,config.RUNS_DIR,self.baseline)['pass'])

    def test_acceptance_failure_never_done(self):
        self.clone('bad_quality')
        from cad_agent.core import runner
        original=runner.quality
        def fail(*args,**kwargs):
            result=original(*args,**kwargs); result.update(score=80,pass_=False)
            result['pass']=False
            return result
        with patch.object(runner,'quality',side_effect=fail):
            r=run_case('bad_quality',no_llm=True)
        self.assertEqual(r['stage'],'BLOCKED')
        self.assertEqual(r['point'],'P8')

    def test_multi_segment_mapping_and_hatch(self):
        doc=ezdxf.new(); ms=doc.modelspace()
        line=ms.add_line((10,10),(30,10))
        hatch=ms.add_hatch(); hatch.paths.add_polyline_path([(10,0),(30,0),(30,5),(10,5)])
        op={'old_bounds':[0,10,20,30],'new_bounds':[0,12,21,35],
            'entities':[line.dxf.handle,hatch.dxf.handle]}
        shift_shaft(doc,op)
        self.assertEqual((line.dxf.start.x,line.dxf.end.x),(12,35))
        self.assertEqual([v[0] for v in hatch.paths[0].vertices],[12,35,35,12])

    def test_atomic_text_batch_and_repeated_tokens(self):
        ed=Editor(self.root/'atomic')
        ed.apply_geo('gear',[])
        working=ed.work/'gear_working.dxf'; before=working.read_bytes()
        with self.assertRaises(EditorError):
            ed.apply_text('gear',[{'handle':'139','old_plain':'6Xφ59','new_plain':'4Xφ52'},
                                  {'handle':'NO_HANDLE','old_plain':'0','new_plain':'1'}])
        self.assertEqual(before,working.read_bytes())
        self.assertFalse((ed.work/'gear_final.dxf').exists())
        self.assertEqual(Editor._patch_dim_raw('10{\\S+10^ 10;}','10+10/10','20+20/20'), '20{\\S+20^ 20;}')

    def test_h4_can_resume(self):
        case=self.clone('large_move')
        p=case/config.S_FILE; s=p.read_text(encoding='utf-8').replace('35×52','35×82')
        p.write_text(s,encoding='utf-8')
        r=run_case('large_move',no_llm=True)
        self.assertEqual((r['stage'],r['point']),('PENDING','H4'),r)
        digest=r['pending'][0]['plan_digest']
        r=run_case('large_move',answers={'geometry':{'allow_large_moves':True,'plan_digest':digest}})
        self.assertEqual(r['stage'],'DONE',r)

    def test_convert_only_preserves_frozen_dxf(self):
        self.clone('convert_only')
        r=run_case('convert_only',no_llm=True)
        self.assertEqual(r['stage'],'DONE')
        f=config.RUNS_DIR/'convert_only/work/gear_final.dxf'; old=f.read_bytes()
        r=convert_case('convert_only')
        self.assertEqual(r['stage'],'DONE'); self.assertEqual(f.read_bytes(),old)
        self.assertTrue((config.RUNS_DIR/'convert_only/大齿轮.dxf').exists())

    def test_missing_baseline_structured_failure(self):
        self.assertFalse(regress('missing',config.RUNS_DIR,self.baseline)['pass'])

    def test_unimplemented_geometry_is_explicit(self):
        self.clone('unsupported')
        # 仅变轴径且不影响轴承/键联动，过去会只改文字直接 DONE。
        p=config.INPUT_DIR/'unsupported'/config.S_FILE
        p.write_text(p.read_text(encoding='utf-8').replace('28×50','29×50'),encoding='utf-8')
        r=run_case('unsupported',no_llm=True)
        self.assertEqual((r['stage'],r['point']),('BLOCKED','GEOMETRY_UNSUPPORTED'),r)

    def test_h3_lookup_answer_is_used(self):
        self.clone('lookup_answer')
        tables=copy.deepcopy(self.assets['lookup_tables'])
        tables['center_distance_tol']['rows']=[]
        assets={**self.assets,'lookup_tables':tables}
        with patch('cad_agent.core.runner._load_assets',return_value=assets), patch(
            'cad_agent.core.runner.Retriever.query',return_value={'state':'miss','hits':[],'top_score':0}):
            r=run_case('lookup_answer',no_llm=True)
            self.assertEqual((r['stage'],r['point']),('PENDING','H3'))
            r=run_case('lookup_answer',answers={'gear.a_tol_text':'161±0.032'},no_llm=True)
            self.assertEqual(r['stage'],'DONE',r)

    def test_rag_zero_threshold_and_model_failure(self):
        from cad_agent.rag.retriever import Retriever
        r=Retriever(); r._chunks=[{'chunk_id':'1','text':'齿轮'}]
        with patch.object(r,'vector_ready',return_value=False):
            self.assertEqual(r.query('齿轮',tau=0)['tau'],0)
            self.assertEqual(r.query('齿轮',tau=0)['state'],'hit')
        r=Retriever(); r._chunks=[{'chunk_id':'1','text':'齿轮'}]
        with patch.object(r,'vector_ready',side_effect=lambda:not r._vector_failed),patch.object(r,'_ensure_emb',side_effect=RuntimeError('model failure')):
            self.assertEqual(r.query('齿轮')['backend'],'lexical_fallback')

    def test_invalid_llm_response_disables_assist(self):
        from cad_agent.llm.advisor import LlmClient
        with patch.dict(os.environ,{'CAD_AGENT_LLM_MOCK':'1'}):
            client=LlmClient()
        with patch.object(client,'_call',return_value='invalid json'):
            self.assertIsNone(client.structure_hit('原文')['structured'])
            self.assertFalse(client.enabled)

    def test_build_preserves_signed_rows(self):
        from cad_agent.builder.rules_compiler import compile_all
        from cad_agent.builder.signoff import apply_signoff,show_pending
        root=self.root/'rules'; root.mkdir()
        for name in ('verdict_rules.json','lookup_tables.json','layout_rules.json'):
            shutil.copyfile(config.ASSETS_DIR/name,root/name)
        apply_signoff({'HB1':{'U0':'accept'},'HB2':{'key_slot':True}},by='test',assets_dir=root)
        compile_all(root)
        rules=json.loads((root/'verdict_rules.json').read_text(encoding='utf-8'))
        self.assertEqual(rules['u_signoffs']['U0']['status'],'signed')
        lookup=json.loads((root/'lookup_tables.json').read_text(encoding='utf-8'))
        self.assertTrue(lookup['key_slot']['rows'][0]['row_signed'])
        # 临时会签目录不能污染下一次默认读取。
        self.assertIn('u_signoffs',show_pending())

    def test_u7_failure_is_hard_gate(self):
        from cad_agent.builder.asset_extractor import validate_assets
        assets=copy.deepcopy(self.assets['template_assets']); assets['binding_verification_problems']=['missing handle']
        with self.assertRaises(ValueError):
            validate_assets(assets)

    def test_dxf_delivery_readback_failure(self):
        from cad_agent.mcp.converter import Converter
        result=Converter.verify(config.TEMPLATE_GEAR,{'mode':'dxf_only','path':str(self.root/'missing.dxf')})
        self.assertFalse(result['pass'])

    def test_regress_command_replays_no_llm(self):
        from cad_agent.cli import cmd_regress
        import argparse
        with patch('cad_agent.core.runner.run_case',return_value={'stage':'DONE'}) as run, patch(
            'cad_agent.qa.quality.regress',return_value={'pass':True,'parts':{}}):
            cmd_regress(argparse.Namespace(case=config.GOLD_CASE,no_llm=True,engine='inline'))
            run.assert_called_once_with(config.GOLD_CASE,engine='inline',no_llm=True)


if __name__=='__main__':
    unittest.main(verbosity=2)
