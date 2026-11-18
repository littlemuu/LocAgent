from .backoff import next_delay

MAX_ATTEMPT = 3


def retry_allowed(status, attempt):
    transient = status == 429 or 500 <= status < 600
    return transient and attempt < MAX_ATTEMPT


def schedule_retry(queue, job, status):
    if not retry_allowed(status, job['attempt']):
        return False
    retry_job = dict(job)
    retry_job['attempt'] += 1
    queue.push(retry_job, delay=next_delay(retry_job['attempt']))
    return True
