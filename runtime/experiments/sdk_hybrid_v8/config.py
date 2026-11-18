from dataclasses import dataclass, asdict
from readonly_agent.core import digest

@dataclass(frozen=True)
class RetrievalConfig:
    mode: str = 'hybrid'
    fallback: str = 'error'
    top_k: int = 5
    max_chars: int = 12000
    rrf_constant: int = 60
    bm25_weight: int = 1
    dense_weight: int = 2
    embedding_model: str = 'synthetic-v8-fixture'
    dimensions: int = 2

    def __post_init__(self):
        if self.mode not in ('body_bm25', 'dense', 'hybrid') or self.fallback not in ('error', 'body_bm25'):
            raise ValueError('invalid_retrieval_mode')
        for value in (self.top_k,self.max_chars,self.rrf_constant,self.bm25_weight,self.dense_weight,self.dimensions):
            if type(value) is not int:raise ValueError('integer_configuration_required')
        if not 1 <= self.top_k <= 5 or not 32 <= self.max_chars <= 12000 or not 1 <= self.dimensions <= 2048:
            raise ValueError('configuration_out_of_bounds')
        if (self.rrf_constant,self.bm25_weight,self.dense_weight)!=(60,1,2):
            raise ValueError('v8_fixed_fusion_parameters_required')
        if self.embedding_model != 'synthetic-v8-fixture':raise ValueError('offline_synthetic_model_only')

    def to_dict(self):return asdict(self)
    @property
    def algorithm(self):
        return {'corpus_policy':'all-allowlisted-python-definitions-v8.1',
                'document_text':'entity_id + newline + original_function_source',
                'bm25':{'method':'lucene','k1':1.5,'b':0.75,'stemming':'english','stopwords':'en','positive_only':True},
                'dense':'normalized_exact_cosine','entity_aggregation':'maximum_chunk_score',
                'fusion':'weighted_rrf','pretruncate':False,'tie_break':'entity_id_lexical',
                'file_projection':'best_entity_rank','definition_policy':'span_bound_blocks_entity_max_aggregation','preview_definition':'within_entity_weighted_rrf_or_max_score','query_contract':'exact_utf8_max16000_v1'}
    @property
    def identity(self):return digest({'config':self.to_dict(),'algorithm':self.algorithm})
