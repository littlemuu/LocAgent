"""Explicit exact route or same-corpus body/dense fusion; renderer cannot reorder."""
from readonly_agent.core import digest
from experiments.retrieval_evidence_v6.retriever import EvidenceRetriever, NOTICE
from experiments.path_retrieval_v4.retriever import is_path_query,path_candidates
from .corpus import Corpus
from .ranking import BodyBM25,fuse,file_projection
from .vectors import CachedDense,QueryVectorMissing,query_key

class PreviewRenderer:
    preview=EvidenceRetriever.preview
    def __init__(self,corpus):
        self.snapshot=corpus.snapshot;self.nodes=corpus.nodes;self.parsed={}
    def render(self,rows):
        text=NOTICE;seen=set();audit=[]
        for rank,row in enumerate(rows,1):
            snippet,record=self.preview(row,rank,seen);text+=snippet+'\n';audit.append(record)
        return text,audit

class HybridRetriever:
    def __init__(self,snapshot,config,*,cache=None,cache_hash=None):
        self.snapshot_id=snapshot.identity;self.config=config;self.corpus=Corpus(snapshot,config.max_chars)
        self.renderer=PreviewRenderer(self.corpus);self.last_audit=None;self.failure=None
        self.lexical=BodyBM25(self.corpus.documents)
        self.dense=None
        if cache is not None:self.dense=CachedDense(cache,self.corpus,config,cache_hash)
        if config.mode!='body_bm25' and self.dense is None:raise ValueError('dense_cache_required')
    def retrieve(self,query):
        if not isinstance(query,str) or not 1<=len(query)<=256 or not query.strip():raise ValueError('invalid_query')
        cfg=self.config;nodes=self.corpus.nodes;lex=[];dense=[];ls={};ds={};scores={};degraded=False;reason=None
        if query in nodes:rows=[{'id':query,'match':'exact_id'}];mode='exact'
        elif is_path_query(query):
            rows=[{'id':r['path'],'match':r['match']} for r in path_candidates(query,[n for n,d in nodes.items() if d['type']=='file'],cfg.top_k)];mode='path'
        elif exact:=sorted(n for n in nodes if ':' in n and n.partition(':')[2]==query):
            rows=[{'id':n,'match':'exact_qualified_name'} for n in exact[:cfg.top_k]];mode='exact'
        else:
            mode=cfg.mode
            if cfg.mode in ('body_bm25','hybrid'):lex,ls=self.lexical.search(query)
            if cfg.mode in ('dense','hybrid'):
                try:dense,ds=self.dense.search(query)
                except QueryVectorMissing:
                    if cfg.fallback!='body_bm25':raise
                    degraded=True;reason='query_vector_not_cached';mode='body_bm25'
                    if cfg.mode=='dense':lex,ls=self.lexical.search(query)
            if mode=='hybrid':ranked,scores=fuse(lex,dense,cfg.rrf_constant,cfg.bm25_weight,cfg.dense_weight)
            elif mode=='dense':ranked=dense;scores=ds
            else:ranked=lex;scores=ls
            rows=[{'id':n,'match':mode} for n in ranked[:cfg.top_k]]
        file_rows=file_projection(ranked if mode in ('hybrid','dense','body_bm25') else [r['id'] for r in rows],cfg.top_k)
        evidence,previews=self.renderer.render(rows)
        meta={'version':'sdk-hybrid-v8-offline-1','snapshot':self.snapshot_id,'corpus':self.corpus.identity,'config_hash':cfg.identity,'algorithm':cfg.algorithm,
              'index_hash':self.dense.identity if self.dense else None,'embedding_kind':'synthetic-fixture' if self.dense else 'none',
              'query_hash':query_key(query),'requested_mode':cfg.mode,'executed_mode':mode,'degraded':degraded,'degradation_reason':reason,
              'lexical_candidates':len(lex),'dense_candidates':len(dense),'membership':len(self.corpus.documents),'excluded_sources':self.corpus.excluded,'file_candidates':file_rows,
              'candidates':[dict(p,bm25_rank=lex.index(p['id'])+1 if p['id'] in lex else None,dense_rank=dense.index(p['id'])+1 if p['id'] in dense else None,bm25_score=ls.get(p['id']),dense_score=ds.get(p['id']),fusion_score=scores.get(p['id']) if mode=='hybrid' else None) for p in previews]}
        self.last_audit=meta
        header=f"Retrieval mode: {mode}; requested: {cfg.mode}; embedding: {meta['embedding_kind']}.\n"
        if degraded:header+='Explicit fallback to body_bm25: query vector not cached.\n'
        if file_rows:header+='File candidates (best entity rank; inspect source to verify): '+', '.join(r['path'] for r in file_rows)+'\n'
        return header+(evidence if rows else 'No locations found.\n')
