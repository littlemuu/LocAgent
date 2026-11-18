from .tokens import lease_token

def claim_lease(job, worker, now, ttl):
    if job['done'] or (job['owner'] is not None and now < job['deadline']):
        return None
    job['generation'] += 1
    job['owner'] = worker
    job['deadline'] = now + ttl
    return lease_token(job)

def renew_lease(job, token, now, ttl):
    if job['done'] or token != lease_token(job) or now >= job['deadline']:
        return False
    job['deadline'] = now + ttl
    return True
