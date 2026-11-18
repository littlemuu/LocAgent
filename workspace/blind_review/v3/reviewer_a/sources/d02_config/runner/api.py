from .settings import resolve_settings
from .worker import start_worker

def launch(project, request):
    settings = resolve_settings(project, request)
    return start_worker(settings)
