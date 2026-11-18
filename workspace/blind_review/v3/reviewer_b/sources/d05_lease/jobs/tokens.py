def lease_token(job):
    return (job['id'], job['owner'], job['generation'])
