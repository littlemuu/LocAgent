"""Controlled demo-v1 source. No paths, pickle uploads or clones from HTTP."""
import json

from locagent_service.models import CreateTask, DemoScenario
from locagent_service.offline import offline_engine
from util.localization_contract import LocalizationOptions, LocalizationRequest


def localize_demo(request: CreateTask):
    # Defense in depth: also revalidate requests loaded from PostgreSQL.
    request = CreateTask.model_validate(request.model_dump(mode='json'))
    with offline_engine():
        import networkx as nx
        from litellm import ModelResponse
        from util.localizer import GraphLocalizer

        code = '\n'.join(['def render(value):',
                          *['    # Deterministic long body for repeat suppression.'] * 8,
                          '    return value'])
        graph = nx.MultiDiGraph()
        graph.add_node('demo.py', type='file', code=code)
        graph.add_node('demo.py:render', type='function', code=code,
                       start_line=1, end_line=10)
        graph.add_edge('demo.py', 'demo.py:render', type='contains')

        def response(content=None, tool=None, arguments=None):
            message = {'role': 'assistant', 'content': content}
            if tool:
                message['tool_calls'] = [{
                    'id': 'demo_call', 'type': 'function',
                    'function': {'name': tool, 'arguments': json.dumps(arguments)},
                }]
            return ModelResponse(
                model='offline-demo', choices=[{'index': 0, 'message': message,
                                                'finish_reason': 'tool_calls' if tool else 'stop'}],
                usage={'prompt_tokens': 1, 'completion_tokens': 2, 'total_tokens': 3},
            )

        if request.demo_scenario == DemoScenario.SUCCESS:
            responses = iter([
                response(tool='search_code_snippets', arguments={'search_terms': ['demo.py:render']}),
                response(tool='get_entity_contents', arguments={'entity_names': ['demo.py:render']}),
                response(tool='finish', arguments={'thought': 'demo.py\nfunction: render'}),
            ])
        else:
            responses = None

        def provider(**kwargs):
            if request.demo_scenario == DemoScenario.PROVIDER_ERROR:
                raise RuntimeError('private demo provider exception; must not be exposed')
            if request.demo_scenario == DemoScenario.EMPTY:
                return response(tool='finish', arguments={'thought': ''})
            if request.demo_scenario == DemoScenario.ITERATION_LIMIT:
                return response('Still locating the function.')
            return next(responses)

        engine = GraphLocalizer.from_graph(
            graph, provider=provider, model_name='offline-demo',
            options=LocalizationOptions(**request.options.model_dump()),
        )
        return engine.localize(LocalizationRequest(
            instance_id='demo__demo-1', repo='demo/demo', base_commit='a' * 40,
            problem_statement=request.problem_statement,
        ))
