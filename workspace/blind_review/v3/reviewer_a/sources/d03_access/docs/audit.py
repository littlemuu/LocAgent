def record_access(audit, user_id, document_id, action):
    audit.append((user_id, document_id, action))
