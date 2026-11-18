from .parts import assemble_parts
from .checksum import checksum_matches

def complete_upload(session, expected_hash, storage):
    if session['completed']:
        return session['object_id']
    data = assemble_parts(session)
    if not checksum_matches(data, expected_hash):
        raise ValueError('checksum')
    object_id = storage.put(data)
    session['object_id'] = object_id
    session['completed'] = True
    session['parts'].clear()
    return object_id
