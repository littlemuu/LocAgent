"""Issue-derived scripted responses used only in offline rehearsal."""
import json
from readonly_agent.core import encoded

def mock_transport(arm, snapshot):
    import httpx
    counter = 0
    def respond(request):
        nonlocal counter
        counter += 1
        messages = json.loads(request.content)['messages']
        if arm == 'baseline':
            if counter == 1:
                name, args = 'search_code_snippets', {'search_terms':['SET TAG']}
            elif counter == 2:
                page = json.loads(next(m['content'] for m in reversed(messages) if m['role']=='tool'))
                if page['next_offset'] is not None:
                    name, args = 'read_tool_output', {'output_id':page['output_id'],'offset':page['next_offset']}
                else:
                    name, args = 'get_entity_contents', {'entity_names':[sorted(snapshot.files)[0]]}
            else:
                name, args = 'get_entity_contents', {'entity_names':[sorted(snapshot.files)[0]]}
        else:
            name, args = [('list_files', {'offset':0}),
                ('read_file', {'path':sorted(snapshot.files)[0],'start_line':1,'end_line':20}),
                ('locagent_retrieve', {'query':'SetItem','offset':0})][min(counter-1,2)]
        if counter == 4:
            name, args = 'finish', {'message':{'files':[],'entities':[],'answer':'Offline rehearsal; no quality score.'}}
        return httpx.Response(200, json={'id':f'mock-{arm}-{counter}','model':'deepseek-flash',
            'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                'tool_calls':[{'id':f'{arm}-{counter}','type':'function','function':{'name':name,'arguments':encoded(args).decode()}}]}}],
            'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
    return httpx.MockTransport(respond)
