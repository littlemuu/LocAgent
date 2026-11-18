def replace_profile(db, cache, versions, tenant, user, payload):
    db.write(tenant, user, payload)
    identity = (tenant, user)
    versions[identity] = versions.get(identity, 0) + 1
    return versions[identity]
