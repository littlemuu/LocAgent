def cache_key(tenant, user, generation):
    return (str(tenant), str(user), generation)
