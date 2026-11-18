"""AST only. Preserve snapshot bytes, declared scope and physical source locations."""
import ast
from dataclasses import dataclass
from readonly_agent.core import digest
from experiments.retrieval_evidence_v6.retriever import ast_entities
from experiments.cohort_preflight.body import lines

@dataclass(frozen=True)
class Document:
    id: str
    entity: str
    path: str
    start: int
    end: int
    part: int
    text: str

class Corpus:
    def __init__(self,snapshot,max_chars=12000):
        if type(max_chars) is not int or not 32 <= max_chars <= 12000:raise ValueError('invalid_chunk_size')
        self.snapshot=snapshot;self.nodes={};docs=[];self.excluded=[]
        for path,source in snapshot.files.items():
            if not path.endswith('.py'):
                self.excluded.append({'path':path,'reason':'non_python'});continue
            self.nodes[path]={'type':'file','code':source}
            _,entries=ast_entities(source);physical=lines(source)
            for (name,start,end),node in entries.items():
                entity=path+':'+name
                if entity in self.nodes:raise ValueError('ambiguous_duplicate_entity_definition')
                self.nodes[entity]={'type':'class' if isinstance(node,ast.ClassDef) else 'function','start_line':start,'end_line':end}
                if isinstance(node,ast.ClassDef):continue
                first=min([start]+[d.lineno for d in node.decorator_list]);part=0;buffer='';a=first;last=first
                def emit(text,lo,hi):
                    nonlocal part
                    if text.strip():
                        body=entity+'\n'+text
                        identity=digest([snapshot.identity,path,name,lo,hi,part,body,max_chars,'function-physical-lines-v8'])
                        docs.append(Document(identity,entity,path,lo,hi,part,body));part+=1
                        if len(docs)>20000:raise ValueError('corpus_chunk_limit')
                for n in range(first,end+1):
                    line=physical[n-1]
                    if buffer and len(buffer)+len(line)>max_chars:emit(buffer,a,last);buffer=''
                    while len(line)>max_chars:emit(line[:max_chars],n,n);line=line[max_chars:]
                    if not buffer:a=n
                    buffer+=line;last=n
                emit(buffer,a,last)
        self.documents=tuple(docs)
        self.identity=digest({'snapshot':snapshot.identity,'policy':'all-allowlisted-python-functions-v8','max_chars':max_chars,'documents':[d.id for d in docs],'excluded':self.excluded})
