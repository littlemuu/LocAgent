from query_contract import validate_retrieval_query
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
        self.corpus=corpus;self.snapshot=corpus.snapshot;self.nodes=dict(corpus.nodes);self.parsed={}
    def render(self,rows):
        text=NOTICE;seen=set();audit=[]
        for rank,row in enumerate(rows,1):
            entity=row['id'];original=self.corpus.nodes[entity]
            definitions=[self.corpus.definitions[d] for d in original.get('definitions',[])]
            chosen=row.get('definition_id')
            self.nodes[entity]=dict(original,**{k:v for k,v in self.corpus.definitions[chosen].items() if k in ('type','start_line','end_line')}) if chosen else original
            snippet,record=self.preview(row,rank,seen)
            if len(definitions)>1:
                ranges=', '.join(str(d['start_line'])+'-'+str(d['end_line']) for d in definitions[:12])
                snippet='Entity has '+str(len(definitions))+' source definitions; ranges: '+ranges+(' (further ranges omitted)' if len(definitions)>12 else '')+'. The displayed definition is selected by retrieval evidence; use read_file to inspect alternatives.\n'+snippet
            record.update(definition_id=chosen,definition_spans=[{'definition_id':d['id'],'start_line':d['start_line'],'end_line':d['end_line'],'type':d['type']} for d in definitions],definition_selection=row.get('definition_selection'))
            text+=snippet+'\n';audit.append(record)
        return text,audit

class HybridRetriever:
    def __init__(self,snapshot,config,*,cache=None,cache_hash=None):
        self.snapshot_id=snapshot.identity;self.config=config;self.corpus=Corpus(snapshot,config.max_chars)
        self.renderer=PreviewRenderer(self.corpus);self.last_audit=None;self.failure=None
        self.lexical=BodyBM25(self.corpus.documents)
        self.dense=None
        if cache is not None:self.dense=CachedDense(cache,self.corpus,config,cache_hash)
        if config.mode!='body_bm25' and self.dense is None:raise ValueError('dense_cache_required')
    def choose_definition(self,entity,mode):
        options=self.corpus.nodes[entity].get('definitions',[])
        if not options:return None,'file'
        pools=[]
        for scores,positive in ((self.lexical.last_scores,True),(self.dense.last_scores if self.dense else [],False)):
            maximum={}
            for doc,value in zip(self.corpus.documents,scores):
                if doc.entity!=entity or positive and value<=0:continue
                maximum[doc.definition_id]=max(maximum.get(doc.definition_id,float('-inf')),value)
            pools.append(sorted(maximum,key=lambda d:(-maximum[d],d)))
        if mode=='hybrid':ranked,_=fuse(*pools);strategy='within_entity_weighted_rrf'
        elif mode=='dense':ranked=pools[1];strategy='max_dense_definition'
        elif mode=='body_bm25':ranked=pools[0];strategy='max_body_bm25_definition'
        else:ranked=[];strategy='source_order_with_ambiguity_disclosed'
        return (ranked[0] if ranked else options[0]),strategy

    def retrieve(self,query):
        validate_retrieval_query(query)
        self.lexical.last_scores=[]
        if self.dense:self.dense.last_scores=[]
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
        for row in rows:
            row['definition_id'],row['definition_selection']=self.choose_definition(row['id'],mode)
        evidence,previews=self.renderer.render(rows)
        meta={'version':'sdk-hybrid-v8.1-offline-1','snapshot':self.snapshot_id,'corpus':self.corpus.identity,'config_hash':cfg.identity,'algorithm':cfg.algorithm,
              'index_hash':self.dense.identity if self.dense else None,'embedding_kind':'synthetic-fixture' if self.dense else 'none',
              'query_hash':query_key(query),'requested_mode':cfg.mode,'executed_mode':mode,'degraded':degraded,'degradation_reason':reason,
              'lexical_candidates':len(lex),'dense_candidates':len(dense),'membership':len(self.corpus.documents),'excluded_sources':self.corpus.excluded,'file_candidates':file_rows,
              'candidates':[dict(p,bm25_rank=lex.index(p['id'])+1 if p['id'] in lex else None,dense_rank=dense.index(p['id'])+1 if p['id'] in dense else None,bm25_score=ls.get(p['id']),dense_score=ds.get(p['id']),fusion_score=scores.get(p['id']) if mode=='hybrid' else None) for p in previews]}
        self.last_audit=meta
        header=f"Retrieval mode: {mode}; requested: {cfg.mode}; embedding: {meta['embedding_kind']}.\n"
        if degraded:header+='Explicit fallback to body_bm25: query vector not cached.\n'
        if file_rows:header+='File candidates (best entity rank; inspect source to verify): '+', '.join(r['path'] for r in file_rows)+'\n'
        return header+(evidence if rows else 'No locations found.\n')
