from .leases import claim_lease, renew_lease
from .completion import acknowledge

def acquire(job, worker, now):
    return claim_lease(job, worker, now, ttl=20)

def complete(job, token, now):
    return acknowledge(job, token, now)
