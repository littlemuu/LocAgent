"""Prediction validation only: no filesystem access, correction, or gold lookup."""
from copy import deepcopy
from readonly_agent.core import safe_name
from readonly_agent.deepseek_wire import finish_message_schema as previous_finish_schema
from readonly_agent.control import CLOSING_INSTRUCTION as PREVIOUS_CLOSING_INSTRUCTION

# Portable JSON-Schema shape checks. Python isidentifier and safe_name below
# remain authoritative for Unicode identifiers, sensitive paths and traversal.
# Do not claim that the provider enforces a constrained-decoding grammar.
FILE_SHAPE = r'^(?!/)[^:\\\u0000-\u001f]+(?![\s\S])'
ENTITY_SHAPE = r'^(?!/)[^:\\\u0000-\u001f]+:[^:\s.]+(?:\.[^:\s.]+)*(?![\s\S])'
FINISH_FORMAT_INSTRUCTION = (
    'FINAL RESULT FORMAT: files contains relative file paths only, such as src/example.py. '
    'Every entities item must contain a colon and a nonempty qualified Python function or class name, '
    'such as src/example.py:Worker.run or src/example.py:load. '
    'Never put a bare file path in entities. If you know only a file location, put it in files '
    'and leave entities empty; do not invent an entity name to fill the field. '
    'Keep the files and entities lists ranked, distinct, and at most five items each. '
    'Before finish, check that every entities item has the path:QualifiedName form. '
    'These generic examples are format illustrations, not repository evidence.'
)
CLOSING_INSTRUCTION = PREVIOUS_CLOSING_INSTRUCTION + ' ' + FINISH_FORMAT_INSTRUCTION


def finish_message_schema():
    schema = previous_finish_schema()
    schema['properties']['files'].update(
        description='Ranked relative source file paths only. Do not include a colon or qualified name. Empty is valid.',
        items={'type':'string','minLength':1,'pattern':FILE_SHAPE})
    schema['properties']['entities'].update(
        description=('Ranked path:QualifiedName IDs of Python functions/classes, e.g. src/example.py:Worker.run. '
                     'A bare filename is invalid here. If only a file is known, list it in files and use entities=[]. '
                     'Copy names from evidence; do not invent a name to satisfy the format.'),
        items={'type':'string','minLength':3,'pattern':ENTITY_SHAPE})
    return schema

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
