class ReceiptStore:
    """In-memory acknowledgements, scoped to the lifetime of this instance."""

    def __init__(self):
        self.acknowledged = set()

    def was_acknowledged(self, delivery_id):
        return delivery_id in self.acknowledged

    def mark_acknowledged(self, delivery_id):
        self.acknowledged.add(delivery_id)
