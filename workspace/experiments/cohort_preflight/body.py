"""Physical-line body BM25; original preflight artifacts stay unchanged."""
import hashlib,json,re
from pathlib import Path
from readonly_agent.core import digest,encoded
from .entry import checked_file,safe_name
VERSION='source-body-physical-line80-v2'
def lines(text):
    # Keep exact CR, LF and CRLF bytes, including final incomplete line.
    # Unicode separators inside strings/comments are not Python physical lines.
    return re.findall(r'[^\r\n]*(?:\r\n|\r|\n|$)',text)[:-1] if text else []
def chunks(snapshot):
    rows=[]
    for path,text in snapshot.files.items():
        source=lines(text)
        for offset in range(0,len(source),80):
            rows.append({'text':''.join(source[offset:offset+80]),'metadata':{
                'file_path':path,'start_line':offset+1,'end_line':min(offset+80,len(source)),
                'source_sha256':snapshot.hashes[path]}})
    return rows
def build(snapshot,directory):
    import Stemmer
    from llama_index.core.schema import TextNode
    from llama_index.retrievers.bm25 import BM25Retriever
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    rows=chunks(snapshot)
    if not rows:raise ValueError('empty_body_corpus')
    nodes=[TextNode(text=r['text'],metadata=r['metadata'],id_=digest(r),
        excluded_embed_metadata_keys=list(r['metadata']),excluded_llm_metadata_keys=list(r['metadata'])) for r in rows]
    retriever=BM25Retriever.from_defaults(nodes=nodes,similarity_top_k=min(10,len(nodes)),
        stemmer=Stemmer.Stemmer('english'),language='english')
    retriever.persist(str(directory))
    att={'version':VERSION,'snapshot':snapshot.identity,'source_hashes':dict(snapshot.hashes),
         'records_digest':digest(rows),'chunks':len(rows),'upstream_epic_equivalent':False,
         'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir()) if p.is_file()}}
    (directory/'attestation.json').write_bytes(encoded(att))
    return att
def load(snapshot,directory,att_hash):
    from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir
    directory=Path(directory);att=json.loads(checked_file(directory/'attestation.json',att_hash).read_text())
    if att['version']!=VERSION or att['snapshot']!=snapshot.identity or att['source_hashes']!=dict(snapshot.hashes):
        raise ValueError('body_snapshot_or_version_mismatch')
    for n,h in att['artifacts'].items():safe_name(n);checked_file(directory/n,h)
    retriever=build_retriever_from_persist_dir(str(directory));rows=chunks(snapshot)
    restored=[json.loads(x['_node_content']) for x in retriever.corpus]
    if digest(rows)!=att['records_digest'] or [(r['text'],r['metadata']) for r in restored]!=[(r['text'],r['metadata']) for r in rows]:
        raise ValueError('body_corpus_mismatch')
    return retriever,att
def backend(retriever,audit):
    from plugins.location_tools.retriever.bm25_retriever import retrieve_nonempty
    from plugins.location_tools.utils.result_format import QueryResult
    class ExactSnippet(QueryResult):
        def format_output(self,searcher,*,include_source=True):
            # Avoid slicing the original LF-only graph formatter with physical
            # CR/LF indices. Return the attested exact chunk, without reinterpreting it.
            return (f'Found code snippet in file `{self.file_path}`, source lines {self.start_line}-{self.end_line}.\n'
                    +('Source: physical-line body BM25.\n' if include_source else '')
                    +'```\n'+self.exact_text+'\n```\n')
    def retrieve(query_info,include_files=None,similarity_top_k=10):
        rows=retrieve_nonempty(retriever,query_info.term)
        selected=[r for r in rows if not include_files or r.metadata['file_path'] in include_files][:5]
        audit.append({'query':query_info.term,'retrieved':len(rows),'returned':len(selected)})
        result=[]
        for row in selected:
            m=row.metadata
            item=ExactSnippet(query_info=query_info,format_mode='code_snippet',nid=m['file_path'],file_path=m['file_path'],
                start_line=m['start_line'],end_line=m['end_line'],retrieve_src=VERSION)
            item.exact_text=row.text;result.append(item)
        return result
    return retrieve
