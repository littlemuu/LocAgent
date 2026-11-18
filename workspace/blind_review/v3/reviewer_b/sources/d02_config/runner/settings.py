from .defaults import DEFAULTS
from .validation import validate_settings

def resolve_settings(project, request):
    merged = dict(DEFAULTS)
    for layer in (project, request):
        for key in DEFAULTS:
            if key in layer and layer[key] is not None:
                merged[key] = layer[key]
    validate_settings(merged)
    return merged
