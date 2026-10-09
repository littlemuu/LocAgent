"""Portable graph/finish guidance regressions; no saved indexes or provider calls."""
import ast
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from locagent_service.offline import offline_engine
from util.localization_contract import LocalizationOptions, LocalizationRequest, ResultStatus, LocalizationError
from util.localizer import GraphLocalizer, _graph_session

SOURCE = """builtin_str = str

class Request:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, event, hook):
        self.hooks[event] = hook
        return hook
"""


def setUpModule():
    global guard
    guard = offline_engine()
    guard.__enter__()


def tearDownModule():
    guard.__exit__(None, None, None)


class SubmissionGuidanceTests(unittest.TestCase):
    def setUp(self):
        import networkx as nx
        from dependency_graph.build_graph import CodeAnalyzer
        from litellm import ModelResponse
        from plugins.location_tools.repo_ops import repo_ops
        self.Response, self.ops = ModelResponse, repo_ops
        self.request = LocalizationRequest('demo__demo-1', 'demo/demo', 'a'*40, 'Find the hook.')
        # Only parse this tiny temporary source; never rebuild a repository/index.
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp)/'demo.py'
            filename.write_text(SOURCE)
            analyzer = CodeAnalyzer(str(filename))
            analyzer.visit(ast.parse(SOURCE))
        self.nodes = analyzer.nodes
        self.graph = nx.MultiDiGraph()
        self.graph.add_node('.', type='directory')
        self.graph.add_node('demo.py', type='file', code=SOURCE,
                            start_line=1, end_line=len(SOURCE.split('\n')))
        self.graph.add_edge('.', 'demo.py', type='contains')
        for node in self.nodes:
            value = deepcopy(node)
            name = value.pop('name')
            self.graph.add_node('demo.py:'+name, **value)
            parent = 'demo.py:'+name.rsplit('.',1)[0] if '.' in name else 'demo.py'
            self.graph.add_edge(parent, 'demo.py:'+name, type='contains')
        self.sent=[]
        output=redirect_stdout(io.StringIO());output.__enter__()
        self.addCleanup(output.__exit__,None,None,None)

    def response(self, name, arguments):
        return self.Response(model='offline-only', choices=[{'index':0,'finish_reason':'tool_calls',
            'message':{'role':'assistant','content':None,'tool_calls':[{
                'id':'offline-call','type':'function','function':{
                    'name':name,'arguments':json.dumps(arguments)}}]}}],
            usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})

    def run_tools(self, calls, *, protocol='bounded-v1', limit=None):
        steps=iter(self.response(name,args) for name,args in calls)
        def provider(**kwargs):
            self.sent.append(deepcopy(kwargs))
            return next(steps)
        return GraphLocalizer.from_graph(self.graph, provider=provider, model_name='offline-only',
            options=LocalizationOptions(max_iterations=limit or len(calls), suppress_repeats=True,
                                        search_protocol=protocol)).localize(self.request)

    def final(self, entity='demo.py:Request.register_hook'):
        return ('finish',{'files':['demo.py'],'entities':[entity]})

    def payloads(self, text):
        return [json.loads(value) for value in re.findall(
            r'Finish target \(type=(?:function|class|file)\): (\{[^\n]*?\})\.', text)]

    def test_analyzer_omits_constructor_node_but_keeps_its_class_source(self):
        self.assertNotIn('demo.py:Request.__init__', self.graph)
        self.assertNotIn('demo.py:builtin_str', self.graph)
        self.assertIn('def __init__(self):', self.graph.nodes['demo.py:Request']['code'])
        self.assertIn('self.hooks = {}', self.graph.nodes['demo.py:Request']['code'])

    def test_variable_file_directory_and_missing_constructor_rejected_as_entities(self):
        from util.localization_protocol import validate_locations
        for entity in ['demo.py:builtin_str','demo.py','.','demo.py:Request.__init__']:
            with self.subTest(entity=entity),self.assertRaises(ValueError):
                validate_locations({'files':['demo.py'],'entities':[entity]},self.graph)
        for entity in ['demo.py:Request','demo.py:Request.register_hook']:
            validate_locations({'files':['demo.py'],'entities':[entity]},self.graph)
        self.assertEqual(validate_locations({'files':['demo.py'],'entities':[]},self.graph),
                         (['demo.py'],[],[]))

    def test_every_advertised_target_uses_existing_type_and_passes_strict_contract(self):
        from util.localization_protocol import validate_locations
        for node in self.graph:
            hint=self.ops._submission_hint(self.graph,node)
            payloads=self.payloads(hint)
            if self.graph.nodes[node]['type']=='directory':
                self.assertEqual(payloads,[])
                self.assertIn('Navigation only',hint)
            else:
                self.assertEqual(len(payloads),1)
                validate_locations(payloads[0],self.graph)
                self.assertIn('type='+self.graph.nodes[node]['type'],hint)
                expected=[] if self.graph.nodes[node]['type']=='file' else [node]
                self.assertEqual(payloads[0]['entities'],expected)
        self.assertEqual(self.ops._submission_hint(self.graph,'demo.py:missing'),'')

    def test_search_and_read_display_graph_ids_and_keep_repeat_suppression(self):
        result=self.run_tools([
            ('search_code_snippets',{'search_terms':['demo.py:Request']}),
            ('get_entity_contents',{'entity_names':['demo.py:Request']}),
            self.final('demo.py:Request')])
        first=result.diagnostics['tool_outputs']['output-1']['raw']
        self.assertIn('Finish target (type=class)',first)
        self.assertIn('Constructor: no separate __init__ node',first)
        self.assertIn('def __init__(self):',first)
        self.assertIn('Repeated content for',self.sent[-1]['messages'][-2]['content'])
        self.assertTrue(result.return_records['demo.py:Request'][1]['previously_in_context'])
        self.assertEqual(result.status,ResultStatus.SUCCESS)

    def test_function_search_and_file_line_read_have_distinct_finish_fields(self):
        with _graph_session(self.graph,self.request.as_task(),None,None):
            function=self.ops.search_code_snippets(
                search_terms=['demo.py:Request.register_hook'],_submission_hints=True)
            lines=self.ops.search_code_snippets(
                line_nums=[1],file_path_or_pattern='demo.py',_submission_hints=True)
        self.assertIn({'files':['demo.py'],'entities':['demo.py:Request.register_hook']},
                      self.payloads(function))
        self.assertIn({'files':['demo.py'],'entities':[]},self.payloads(lines))
        self.assertIn('variable/assignment aliases are not entities',lines)

    def test_unindexed_variable_read_points_only_to_file(self):
        result=self.run_tools([
            ('get_entity_contents',{'entity_names':['demo.py:builtin_str']}),self.final()])
        raw=result.diagnostics['tool_outputs']['output-1']['raw']
        self.assertIn('Invalid name.',raw)
        self.assertEqual(self.payloads(raw),[{'files':['demo.py'],'entities':[]}])

    def test_constructor_read_suggests_class_and_source_is_still_readable(self):
        result=self.run_tools([
            ('get_entity_contents',{'entity_names':['demo.py:Request.__init__']}),
            ('get_entity_contents',{'entity_names':['demo.py:Request']}),
            self.final('demo.py:Request')])
        raw=result.diagnostics['tool_outputs']['output-1']['raw']
        self.assertIn('No separate constructor entity exists.',raw)
        self.assertEqual(self.payloads(raw),[{'files':['demo.py'],'entities':['demo.py:Request']}])
        self.assertIn('def __init__(self):',result.diagnostics['tool_outputs']['output-2']['raw'])
        self.assertEqual(result.found_modules,['demo.py:Request'])

    def test_tree_displays_types_and_only_valid_submit_ids(self):
        from util.localization_protocol import validate_locations
        result=self.run_tools([
            ('explore_tree_structure',{'start_entities':['/'],'traversal_depth':3}),self.final()])
        raw=result.diagnostics['tool_outputs']['output-1']['raw']
        self.assertIn('Navigation only (type=directory)',raw)
        self.assertIn('type=file',raw);self.assertIn('type=class',raw);self.assertIn('type=function',raw)
        for payload in self.payloads(raw):validate_locations(payload,self.graph)
        self.assertIn('Constructor: no separate __init__ node',raw)

    def test_legacy_tool_display_stays_unchanged(self):
        result=self.run_tools([
            ('get_entity_contents',{'entity_names':['demo.py:Request']}),
            ('explore_tree_structure',{'start_entities':['.'],'traversal_depth':3}),
            ('finish',{'thought':'demo.py\nfunction: Request.register_hook'})],protocol='legacy')
        observations=[m['content'] for m in result.messages if m['role']=='tool']
        self.assertTrue(observations)
        self.assertTrue(all('Finish target' not in text for text in observations))
        self.assertEqual(result.status,ResultStatus.SUCCESS)

    def test_system_schema_and_final_prompt_state_same_strict_rules(self):
        self.run_tools([self.final()],limit=1)
        request=self.sent[0]
        properties=request['tools'][0]['function']['parameters']['properties']
        self.assertIn('Variables/assignment aliases',properties['files']['description'])
        self.assertIn('function/class',properties['entities']['description'])
        self.assertIn('One invalid item rejects',properties['entities']['description'])
        self.assertIn('owning class ID',properties['entities']['description'])
        self.assertIn('Source code names are not automatically graph IDs',request['messages'][0]['content'])
        self.assertIn('One invalid item rejects all results',request['messages'][-1]['content'])
        self.assertEqual(request['tool_choice']['function']['name'],'finish')

    def test_guidance_does_not_mark_paginated_unread_source_seen(self):
        self.graph.nodes['demo.py:Request']['code']=(
            'class Request:\n    def __init__(self):\n        self.value = "'+'x'*20000+'"')
        self.graph.nodes['demo.py:Request']['start_line']=1
        self.graph.nodes['demo.py:Request']['end_line']=3
        result=self.run_tools([
            ('get_entity_contents',{'entity_names':['demo.py:Request']}),
            self.final('demo.py:Request')])
        entry=result.return_records['demo.py:Request'][0]
        self.assertFalse(entry['in_context'])
        self.assertIn('Finish target (type=class)',result.messages[3]['content'])
        self.assertTrue(result.diagnostics['tool_messages'][0]['truncation_reason'])
        self.assertLessEqual(result.diagnostics['tool_messages'][0]['message_json_bytes'],8192)

    def test_model_cannot_override_internal_display_policy(self):
        with self.assertRaises(LocalizationError):
            self.run_tools([('get_entity_contents',{'entity_names':['demo.py'],'_submission_hints':False}),
                            self.final()])


class SavedInvalidFinishTests(unittest.TestCase):
    def check_case(self,name):
        import networkx as nx
        from litellm import ModelResponse
        from util.localization_protocol import validate_locations
        from locagent_service.evaluate import summarize
        fixture=json.loads((Path(__file__).parent/'fixtures/invalid_finish_cases.json').read_text())
        case=next(c for c in fixture['cases'] if c['name']==name)
        graph=nx.MultiDiGraph()
        for node in case['graph_nodes']:
            graph.add_node(node['id'],type=node['type'],code='pass',start_line=1,end_line=1)
        args=json.loads(case['arguments_json'])
        self.assertIn(case['known_valid_target'],args['entities'])
        validate_locations({'files':[case['known_valid_target'].partition(':')[0]],
                            'entities':[case['known_valid_target']]},graph)
        with self.assertRaises(ValueError):validate_locations(args,graph)
        response=ModelResponse(model='offline-saved-arguments',choices=[{'index':0,'finish_reason':'tool_calls',
            'message':{'role':'assistant','content':None,'tool_calls':[{'id':'fixture','type':'function',
                'function':{'name':'finish','arguments':case['arguments_json']}}]}}],
            usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})
        result=GraphLocalizer.from_graph(graph,provider=lambda **kw:response,model_name='offline',
            options=LocalizationOptions(max_iterations=1,search_protocol='bounded-v1')).localize(
                LocalizationRequest(case['sample'],'psf/requests',case['base_commit'],'Fixture only.'))
        self.assertEqual(result.diagnostics['termination_reason'],'invalid_finish')
        self.assertEqual(result.found_files,[]);self.assertEqual(result.found_entities,[])
        self.assertEqual(result.status,ResultStatus.ITERATION_LIMIT)
        # Exercise scoring on a synthetic envelope; no claim about new real quality.
        summary=summarize({'sources':['fixture'],'arms':[False]},
            [{'source_id':'fixture','suppress_repeats':False,'mode':'live','status':'completed','result':result.to_dict()}],
            {'fixture':{'files':[case['known_valid_target'].partition(':')[0]],
                        'entities':[case['known_valid_target']]}})
        self.assertTrue(all(value==0 for value in summary['arms']['false']['metrics'].values()))

    def test_2317_off_valid_target_plus_unknown_variable_stays_zero(self):
        self.check_case('psf__requests-2317-false')

    def test_2317_on_valid_target_plus_file_entity_stays_zero(self):
        self.check_case('psf__requests-2317-true')

    def test_863_off_valid_target_plus_absent_constructor_stays_zero(self):
        self.check_case('psf__requests-863-false')

    def test_863_on_valid_target_plus_absent_constructor_stays_zero(self):
        self.check_case('psf__requests-863-true')
