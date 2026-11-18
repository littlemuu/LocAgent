from .http import send_request
from .retry import schedule_retry


def process_delivery(job, client, queue, receipts):
    delivery_id = job['delivery_id']
    if receipts.was_acknowledged(delivery_id):
        return 'duplicate'
    status = send_request(client, job)
    if 200 <= status < 300:
        receipts.mark_acknowledged(delivery_id)
        return 'acknowledged'
    if schedule_retry(queue, job, status):
        return 'retry_scheduled'
    return 'failed'
