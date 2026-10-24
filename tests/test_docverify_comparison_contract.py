"""Purpose-aware comparison contract. Executable with unittest, without the project gate."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web.services.docverify.pair import engine, contradiction
from web.services.docverify import pair_review as pr, pair_cases as pc, pair_report
from web.services.docverify import settings_store as settings

CFG = {'exit': {'max_open': {'critical': 0, 'major': None, 'minor': None}, 'changed_rule': 'same'},
       'types': {}, 'labels': {'critical': '重大', 'major': '警告', 'minor': '提案'}}


class ComparisonContract(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'WEBSPEC2DOC_DOCVERIFY_SEMANTIC': 'off'})
        self.env.start()
        self.cfg = patch.object(settings, 'effective', return_value=CFG)
        self.cfg.start()

    def tearDown(self):
        self.cfg.stop()
        self.env.stop()

    def test_ai_none_is_out_of_scope_and_passes(self):
        cfg = {**CFG, 'ai': {'provider': 'none'}}
        with patch.object(settings, 'effective', return_value=cfg):
            result = engine.inspect('検索の応答は30秒以内。', '検索の応答は30秒以内。', 'legacy_requirement_design')
            a = result['assessment']
            self.assertEqual({'ai': 'out_of_scope'}, a['scope'])
            self.assertFalse([e for e in result['errors'] if e['detector'].startswith('semantic')])
            o = pr._judge([], [], assessment={**a, 'status': 'complete', 'baseline_units': 1, 'target_units': 1, 'compared_pairs': 1, 'reasons': []})
        self.assertEqual('合格', o['verdict'])
        self.assertIn('AI 検査は設定により範囲外（ルール検査のみで判定）', pr._reasons(o))

    def test_ai_configured_failure_is_unverified(self):
        cfg = {**CFG, 'ai': {'provider': 'openai'}}
        env = {k: v for k, v in os.environ.items() if k != 'WEBSPEC2DOC_DOCVERIFY_SEMANTIC'}
        with patch.object(settings, 'effective', return_value=cfg), patch.dict(os.environ, env, clear=True), \
                patch.object(engine.semantic, 'available', return_value=True), \
                patch.object(engine.semantic, 'extra', side_effect=RuntimeError('api down')):
            result = engine.inspect('検索の応答は30秒以内。', '検索の応答は30秒以内。', 'legacy_requirement_design')
        self.assertEqual('unverified', result['assessment']['status'])
        self.assertEqual({}, result['assessment']['scope'])
        self.assertEqual('判定不能', pr._judge([], [], assessment=result['assessment'])['verdict'])

    def test_api_specifications_need_no_req_ids(self):
        result = engine.inspect('# API\n## 検索\n- API-001 検索の応答は30秒以内。', '# API\n## 検索\n- API-001 検索の応答は60秒以内。', 'consistency')
        self.assertIn('CONTRADICTION', [d['type'] for d in result['defects']])
        self.assertEqual('complete', result['assessment']['status'])

    def test_plain_text_can_be_compared_and_clear(self):
        result = engine.inspect('検索の応答は30秒以内。', '検索の応答は30秒以内。', 'consistency')
        self.assertEqual('complete', result['assessment']['status'])
        self.assertEqual([], result['defects'])
        self.assertEqual('合格', pr._judge([], [], assessment=result['assessment'])['verdict'])

    def test_empty_and_unrelated_are_unknown(self):
        for a, b in [('# 空', '# 空'), ('パスワードは8文字。', '出荷は3日以内。')]:
            result = engine.inspect(a, b, 'consistency')
            self.assertEqual('unverified', result['assessment']['status'])
            verdict = pr._judge([], [], assessment=result['assessment'])
            self.assertFalse(verdict['pass'])
            self.assertEqual('判定不能', verdict['verdict'])

    def test_detector_failure_blocks_pass(self):
        with patch.object(contradiction, 'detect', side_effect=ValueError('probe')):
            result = engine.inspect('検索の応答は30秒以内。', '検索の応答は30秒以内。', 'consistency')
        self.assertTrue(result['errors'])
        self.assertEqual('判定不能', pr._judge([], [], assessment=result['assessment'])['verdict'])

    def test_legacy_without_assessment_blocks_pass(self):
        self.assertEqual('判定不能', pr._judge([], [])['verdict'])

    def test_document_edits_invalidate_assessment_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            meta = pr._write_docs(folder, '検索の応答は30秒以内。', '検索の応答は30秒以内。', None, None)
            result = engine.inspect('検索の応答は30秒以内。', '検索の応答は30秒以内。', 'consistency')
            pr._write(folder/'docs/meta.json', {**meta, 'purpose':'consistency', 'name':'契約確認', 'baseline_name':'契約.md', 'target_name':'実装仕様.md', 'assessment':result['assessment']})
            pr._write(folder/'findings.json', [])
            with patch.object(pr, '_existing', return_value=folder):
                self.assertEqual('合格', pr.gate('probe')['overall']['verdict'])
                (folder/'docs/design.md').write_text('検索の応答は60秒以内。')
                gate = pr.gate('probe')
                self.assertEqual('判定不能', gate['overall']['verdict'])
                text = pc.report_md('probe')
                self.assertIn('契約.md', text)
                self.assertIn('実装仕様.md', text)
                self.assertIn('判定不能', text)
                self.assertIn('検査後に変更', text)

    def test_unknown_purpose_and_role_are_rejected(self):
        for opts in ({'purpose':'anything'}, {'purpose':'consistency', 'baseline_role':'unknown'}):
            with self.assertRaises(pr.PairError):
                pc.create('probe',b'a',b'b','', '_seed', **opts)


if __name__ == '__main__':
    unittest.main()
