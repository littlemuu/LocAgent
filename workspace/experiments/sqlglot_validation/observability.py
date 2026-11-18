"""Post-run read evidence checks; labels/source are never passed to the worker."""
import json
import re
from readonly_agent.read_lines import source_lines


def check_reads(calls,events,sources,reference):
    observations={e['data']['tool_call_id']:e['data'] for e in events
        if e.get('event')=='sdk_event' and e.get('data',{}).get('kind')=='ObservationEvent'}
    actions={e['data']['tool_call_id']:e['data'] for e in events
        if e.get('event')=='sdk_event' and e.get('data',{}).get('kind')=='ActionEvent'}
    requests=[json.loads(c['request']) for c in calls]
    rows=[];delivered_lines=set();issued={}
    for index,call in enumerate(calls):
        if call['status']!='settled':continue
        raw=json.loads(call['response'])
        for toolcall in raw['choices'][0]['message'].get('tool_calls',[]):
            fn=toolcall['function']
            if fn['name']!='read_file':continue
            identifier=toolcall['id']
            try:args=json.loads(fn['arguments'])
            except (TypeError,ValueError):
                rows.append({'turn':index+1,'arguments_parse_error':True});continue
            obs=observations.get(identifier,{});action=actions.get(identifier,{})
            linked=bool(action and obs.get('action_id')==action.get('id') and obs.get('tool_name')=='read_file')
            content=''.join(p.get('text','') for p in obs.get('observation',{}).get('content',[]) if p.get('type')=='text')
            try:packet=json.loads(content)
            except (ValueError,TypeError):packet={}
            if not isinstance(packet,dict):packet={}
            success=linked and not obs.get('observation',{}).get('is_error',True) and 'error' not in packet
            delivered=bool(content and index+1<len(requests) and any(m.get('role')=='tool' and m.get('tool_call_id')==identifier
                and m.get('content')==content for m in requests[index+1]['messages']))
            cursor=args.get('cursor');valid_cursor=None if cursor is None else bool(cursor in issued and issued[cursor]==args.get('path'))
            matched=True;numbered=[]
            text=packet.get('text','')
            if success:
                lines=source_lines(sources[args['path']])
                for n,row in enumerate(text.split('\n')):
                    if not row:continue
                    match=re.match(r'^(\d+): (.*)$',row,re.S)
                    if not match:matched=False;continue
                    line=int(match[1]);part=match[2];column=packet['start_column'] if n==0 else 0
                    matched=matched and 1<=line<=len(lines) and lines[line-1][column:column+len(part)]==part
                    numbered.append(line)
                    if delivered and column==0 and line<=len(lines) and part==lines[line-1]:
                        delivered_lines.add((args['path'],line))
                if numbered:matched=matched and numbered[0]==packet['start_line'] and numbered[-1]==packet['end_line']
                if packet.get('next_cursor'):issued[packet['next_cursor']]=args['path']
            rows.append({'turn':index+1,'tool_call_id':identifier,'arguments':args,'old_offset_attempt':'offset' in args,
                'sdk_observation_linked':linked,'tool_succeeded':bool(success),'line_evidence_matches_source':bool(success and matched),
                'reported_start_line':packet.get('start_line'),'reported_end_line':packet.get('end_line'),
                'continuation_call':cursor is not None,'cursor_was_previously_returned_for_path':valid_cursor,
                'next_cursor_available':bool(packet.get('next_cursor')),'in_immediate_next_model_request':delivered})
    mapping=reference['mapping']['gold_mappings'][0];file=reference['gold_files'][0]
    expected=set(range(mapping['strict_ast']['start_line'],mapping['strict_ast']['end_line']+1))
    actual={line for path,line in delivered_lines if path==file}
    continuation=[r for r in rows if r.get('continuation_call')]
    return {'read_calls':rows,'reference_function':mapping['label'],
        'reference_body_lines_received':sorted(actual&expected),'reference_body_lines_required':sorted(expected),
        'full_reference_body_entered_model_context':expected<=actual,
        'paging_observed':bool(continuation),'paging_protocol_valid':all(r['tool_succeeded'] and r['cursor_was_previously_returned_for_path'] for r in continuation) if continuation else None,
        'absence_of_paging_is_not_failure':True,'semantic_answer_correctness_not_measured':True}
