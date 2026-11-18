"""Opt-in graph-module retriever adapter. No HTTP configuration or real embeddings."""
from types import SimpleNamespace
from locagent_service.rag_offline import ExactIndex, Hit, SearchConfig, rrf, search


class GraphModuleRetriever:
    def __init__(self, lexical, version, chunks, graph_nodes, *, index=None,
                 provider=None, config=SearchConfig()):
        self.lexical=lexical;self.version=version;self.index=index
        self.provider=provider;self.config=config;self.stemmer=lexical.stemmer
        self.graph_nodes=frozenset(graph_nodes);self.members={};self.last_diagnostics=None
        for c in chunks:
            if c.version!=version:raise ValueError('Mixed graph retrieval versions')
            nid=c.path+(':'+c.entity if c.entity else '')
            if nid in self.graph_nodes:self.members.setdefault(nid,[]).append(c)
        self.by_id={c.id:nid for nid,cs in self.members.items() for c in cs}

    def validate_task(self, task):
        if (task['repo'],task['base_commit'])!=(self.version.repo,self.version.commit):
            raise ValueError('Retriever/task version mismatch')

    def retrieve(self, query):
        if self.config.mode=='bm25':return self.lexical.retrieve(query)
        def entity_hits(nodes):
            # Normalize each ranking to graph entities before fusion and top-k.
            result=[];seen=set()
            for nid, score in nodes:
                if nid in seen:continue
                seen.add(nid)
                result.append(Hit(self.members[nid][0], score))
            return result

        # ExactIndex already scores all rows. Retain them until entity dedup so
        # multiple parts cannot crowd other entities out of the candidate set.
        candidate_k=max(self.config.k,len(self.index.rows)) if isinstance(self.index,ExactIndex) else self.config.k
        result=search(query,self.version,self.lexical.retrieve,index=self.index,
                      provider=self.provider,config=SearchConfig('dense',self.config.fallback,candidate_k))
        self.last_diagnostics={'mode':result.mode if result.degraded else self.config.mode,
                               'degraded':result.degraded,'reason':result.reason}
        if result.degraded:return result.hits
        dense=[]
        for hit in result.hits:
            nid=self.by_id.get(hit.chunk.id)
            if nid is None:raise ValueError('Candidate is outside graph membership')
            dense.append((nid,hit.score))
        dense=entity_hits(dense)
        if self.config.mode=='hybrid':
            lexical=entity_hits((node.text,node.score) for node in self.lexical.retrieve(query)
                                if node.score>0 and node.text in self.members)
            ranked=rrf([lexical,dense],k=self.config.k)
        else:
            ranked=dense[:self.config.k]
        return [SimpleNamespace(text=self.by_id[hit.chunk.id],score=1.0/(rank+1))
                for rank,hit in enumerate(ranked)]
