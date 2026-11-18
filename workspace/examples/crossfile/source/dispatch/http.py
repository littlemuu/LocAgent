def send_request(client, job):
    """Send the stable delivery identity as the receiver's idempotency key."""
    response = client.post(
        job['endpoint'],
        json=job['payload'],
        headers={'Idempotency-Key': job['delivery_id']},
    )
    return response.status_code
