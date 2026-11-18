"""Prediction validation only: no filesystem access, correction, or gold lookup."""
from copy import deepcopy
from readonly_agent.core import safe_name

PATH_INSTRUCTION = (
    'Copy final paths and qualified names exactly from source-tool evidence when available. '
    'Issue spelling may be wrong (including l versus 1); do not infer a correction. '
    'State uncertainty for unverified predictions. Safe nonexistent predictions remain '
    'localization errors; no spelling is automatically repaired.'
)

def validate_finish(args, snapshot):
    if not isinstance(args, dict) or set(args) != {'files', 'entities', 'answer'}:
        raise ValueError('invalid_finish_fields')
    if not isinstance(args['answer'], str):
        raise ValueError('invalid_answer')
    for key in ('files', 'entities'):
        values = args[key]
        if not isinstance(values, list) or len(values) > 5 or any(not isinstance(v, str) for v in values):
            raise ValueError('invalid_predictions')
        if len(set(values)) != len(values):
            raise ValueError('duplicate_predictions')
        for value in values:
            path, sep, entity = value.partition(':')
            safe_name(path)
            if any(p in {'.git','.hg','.svn','.env','.aws','.ssh','.codex','.agents'} or p.startswith('.env.') for p in path.split('/')):
                raise ValueError('sensitive_prediction_path')
            if key == 'files' and sep:
                raise ValueError('invalid_file_format')
            if key == 'entities' and (not sep or not entity or any(not p.isidentifier() for p in entity.split('.'))):
                raise ValueError('invalid_entity_format')
    return deepcopy(args)

def audit_predictions(args, snapshot):
    data = validate_finish(args, snapshot)
    return {'policy':'safe-predictions-v2', 'predictions_unchanged':True,
            'unknown_paths':sorted({v.partition(':')[0] for key in ('files','entities')
                                    for v in data[key] if v.partition(':')[0] not in snapshot.files}),
            'corrections':[], 'requires_quality_scoring':True}
