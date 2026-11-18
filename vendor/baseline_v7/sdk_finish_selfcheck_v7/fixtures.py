"""Scripts test transport wiring only; no simulated quality score."""
import json,re
from readonly_agent.core import encoded

def mock_transport(arm,snapshot,issue):
    import httpx
    count=0;query=sorted(snapshot.files)[0]
    def reply(req):
        nonlocal count
        count+=1;q=json.loads(req.content);names={t['function']['name'] for t in q['tools']}
        if count==4 or names=={'finish'}:
            name,args='finish',{'message':{'files':[sorted(snapshot.files)[0]],'entities':[],'answer':'Offline fixture; no localization quality measurement.'}}
        elif count==1:name,args='list_files',{'offset':0}
        elif count==2:name,args='read_file',{'path':sorted(snapshot.files)[0],'start_line':1,'end_line':20}
        else:name,args='locagent_retrieve',{'query':query,'offset':0}
        return httpx.Response(200,json={'id':f'mock-{arm}-{count}','model':'deepseek-flash','choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,'tool_calls':[{'id':f'{arm}-{count}','type':'function','function':{'name':name,'arguments':encoded(args).decode()}}]}}],'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
    return httpx.MockTransport(reply)
