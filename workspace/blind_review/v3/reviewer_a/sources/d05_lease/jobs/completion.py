from .tokens import lease_token

def acknowledge(job, token, now):
    if job['done'] or token != lease_token(job) or now >= job['deadline']:
        return False
    job['done'] = True
    return True
