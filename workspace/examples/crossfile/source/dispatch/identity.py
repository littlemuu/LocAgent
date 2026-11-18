from hashlib import sha256


def delivery_key(event_id, endpoint):
    """Stable identity for one event sent to one destination."""
    material = str(event_id) + '\n' + endpoint
    return sha256(material.encode('utf-8')).hexdigest()
