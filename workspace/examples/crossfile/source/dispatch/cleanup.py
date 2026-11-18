def prune_receipts(receipts, expired_ids):
    """Retention is controlled by the caller, without a persistent archive."""
    receipts.acknowledged.difference_update(expired_ids)
