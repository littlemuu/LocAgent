def validate_settings(settings):
    if type(settings['attempts']) is not int or settings['attempts'] < 0:
        raise ValueError('attempts')
    if type(settings['timeout']) is not int or settings['timeout'] <= 0:
        raise ValueError('timeout')
    if type(settings['enabled']) is not bool:
        raise ValueError('enabled')
