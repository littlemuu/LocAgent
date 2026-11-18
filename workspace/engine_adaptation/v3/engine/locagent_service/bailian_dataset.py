"""Frozen, manually authored development set. Never imports repository code."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from locagent_service import bailian_contract as c
from locagent_service.bailian_experiment import COMMIT, REPO
from locagent_service.rag_offline import Version, chunk_snapshot

FILES = tuple('src/itsdangerous/' + x + '.py' for x in ('encoding','signer','timed','url_safe'))
VERSION = Version(REPO, COMMIT, c.MODEL, max_chars=12000)
LABELS = [
    ('Where does text become UTF-8 bytes while byte input is returned unchanged?', 'encoding', 'want_bytes'),
    ('Where is trailing padding removed from URL-safe base64 output?', 'encoding', 'base64_encode'),
    ('Where is missing padding restored before decoding URL-safe data?', 'encoding', 'base64_decode'),
    ('Where are leading zero bytes stripped from a packed 64-bit integer?', 'encoding', 'int_to_bytes'),
    ('Where is short binary input left-padded to eight bytes before unpacking an integer?', 'encoding', 'bytes_to_int'),
    ('Where does the choice of key derivation scheme select concatenation, keyed hashing, or the unchanged key?', 'signer', 'Signer.derive_key'),
    ("Where are older secret keys tried in reverse order when checking a value's authentication tag?", 'signer', 'Signer.verify_signature'),
    ('Where is a missing separator rejected before splitting a value from its authentication tag?', 'signer', 'Signer.unsign'),
    ('Where is compression used only when it saves enough space to cover an extra marker?', 'url_safe', 'URLSafeSerializerMixin.dump_payload'),
    ('Where does a leading dot trigger decompression after URL-safe decoding?', 'url_safe', 'URLSafeSerializerMixin.load_payload'),
]


def questions():
    return [{'id':f'q{i+1:02d}', 'text':text,
             'relevant_entities':['src/itsdangerous/'+file+'.py:'+entity]}
            for i,(text,file,entity) in enumerate(LABELS)]


def members(files):
    if set(files) != set(FILES):
        raise ValueError('Fixed four-file scope required')
    return tuple(ch for ch in chunk_snapshot(files, VERSION) if ch.kind == 'function')


def documents(chunks):
    # Include the exact same path/entity/code text in BM25 and embedding inputs.
    return [{'id':ch.id, 'entity':ch.path+':'+ch.entity, 'path':ch.path,
             'text':f'{ch.path}:{ch.entity}\n{ch.text}'} for ch in chunks]


def blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def validate_dataset(m):
    if m['repo'] != REPO or m['commit'] != COMMIT or m['questions'] != questions():
        raise ValueError('Dataset differs from reviewed development set')
    if m['chunker'] != asdict(VERSION) or m['selection'] != 'all-function-regions-in-four-fixed-files-including-overloads-v1':
        raise ValueError('Chunking or membership policy changed')
    files = {name: text.encode('utf-8') for name,text in m['source_files'].items()}
    if m['git_blobs'] != {name:blob(raw) for name,raw in files.items()}:
        raise ValueError('Source Git blob mismatch')
    if m['documents'] != documents(members(files)):
        raise ValueError('Source/chunk membership mismatch')
    labels = {x['entity'] for x in m['documents']}
    for q in m['questions']:
        if not set(q['relevant_entities']) <= labels:
            raise ValueError('Label outside membership')
        if any(label.split('.')[-1].lower() in q['text'].lower() for label in q['relevant_entities']):
            raise ValueError('Target symbol leaked into question')


def prepare(root):
    from locagent_service.public_repo import fetch
    from locagent_service.bailian_live import APPROVAL, ORIGIN, WORKSPACE, engine_hashes
    # Read only cached public source; independently verify each blob against the
    # exact GitHub commit tree. No old engine manifest/ledger is loaded or weakened.
    candidates=list((root/'outputs/public-single-20261015-resume1/sources').glob('public-index-*/repo'))
    if len(candidates)!=1:
        raise ValueError('Ambiguous cached public snapshot')
    snapshot=candidates[0]
    files={}
    for name in FILES:
        path=snapshot/name
        if any(p.is_symlink() for p in [path,*path.parents]) or path.stat().st_size>1024*1024:
            raise ValueError('Unsafe source file')
        files[name]=path.read_bytes()
    # Use a bounded fixed-commit codeload archive. GitHub's unauthenticated
    # tree API returned 403 during admission; do not retry or infer its cause.
    import gzip, io, tarfile
    from pathlib import PurePosixPath
    archive=fetch('codeload.github.com','/'+REPO+'/tar.gz/'+COMMIT)
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as zipped:
        expanded=zipped.read(32*1024*1024+1)
    if len(expanded)>32*1024*1024:raise ValueError('Archive expanded limit')
    found={};seen=set()
    with tarfile.open(fileobj=io.BytesIO(expanded),mode='r:') as tar:
        for number,member in enumerate(tar):
            path=PurePosixPath(member.name)
            if number>=3000 or len(member.name)>512 or len(path.parts)>30:
                raise ValueError('Archive size limit')
            if (not path.parts or path.parts[0]!='itsdangerous-'+COMMIT or path.is_absolute()
                or '..' in path.parts or '\\' in member.name or any(ord(x)<32 for x in member.name)
                or member.name in seen or not (member.isdir() or member.isfile())):
                raise ValueError('Archive layout rejected')
            seen.add(member.name)
            if member.size>1024*1024:raise ValueError('Archive file limit')
            name=PurePosixPath(*path.parts[1:]).as_posix()
            if member.isfile() and name in FILES:
                raw=tar.extractfile(member).read(1024*1024+1)
                if raw!=files[name]:raise ValueError('Cached source differs from fixed-commit archive')
                found[name]=raw
    if set(found)!=set(FILES):raise ValueError('Archive missing selected source')
    expected={name:blob(raw) for name,raw in files.items()}
    provenance={'method':'pinned-HTTPS-fixed-commit-codeload-byte-comparison',
                'archive_sha256':hashlib.sha256(archive).hexdigest(),
                'github_tree_attempt_http_status':403,
                'independent_git_tree_verification':False}
    docs=documents(members(files)); qs=questions()
    from importlib.metadata import version
    manifest={'version':1,'approval':APPROVAL,'repo':REPO,'commit':COMMIT,
              'endpoint':c.endpoint(WORKSPACE,ORIGIN),'model':c.MODEL,'dimensions':1024,
              'parameters':c.request(['x'],'query')['parameters'],
              'document_parameters':c.request(['x'],'document')['parameters'],
              'preprocessing':'path-colon-symbol-newline-verbatim-code-v1',
              'chunker':asdict(VERSION),'selection':'all-function-regions-in-four-fixed-files-including-overloads-v1',
              'source_files':{name:raw.decode('utf-8') for name,raw in files.items()},'git_blobs':expected,
              'provenance':provenance,
              'documents':docs,'questions':qs,'engine_files':engine_hashes(root),
              'budget_cny':'1','reservation_cny':str(c.planned_cost(len(docs),len(qs))),
              'evaluation':'manually-constructed-development-set-not-blind',
              'package_versions':{name:version(name) for name in ('bm25s','PyStemmer','psycopg')},
              'retrieval':{'bm25':'bm25s-lucene-k1=1.5-b=0.75-english-stemmer',
                           'dense':'exact-cosine-max-chunk-per-entity',
                           'hybrid':'entity-RRF-k=60-full-positive-bm25-plus-full-dense',
                           'cutoffs':[1,3,5]}}
    validate_dataset(manifest)
    target=root/'outputs/bailian-frozen-manifest.json'
    with target.open('xb') as out:
        out.write(c.canonical(manifest));out.flush()
        import os
        os.fsync(out.fileno())
    return {'manifest_sha256':hashlib.sha256(c.canonical(manifest)).hexdigest(),
            'documents':len(docs),'questions':len(qs),'reservation_cny':manifest['reservation_cny']}
