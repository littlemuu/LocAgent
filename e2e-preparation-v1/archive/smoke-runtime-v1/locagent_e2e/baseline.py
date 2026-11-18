"""Transport-only adapter for frozen v6/v7; identifier BM25, original preview/finish."""
import ast,json,os
from pathlib import Path
from .common import ROOT
from .baseline_original import CodeAnalyzer,is_test_file
from experiments.retrieval_evidence_v6.retriever import EvidenceRetriever
class CurrentRetriever(EvidenceRetriever):
 def __init__(self,snapshot):
  import bm25s,Stemmer
  self.snapshot=snapshot;self.snapshot_id=snapshot.identity;self.nodes={'/':{'type':'directory'}}
  # Same original analyzer, including __init__ exclusion and last-definition node overwrite.
  for name,source in snapshot.files.items():
   if not name.endswith('.py'):continue
   parts=Path(name).parts[:-1]
   for n in range(1,len(parts)+1):self.nodes.setdefault('/'.join(parts[:n]),{'type':'directory'})
   self.nodes[name]={'type':'file','code':source}
   analyzer=CodeAnalyzer(str(snapshot_root(snapshot)/name))
   try:analyzer.visit(ast.parse(source))
   except (SyntaxError,RecursionError):continue
   for node in analyzer.nodes:self.nodes[name+':'+node['name']]={k:node[k] for k in ('type','code','start_line','end_line')}
  self.searchable=tuple(n for n in self.nodes if not is_test_file(n));self.parsed={};self.last_audit=None
  self.stemmer=Stemmer.Stemmer('english');self.bm=bm25s.BM25()
  tokens=bm25s.tokenize(list(self.searchable),stopwords='english',stemmer=self.stemmer,show_progress=False)
  self.bm.index(tokens,show_progress=False)
 def lexical(self,query):
  import bm25s
  tokens=bm25s.tokenize(query,stemmer=self.stemmer,show_progress=False)
  if not any(tokens.ids):return []
  ids,scores=self.bm.retrieve(tokens,k=min(20,len(self.searchable)),show_progress=False)
  return [self.searchable[int(i)] for i,s in zip(ids[0],scores[0]) if s>0]

def snapshot_root(snapshot):
 # Snapshot deliberately retains only immutable contents; caller sets its source-only root.
 return snapshot.e2e_source_root
