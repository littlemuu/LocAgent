from .shares import valid_share

def permitted(user, document, action, token):
    if user['disabled'] or user['tenant'] != document['tenant']:
        return False
    if action not in ('read', 'write'):
        return False
    if user['id'] == document['owner'] or user['role'] == 'admin':
        return True
    return action == 'read' and valid_share(token, document)
