def discard_expired(cache, now):
    for key in list(cache):
        if cache[key]['expires_at'] <= now:
            del cache[key]
