from .access import permitted
from .audit import record_access

def open_document(user, document, action, token, audit):
    if not permitted(user, document, action, token):
        raise PermissionError('denied')
    record_access(audit, user['id'], document['id'], action)
    return document['body']
