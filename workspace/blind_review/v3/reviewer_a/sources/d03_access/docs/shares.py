def valid_share(token, document):
    return (token is not None and not token['revoked']
            and token['document_id'] == document['id']
            and token['tenant'] == document['tenant'])
