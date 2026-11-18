"""Pure math matching the legacy max-entity, positive BM25 and weighted RRF rules."""
import math

def entity_ranking(documents,scores,positive_only=False):
    if len(documents)!=len(scores):raise ValueError('score_membership_mismatch')
    best={}
    for doc,value in zip(documents,scores):
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('invalid_score')
        if positive_only and value<=0:continue
        best[doc.entity]=max(best.get(doc.entity,-math.inf),float(value))
    return sorted(best,key=lambda x:(-best[x],x)),best

def fuse(lexical,dense,constant=60,bm25_weight=1,dense_weight=2):
    if len(set(lexical))!=len(lexical) or len(set(dense))!=len(dense):raise ValueError('deduplicate_entities_before_fusion')
    if any(type(x) is not int or x<=0 for x in (constant,bm25_weight,dense_weight)):raise ValueError('invalid_fusion_parameters')
    scores={}
    for ranking,weight in ((lexical,bm25_weight),(dense,dense_weight)):
        for rank,entity in enumerate(ranking,1):scores[entity]=scores.get(entity,0)+weight/(constant+rank)
    return sorted(scores,key=lambda x:(-scores[x],x)),scores

def file_projection(ranking,top_k):
    """Project full entity order onto files by each file's best function rank."""
    rows=[];seen=set()
    for rank,entity in enumerate(ranking,1):
        path=entity.partition(':')[0]
        if path in seen:continue
        seen.add(path);rows.append({'path':path,'best_entity':entity,'entity_rank':rank})
        if len(rows)==top_k:break
    return rows

class BodyBM25:
    def __init__(self,documents):
        import bm25s,Stemmer
        self.docs=documents;self.stemmer=Stemmer.Stemmer('english');self.bm=None
        self.tokenize=lambda texts:bm25s.tokenize(texts,stemmer=self.stemmer,stopwords='en',show_progress=False)
        if documents:
            tokens=self.tokenize([d.text for d in documents])
            if any(tokens.ids):
                self.bm=bm25s.BM25(k1=1.5,b=.75,method='lucene');self.bm.index(tokens,show_progress=False)
    def search(self,query):
        if self.bm is None:return [],{}
        tokens=self.tokenize(query)
        if not any(tokens.ids):return [],{}
        ids,scores=self.bm.retrieve(tokens,k=len(self.docs),show_progress=False)
        ordered=[0.]*len(self.docs)
        for i,score in zip(ids[0],scores[0]):ordered[int(i)]=float(score)
        return entity_ranking(self.docs,ordered,True)
