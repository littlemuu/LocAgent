"""Read-only evidence audit. Never imports SDK, tools, target source or transport."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from readonly_agent.core import digest


def sha(data):
    return hashlib.sha256(data).hexdigest()


def analyze_records(calls, events, result, *, simulation):
    answer = result.get('answer')
    if not isinstance(answer, dict):
        answer = {}
    actions = {e['tool_call_id']: e for e in events if e.get('kind') == 'ActionEvent'}
    observations = {e['tool_call_id']: e for e in events if e.get('kind') == 'ObservationEvent'}
    finishes = [e for e in actions.values() if e.get('tool_name') == 'finish'
                and e.get('action', {}).get('kind') == 'FinishAction']
    normal_finish = (result.get('status') == 'completed' and result.get('sdk_status') == 'finished'
        and isinstance(result.get('answer'), dict) and any(
            f['tool_call_id'] in observations
            and observations[f['tool_call_id']].get('action_id') == f['id']
            and not observations[f['tool_call_id']].get('observation', {}).get('is_error', True)
            for f in finishes))
    retrieved = []
    evidence_issues = []
    for index, call in enumerate(calls):
        if call.get('response_evidence_issue'):
            evidence_issues.append({'request_number':index+1,'reason':call['response_evidence_issue']})
            continue
        response = call.get('response') or {}
        for choice in response.get('choices', []):
            for invoked in choice.get('message', {}).get('tool_calls', []):
                if invoked.get('function', {}).get('name') != 'locagent_retrieve':
                    continue
                identifier = invoked['id']
                try:
                    args = json.loads(invoked['function']['arguments'])
                    if not isinstance(args,dict):raise ValueError('non_object_tool_arguments')
                except (ValueError,TypeError,KeyError):
                    evidence_issues.append({'request_number':index+1,'reason':'unparseable_retrieval_arguments'})
                    continue
                request = call['request']
                offered = any(t.get('function', {}).get('name') == 'locagent_retrieve'
                              for t in request['tools'])
                action = actions.get(identifier, {})
                observation = observations.get(identifier, {})
                action_matches = (action.get('tool_name') == 'locagent_retrieve'
                    and action.get('tool_call', {}).get('name') == 'locagent_retrieve'
                    and json.loads(action.get('tool_call', {}).get('arguments', '{}')) == args)
                linked = bool(action_matches and observation.get('tool_name') == 'locagent_retrieve'
                              and observation.get('action_id') == action.get('id'))
                observed = observation.get('observation', {})
                parts = observed.get('content', [])
                text = ''.join(p['text'] for p in parts if p.get('type') == 'text')
                try:
                    body = json.loads(text)
                except (ValueError, TypeError):
                    body = {}
                if not isinstance(body, dict):
                    body = {}
                success = bool(linked and not observed.get('is_error', True)
                               and isinstance(body, dict) and 'error' not in body)
                evidence = body.get('text', '') if isinstance(body, dict) else ''
                found = bool(success and isinstance(evidence, str) and '### Search Result:' in evidence
                             and 'Found ' in evidence)
                next_call = calls[index+1] if index+1 < len(calls) else None
                # Immediate next provider request, not merely a saved SDK event.
                delivered = bool(next_call and text and any(
                    m.get('role') == 'tool' and m.get('tool_call_id') == identifier
                    and m.get('content') == text for m in next_call['request']['messages']))
                choice_mode = request.get('tool_choice')
                selection = ('scripted_fixture' if simulation else
                             'live_auto_selection' if choice_mode == 'auto' else 'live_forced_tool_policy')
                retrieved.append({'call_id': identifier, 'request_number': index+1,
                    'query': args.get('query'), 'offset': args.get('offset', 0),
                    'tool_was_offered': offered, 'selection_category': selection,
                    'wire_tool_choice': choice_mode, 'sdk_action_matches_response': action_matches,
                    'sdk_observation_linked': linked, 'tool_succeeded': success,
                    'source_evidence_found': found, 'pagination_remaining': body.get('next_offset') is not None,
                    'observation_sha256': sha(text.encode()),
                    'observation_bytes': len(text.encode()),
                    'in_immediate_next_request': delivered,
                    'next_request_number': index+2 if delivered else None,
                    'returned_path_mentions_in_final': [p for p in answer.get('files', [])
                                                        if p in evidence],
                    'chain_verified': bool(offered and linked and success and found and delivered and normal_finish)})
    return {'simulation': simulation, 'retrieval_offered': any(any(
                t.get('function', {}).get('name') == 'locagent_retrieve' for t in c['request']['tools']) for c in calls),
            'retrieval_calls': len(retrieved), 'normal_finish': bool(normal_finish), 'invocations': retrieved,
            'all_invocations_verified': bool(retrieved) and not evidence_issues and all(r['chain_verified'] for r in retrieved),
            'live_auto_selection_observed': any(r['selection_category']=='live_auto_selection' for r in retrieved),
            'outcome': ('observed_with_incomplete_response_evidence' if retrieved else 'incomplete_response_evidence')
                       if evidence_issues else ('not_selected' if not retrieved else 'observed'),
            'response_evidence_issues': evidence_issues,
            'claims_retrieval_benefit': False,
            'interpretation': 'Evidence delivery and path overlap do not prove causal use or retrieval benefit.'}


def audit(ledger_path, arm_dir, arm):
    ledger_path, arm_dir = Path(ledger_path).resolve(), Path(arm_dir).resolve()
    with sqlite3.connect(ledger_path.as_uri()+'?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        state = db.execute('SELECT * FROM run').fetchone()
        if state['owner'] != str(ledger_path):
            raise ValueError('ledger_path_binding_changed')
        plan=json.loads(state['plan'])
        if digest(plan) != state['hash']:
            raise ValueError('plan_digest_mismatch')
        calls=[]
        for row in db.execute('SELECT * FROM calls WHERE arm=? ORDER BY id',(arm,)):
            if sha(row['request']) != row['request_hash']:
                raise ValueError('request_digest_mismatch')
            response = None
            issue = None
            if row['response'] is not None:
                if sha(row['response']) != row['response_hash']:
                    raise ValueError('response_digest_mismatch')
                if row['status']!='settled' or row['complete']!=1 or row['http_status']!=200:
                    # Verify the stored bytes' hash, but never parse an incomplete
                    # or unsettled receipt as evidence of model/tool behavior.
                    issue = 'receipt_unsettled_or_incomplete'
                else:
                    response = json.loads(row['response'])
            else:
                issue = 'receipt_missing'
            calls.append({'request':json.loads(row['request']), 'response':response,
                          'response_evidence_issue':issue})
        simulation = 'mode' not in state.keys() or state['mode'] == 'simulation'
    trace = [json.loads(line) for line in (arm_dir/'trace.jsonl').read_text().splitlines()]
    contract=json.loads((arm_dir/'contract.json').read_text())
    for key in ('snapshot','source_hashes','issue_hash','runtime_hash','system_hash','limits','sdk_version'):
        if contract[key] != plan[key]:
            raise ValueError('contract_plan_mismatch')
    if contract['retrieval'] != (arm=='retrieval'):
        raise ValueError('arm_contract_mismatch')
    if 'controller_policy' in plan and contract.get('controller_policy') != plan['controller_policy']:
        raise ValueError('controller_policy_mismatch')
    events = [line['data'] for line in trace if line.get('event')=='sdk_event']
    result = json.loads((arm_dir/'result.json').read_text())
    report = analyze_records(calls, events, result, simulation=simulation)
    report.update({'arm':arm,'plan_hash':state['hash'], 'ledger_sha256':sha(ledger_path.read_bytes()),
                   'trace_sha256':sha((arm_dir/'trace.jsonl').read_bytes()), 'artifact_bindings_verified':True})
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--arm-dir',type=Path,required=True)
    parser.add_argument('--arm',choices=['baseline','retrieval'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=audit(args.ledger,args.arm_dir,args.arm)
    with args.output.open('x') as stream:
        json.dump(report,stream,indent=2,ensure_ascii=False)
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
