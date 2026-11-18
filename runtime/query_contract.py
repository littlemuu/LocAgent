"""One exact UTF-8 retrieval-query contract shared by schemas, tools and IPC."""
MAX_RETRIEVAL_QUERY_BYTES = 16000

def validate_retrieval_query(query):
    if not isinstance(query,str) or not query.strip():
        raise ValueError('invalid_query')
    try:raw=query.encode('utf-8')
    except UnicodeError:raise ValueError('invalid_query_utf8') from None
    if len(raw)>MAX_RETRIEVAL_QUERY_BYTES:
        raise ValueError('retrieval_query_byte_limit')
    return query
