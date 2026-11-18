"""Real offline loop -> scorer regressions; no provider calls or historical re-score."""
import unittest
import test_bounded_protocol as fixtures
from locagent_service.offline import offline_engine
from locagent_service.evaluate import summarize, valid_finish

def setUpModule():
    global guard
    guard = offline_engine()
    guard.__enter__()

def tearDownModule():
    guard.__exit__(None, None, None)

class FinishCompatibilityTests(unittest.TestCase):
    setUp = fixtures.BoundedProtocolTests.setUp
    response = fixtures.BoundedProtocolTests.response
    run_steps = fixtures.BoundedProtocolTests.run_steps
    finish = fixtures.BoundedProtocolTests.finish

    def score(self, result, mode='live'):
        # "live" selects arithmetic only; every response above is a local fixture.
        row = {'source_id':'s','suppress_repeats':False,'mode':mode,
               'status':'completed','result':result}
        plan = {'sources':['s'],'arms':[False]}
        answers = {'s':{'files':['src/demo.py'],'entities':[self.entity]}}
        return summarize(plan,[row],answers)['arms']['false']

    def test_legacy_success_uses_engine_terminal_status(self):
        result = self.run_steps([self.response(text='src/demo.py\nfunction: render\n<finish></finish>')],
                                protocol='legacy').to_dict()
        self.assertNotIn('diagnostics',result)
        self.assertEqual(result['status'],'success')
        score = self.score(result)
        self.assertEqual(score['valid_finish_count'],1)
        self.assertEqual(score['valid_finish_rate'],1)
        self.assertEqual(score['metrics']['entities_recall_at_1'],1)

    def test_legacy_valid_empty_is_finished_but_no_location_credit(self):
        result = self.run_steps([self.response(text='<finish></finish>')],protocol='legacy').to_dict()
        self.assertEqual(result['status'],'empty')
        self.assertNotIn('diagnostics',result)
        score = self.score(result)
        self.assertEqual(score['valid_finish_count'],1)
        self.assertTrue(all(value==0 for value in score['metrics'].values()))

    def test_legacy_iteration_limit_has_no_finish_or_location_credit(self):
        result = self.run_steps([self.response(text='Still searching.')],
                                max_iterations=1,protocol='legacy').to_dict()
        self.assertEqual(result['status'],'iteration_limit')
        score = self.score(result)
        self.assertEqual(score['valid_finish_count'],0)
        self.assertTrue(all(value==0 for value in score['metrics'].values()))

    def test_bounded_failures_never_fall_back_to_legacy_success(self):
        responses = [
            self.response('finish',{'files':['src/demo.py'],'entities':['unknown']}),
            self.response(text='src/demo.py\nfunction: render\n<finish></finish>'),
            self.finish(reason='length')]
        for response in responses:
            with self.subTest(response=response):
                result = self.run_steps([response],max_iterations=1).to_dict()
                score = self.score(result)
                self.assertEqual(score['valid_finish_count'],0)
                self.assertEqual(result['found_files'],[])
                self.assertTrue(all(value==0 for value in score['metrics'].values()))
                forensic = {**result,'status':'success'}
                self.assertFalse(valid_finish({'status':'completed','result':forensic}))

    def test_ambiguous_termination_is_na_without_changing_recall(self):
        result = {'found_files':['src/demo.py'],'found_entities':[self.entity],'messages':[]}
        score = self.score(result)
        self.assertIsNone(score['valid_finish_count'])
        self.assertIsNone(score['valid_finish_rate'])
        self.assertEqual(score['valid_finish_unknown_count'],1)
        self.assertEqual(score['metrics']['files_recall_at_1'],1)
        self.assertIsNone(valid_finish({'status':'completed','result':{**result,'status':'success','diagnostics':{}}}))
        self.assertFalse(valid_finish({'status':'failed','result':{**result,'status':'success'}}))
        self.assertFalse(valid_finish({'status':'missing'}))

    def test_offline_termination_metrics_remain_unavailable(self):
        result = self.run_steps([self.response(text='<finish></finish>')],protocol='legacy').to_dict()
        score = self.score(result,mode='offline')
        for key in ['valid_finish_count','valid_finish_rate','valid_finish_unknown_count']:
            self.assertIsNone(score[key])
        self.assertTrue(all(value is None for value in score['metrics'].values()))
