from .cache import fetch_profile
from .writes import replace_profile

def get_profile(db, cache, versions, tenant, user, now):
    return fetch_profile(db, cache, versions, tenant, user, now)

def put_profile(db, cache, versions, tenant, user, payload):
    return replace_profile(db, cache, versions, tenant, user, payload)
