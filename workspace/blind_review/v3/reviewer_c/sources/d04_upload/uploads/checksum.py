from hashlib import sha256

def checksum_matches(data, expected):
    return sha256(data).hexdigest() == expected
