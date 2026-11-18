"""Post-hoc only; not imported by the runner. No target imports or upstream execution."""
import math

from experiments.dev_compare.suite import score_localization


def official_reference(gold, predictions, k=5, max_k=10):
    """Frozen upstream found_entities semantics; NOT an official benchmark run."""
    if not 1 <= k <= max_k:
        raise ValueError('invalid_k')
    targets = list(dict.fromkeys(x[:-9] if x.endswith('.__init__') else x for x in gold))
    if not targets:
        return None
    count = min(len(targets), max_k)
    hits = [int(x in targets) for x in predictions[:k]]
    ideal = sum(1/math.log2(i+2) for i in range(min(k,count)))
    return {'Acc':float(sum(hits)==min(k,count)), 'Recall':sum(hits)/count, 'P':sum(hits)/k,
        'NDCG':sum(v/math.log2(i+2) for i,v in enumerate(hits))/ideal,
        'MAP':sum(sum(hits[:i+1])/(i+1) for i,v in enumerate(hits) if v)/k}


def score(result, labels):
    if result.get('simulation') or result.get('quality_measured') is False:
        raise ValueError('scripted_fixtures_are_not_quality_results')
    if result['status'] == 'not_run':
        return {'status':'not_run','raw_score':None,'planned_denominator_score':0}
    strict = score_localization(result, labels)
    predicted = result['answer']['entities'] if result['status'] == 'completed' else []
    return {'strict_exact_top5':strict,
            'upstream_found_entities_reference_at5':official_reference(labels['gold_entities'],predicted),
            'official_benchmark_run':False}
