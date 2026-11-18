from .keys import cache_key
TTL = 30

def fetch_profile(db, cache, versions, tenant, user, now):
    generation = versions.get((tenant, user), 0)
    key = cache_key(tenant, user, generation)
    entry = cache.get(key)
    if entry is not None and now < entry['expires_at']:
        return entry['value']
    value = db.read(tenant, user)
    cache[key] = {'value': value, 'expires_at': now + TTL}
    return value
