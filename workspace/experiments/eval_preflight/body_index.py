"""Source-only deterministic line chunks, explicitly not upstream EpicSplitter."""
import hashlib
import json
from pathlib import Path
from readonly_agent.core import encoded, digest


def chunks(snapshot, lines_per_chunk=80):
    result = []
    for path, text in snapshot.files.items():
        lines = text.splitlines(keepends=True)
        for start in range(0, len(lines), lines_per_chunk):
            result.append({'text': ''.join(lines[start:start+lines_per_chunk]),
                'metadata': {'file_path': path, 'start_line': start+1,
                             'end_line': min(start+lines_per_chunk, len(lines)),
                             'source_sha256': snapshot.hashes[path]}})
    return result


def build(snapshot, directory):
    import Stemmer
    from llama_index.core.schema import TextNode
    from llama_index.retrievers.bm25 import BM25Retriever
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=False)
    records = chunks(snapshot)
    nodes = [TextNode(text=r['text'], metadata=r['metadata'], id_=digest(r),
                     excluded_embed_metadata_keys=list(r['metadata']),
                     excluded_llm_metadata_keys=list(r['metadata'])) for r in records]
    retriever = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=min(10,len(nodes)),
        stemmer=Stemmer.Stemmer('english'), language='english')
    retriever.persist(str(directory))
    attestation = {'version':'source-body-line80-v1','snapshot':snapshot.identity,
        'source_hashes':dict(snapshot.hashes),'records_digest':digest(records),'chunks':len(records),
        'all_allowlisted_python_including_tests':True,
        'upstream_epic_splitter_equivalent':False,
        'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir()) if p.is_file()}}
    (directory/'attestation.json').write_bytes(encoded(attestation))
    return attestation


def load(snapshot, directory, attestation_hash):
    from plugins.location_tools.retriever.bm25_retriever import build_retriever_from_persist_dir
    directory = Path(directory)
    if directory.is_symlink(): raise ValueError('linked_body_index')
    p=directory/'attestation.json'
    assert hashlib.sha256(p.read_bytes()).hexdigest()==attestation_hash
    att=json.loads(p.read_text())
    assert att['snapshot']==snapshot.identity and att['source_hashes']==dict(snapshot.hashes)
    for name,h in att['artifacts'].items():
        f=directory/name
        assert f.parent==directory and not f.is_symlink() and hashlib.sha256(f.read_bytes()).hexdigest()==h
    retriever=build_retriever_from_persist_dir(str(directory))
    records=chunks(snapshot)
    assert digest(records)==att['records_digest']
    restored=[json.loads(x['_node_content']) for x in retriever.corpus]
    assert [(x['text'],x['metadata']) for x in restored]==[(x['text'],x['metadata']) for x in records]
    return retriever,att


def backend(retriever, audit):
    from plugins.location_tools.retriever.bm25_retriever import retrieve_nonempty
    from plugins.location_tools.utils.result_format import QueryResult
    def retrieve(query_info, include_files=None, similarity_top_k=10):
        rows = retrieve_nonempty(retriever, query_info.term)
        selected=[r for r in rows if not include_files or r.metadata['file_path'] in include_files][:5]
        audit.append({'query':query_info.term,'retrieved':len(rows),
                      'delivered_candidates':[dict(r.metadata) for r in selected]})
        return [QueryResult(query_info=query_info,format_mode='code_snippet',
            nid=r.metadata['file_path'],file_path=r.metadata['file_path'],
            start_line=r.metadata['start_line'],end_line=r.metadata['end_line'],
            retrieve_src='Source body BM25, fixed 80-line chunks; not entity-ID ranking.') for r in selected]
    return retrieve
