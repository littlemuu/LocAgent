"""Bound immutable synthetic cache. No provider, key, URL, DB or embedding call."""
import hashlib,math
from readonly_agent.core import digest
from .ranking import entity_ranking

class QueryVectorMissing(ValueError):pass

def query_key(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def normalized(value,dimensions):
    if not isinstance(value,list) or len(value)!=dimensions or any(type(x) not in (int,float) or not math.isfinite(x) for x in value):raise ValueError('invalid_vector')
    norm=math.hypot(*value)
    if not norm or not math.isfinite(norm):raise ValueError('invalid_vector_norm')
    return tuple(x/norm for x in value)

def make_synthetic_cache(corpus,config,document_vectors,query_vectors):
    """Fixture builder only; values are supplied, never generated or inferred."""
    payload={'format':'v8-synthetic-cache-v1','kind':'synthetic-fixture','snapshot':corpus.snapshot.identity,'corpus':corpus.identity,'model':config.embedding_model,'dimensions':config.dimensions,'documents':document_vectors,'queries':{query_key(q):v for q,v in query_vectors.items()}}
    CachedDense(payload,corpus,config,digest(payload))
    return payload

class CachedDense:
    def __init__(self,payload,corpus,config,expected_hash):
        import re
        if not isinstance(payload,dict) or set(payload)!={'format','kind','snapshot','corpus','model','dimensions','documents','queries'}:raise ValueError('invalid_vector_cache_fields')
        if digest(payload)!=expected_hash:raise ValueError('vector_cache_hash_mismatch')
        if payload['format']!='v8-synthetic-cache-v1' or payload['kind']!='synthetic-fixture':raise ValueError('offline_synthetic_cache_only')
        if (payload['snapshot'],payload['corpus'],payload['model'],payload['dimensions'])!=(corpus.snapshot.identity,corpus.identity,config.embedding_model,config.dimensions) or type(payload['dimensions']) is not int:raise ValueError('vector_cache_binding_mismatch')
        docs=payload['documents'];queries=payload['queries']
        if not isinstance(docs,dict) or set(docs)!={d.id for d in corpus.documents}:raise ValueError('vector_document_membership_mismatch')
        if not isinstance(queries,dict) or len(queries)>20000 or any(not isinstance(k,str) or not re.fullmatch('[a-f0-9]{64}',k) for k in queries):raise ValueError('invalid_query_cache')
        self.rows=tuple(normalized(docs[d.id],config.dimensions) for d in corpus.documents)
        self.queries={k:normalized(v,config.dimensions) for k,v in queries.items()}
        self.docs=corpus.documents;self.identity=expected_hash
    def search(self,query):
        try:q=self.queries[query_key(query)]
        except KeyError:raise QueryVectorMissing('query_vector_not_cached') from None
        return entity_ranking(self.docs,[math.fsum(a*b for a,b in zip(q,v)) for v in self.rows])
