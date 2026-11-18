"""Separate protocol/budget/transport failures from completed localization misses."""
from readonly_agent.deepseek_wire import strict_json, structured_finish
from .scoring import ranked_metrics

def outcome(system, result, *, simulation=False):
    if system not in ('sdk','native'): raise ValueError('unknown_system')
    if simulation or result.get('simulation'):
        return {'category':'simulation','quality_eligible':False,'answer':None}
    status=result.get('status')
    if status=='not_run':return {'category':'not_run','quality_eligible':False,'answer':None}
    if system=='sdk':
        completed=status=='completed'
        answer=result.get('answer')
        reason=result.get('failure')
    else:
        reason=(result.get('diagnostics') or {}).get('termination_reason',result.get('error'))
        completed=status in ('success','empty') and reason=='finished'
        answer=None
        if completed:
            try:
                wrapper=strict_json(result['raw_output'])
                if set(wrapper)!={'message'}:raise ValueError('unexpected_native_finish')
                answer=wrapper['message']
            except (ValueError,TypeError,KeyError):
                return {'category':'protocol_failure','quality_eligible':False,'answer':None}
    if completed:
        try:answer=structured_finish(answer)
        except (ValueError,TypeError):
            return {'category':'protocol_failure','quality_eligible':False,'answer':None}
        return {'category':'completed','quality_eligible':True,'answer':answer}
    reason=str(reason or status or 'unknown')
    if any(t in reason.lower() for t in ('timeout','unknown','transport','readtimeout')):
        category='transport_failure'
    elif any(t in reason for t in ('budget','context_limit','iteration_limit','quota')):
        category='budget_or_termination_failure'
    elif any(t in reason for t in ('index','source','executor','execution_error')):
        category='tool_or_index_failure'
    elif any(t in reason for t in ('finish','truncat','protocol','invalid','unavailable_tool','response')):
        category='protocol_failure'
    else:category='unclassified_failure'
    return {'category':category,'reason':reason,'quality_eligible':False,'answer':None}

def score_outcome(normalized,gold,k,dialect='strict'):
    if not normalized['quality_eligible']:
        return {'category':normalized['category'],'quality':None,
                'planned_denominator_adjusted_zero':0 if normalized['category']!='simulation' else None}
    return {'category':'completed','quality':ranked_metrics(gold,normalized['answer']['entities'],k,dialect=dialect)}
