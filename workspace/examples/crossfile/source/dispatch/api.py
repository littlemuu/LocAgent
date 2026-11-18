from .identity import delivery_key


def submit_delivery(queue, event, endpoint):
    """Enqueue one webhook delivery for an event and destination."""
    job = {
        'delivery_id': delivery_key(event['id'], endpoint),
        'endpoint': endpoint,
        'payload': event['payload'],
        'attempt': 0,
    }
    queue.push(job, delay=0)
    return job['delivery_id']
