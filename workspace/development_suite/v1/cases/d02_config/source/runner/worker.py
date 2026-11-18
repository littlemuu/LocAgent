def start_worker(settings):
    if not settings['enabled']:
        return {'started': False}
    return {'started': True, 'attempts': settings['attempts'], 'timeout': settings['timeout']}
