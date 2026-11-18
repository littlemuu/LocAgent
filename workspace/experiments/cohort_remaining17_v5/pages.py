from copy import deepcopy
from readonly_agent.core import encoded,safe_name

class CommonPages:
    """Count a bounded renderer-provenance index inside the existing page budget."""
    def __init__(self,reserved_bytes=0):
        self.outputs,self.audit={},[]
        self.delivered_bytes=0
    def add(self,raw,name,arguments):
        key='output-'+str(len(self.outputs)+1)
        candidates=[];seen=set()
        for span in getattr(raw,'candidate_spans',[]):
            if span.get('repeated'):continue
            for path in span.get('payload',{}).get('files',[]):
                safe_name(path)
                if path in seen:continue
                seen.add(path)
                offset=span['offset']
                if type(offset) is not int or not 0<=offset<len(raw):raise ValueError('invalid_evidence_span')
                candidates.append({'path':path,'evidence_offset':offset})
        self.outputs[key]={'raw':str(raw),'tool':name,'arguments':deepcopy(arguments),'candidates':candidates}
        return key
    def page(self,output_id,offset,call_id,name):
        if output_id not in self.outputs or type(offset) is not int:raise ValueError('invalid_continuation')
        item=self.outputs[output_id];raw=item['raw']
        if not 0<=offset<=len(raw):raise ValueError('invalid_continuation')
        capacity=min(4096,14336-self.delivered_bytes)
        selected=[]
        if offset==0:
            for row in item['candidates'][:8]:
                if len(encoded(selected+[row]))>min(1024,capacity//3):break
                selected.append(row)
        def body(end):
            value={'text':raw[offset:end],'output_id':output_id,'next_offset':end if end<len(raw) else None}
            if offset==0 and item['candidates']:
                value['candidate_index']=selected
                value['candidate_index_omitted']=len(item['candidates'])-len(selected)
                value['candidate_index_note']='Retrieved paths only; not verified relevance. evidence_offset is a raw-output character cursor.'
            return value
        low,high=offset,len(raw)
        if len(encoded(body(low)))>capacity:raise BufferError('tool_budget_exhausted')
        while low<high:
            mid=(low+high+1)//2
            if len(encoded(body(mid)))<=capacity:low=mid
            else:high=mid-1
        if low==offset and low<len(raw):raise BufferError('tool_budget_exhausted')
        content=encoded(body(low)).decode();size=len(content.encode());self.delivered_bytes+=size
        self.audit.append({'output_id':output_id,'offset':offset,'end_offset':low,'content_utf8_bytes':size,'source_bytes':self.delivered_bytes,'candidate_index':deepcopy(selected)})
        return {'role':'tool','tool_call_id':call_id,'content':content}
