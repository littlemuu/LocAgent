"""Offline retrieval primitives; no implicit model, database or network access.

Callers supply statically verified snapshot bytes. Not wired into the agent yet.
"""
import ast
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
from typing import Protocol


def key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class Version:
    repo: str
    commit: str
    model: str
    chunker: str = 'python-ast-lines-v2'
    max_chars: int = 2000

    def __post_init__(self):
        if type(self.max_chars) is not int or not 32 <= self.max_chars <= 16000:
            raise ValueError('Invalid versioned chunk size')
        if not re.fullmatch(r'[a-z0-9_.-]+/[a-z0-9_.-]+', self.repo):
            raise ValueError('Canonical repository identity required')
        if not re.fullmatch(r'[a-f0-9]{40}', self.commit) or not self.model or not self.chunker:
            raise ValueError('Fixed commit and explicit model/chunker versions required')


@dataclass(frozen=True)
class Chunk:
    version: Version
    path: str
    entity: str
    kind: str
    start: int
    end: int
    part: int
    text: str

    @property
    def content_hash(self):
        return hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def vector_key(self):
        # Only identical embedding inputs share vectors. Membership is separate.
        return key(self.version.model, self.version.chunker, self.version.max_chars, self.content_hash)

    @property
    def id(self):
        return key(self.version.repo, self.version.commit, self.version.model,
                   self.version.chunker, self.version.max_chars, self.path, self.entity, self.kind,
                   self.start, self.end, self.part, self.content_hash)


BLOCKED = {'.git', '.venv', 'venv', 'env', 'node_modules', '__pycache__',
           'build', 'dist', 'outputs', 'generated', 'site-packages'}
CONFIG_NAMES = {'config.py', 'settings.py', 'secrets.py', 'credentials.py', 'local_settings.py'}


def allowed(path):
    if not isinstance(path, str):return False
    p = PurePosixPath(path)
    return (isinstance(path, str) and 0 < len(path) <= 512 and
            str(p) == path and not p.is_absolute() and
            not any(x in ('.', '..') or x.lower() in BLOCKED or x.startswith('.') for x in p.parts)
            and not any(ord(x) < 32 for x in path) and '\\' not in path and ':' not in path
            and p.suffix == '.py' and p.name.lower() not in CONFIG_NAMES)


def chunk_snapshot(files: dict[str, bytes], version: Version, *, max_chars=None,
                   max_files=3000, max_bytes=32*1024*1024, max_chunks=20000):
    """AST regions plus bounded line windows; never imports snapshot code.

    Large individual lines split into character slices with the same line number.
    Classes intentionally overlap method chunks; RRF deduplicates chunk IDs only.
    Filename filtering is not a secret scanner; use verified public snapshots.
    """
    if max_chars is None:max_chars=version.max_chars
    if max_chars != version.max_chars:
        raise ValueError('Chunk size must match version identity')
    if max_chars < 32 or min(max_files, max_bytes, max_chunks) < 1:
        raise ValueError('Invalid chunk limits')
    if len(files) > max_files or sum(len(b) for b in files.values()) > max_bytes:
        raise ValueError('Snapshot limit exceeded')
    chunks = []
    for path, raw in sorted(files.items()):
        if not allowed(path) or b'\0' in raw:
            continue
        if len(raw) > 1024*1024:
            raise ValueError('File limit exceeded')
        try:
            text = raw.decode('utf-8'); tree = ast.parse(text)
        except (UnicodeError, SyntaxError):
            raise ValueError('Unsupported Python source') from None
        if sum(1 for _ in ast.walk(tree)) > 100000:
            raise ValueError('AST limit exceeded')
        # AST line numbers count LF, CRLF and CR, not string control characters.
        lines = re.findall(r'[^\r\n]*(?:\r\n|\r|\n|$)', text)
        if lines and lines[-1] == '':lines.pop()
        regions = []
        def visit(body, prefix=''):
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = prefix + node.name
                    start = min([node.lineno]+[d.lineno for d in node.decorator_list])
                    regions.append((start, node.end_lineno, name,
                                    'class' if isinstance(node, ast.ClassDef) else 'function'))
                    visit(node.body, name+'.')
                else:
                    # Traverse lexical control-flow scopes without inventing entities.
                    # ExceptHandler/match_case are AST containers, not ast.stmt.
                    visit((child for child in ast.iter_child_nodes(node)
                           if not isinstance(child, ast.expr)), prefix)
        visit(tree.body)
        # Module-level statements not already contained in top-level definitions.
        covered = set()
        for start,end,entity,_ in regions:
            if '.' not in entity:covered.update(range(start,end+1))
        start=None
        for n in range(1,len(lines)+2):
            if n <= len(lines) and n not in covered:
                if start is None:start=n
            elif start is not None:
                regions.append((start,n-1,'','module'));start=None
        for start,end,entity,kind in sorted(regions):
            buffer='';first=start;last=start;part=0
            def emit(content, a, b):
                nonlocal part
                if content.strip():
                    chunks.append(Chunk(version,path,entity,kind,a,b,part,content));part+=1
                    if len(chunks)>max_chunks:raise ValueError('Chunk limit exceeded')
            for n in range(start,end+1):
                line=lines[n-1]
                if buffer and len(buffer)+len(line)>max_chars:
                    emit(buffer,first,last);buffer=''
                while len(line)>max_chars:
                    emit(line[:max_chars],n,n);line=line[max_chars:]
                if not buffer:first=n
                buffer+=line;last=n
            emit(buffer,first,last)
    return tuple(chunks)


class Embeddings(Protocol):
    model: str
    dimensions: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class RetrievalError(ValueError): pass
class IndexNotReady(RetrievalError): pass
class ProviderError(RetrievalError): pass


def vector(value, dimensions):
    if len(value)!=dimensions or dimensions<1 or any(type(x) not in (int,float) or not math.isfinite(x) for x in value):
        raise ProviderError('Invalid embedding shape or values')
    norm=math.sqrt(sum(x*x for x in value))
    if not math.isfinite(norm) or norm==0:raise ProviderError('Invalid embedding norm')
    return tuple(x/norm for x in value)


def embed(provider, texts):
    try:
        result=provider.embed(texts)
        if len(result)!=len(texts):raise ValueError()
        return [vector(v,provider.dimensions) for v in result]
    except Exception:
        raise ProviderError('Embedding provider failed; no index published') from None


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


@dataclass(frozen=True)
class ExactIndex:
    version: Version
    dimensions: int
    rows: tuple

    @classmethod
    def build(cls, version, chunks, provider, cache=None):
        if provider.model != version.model:raise ValueError('Model version mismatch')
        chunks=tuple(chunks)
        if any(c.version!=version for c in chunks) or len({c.id for c in chunks})!=len(chunks):
            raise ValueError('Mixed or duplicate version membership')
        cached={} if cache is None else cache
        pending={};rows=[]
        for c in chunks:
            k=key(c.vector_key,provider.dimensions)
            if k not in cached and k not in pending:
                pending[k]=embed(provider,[c.text])[0]
            value=vector(cached[k] if k in cached else pending[k],provider.dimensions)
            rows.append((c,value))
        # A failed build never exposes a partial index or updates the cache.
        if cache is not None:cache.update(pending)
        return cls(version,provider.dimensions,tuple(rows))

    def search(self, query, version, provider, k=10):
        if version!=self.version or provider.model!=version.model or provider.dimensions!=self.dimensions:
            raise ValueError('Index version mismatch')
        if k<1:raise ValueError('Positive k required')
        if not query.strip():return []
        q=embed(provider,[query])[0]
        hits=[Hit(c,sum(x*y for x,y in zip(q,v))) for c,v in self.rows]
        return sorted(hits,key=lambda h:(-h.score,h.chunk.id))[:k]


def rrf(rankings, *, k=10, constant=60):
    if k<1 or constant<1:raise ValueError('Positive RRF bounds required')
    scores={};chunks={};version=None
    for ranking in rankings:
        seen=set()
        for rank,hit in enumerate(ranking,1):
            c=hit.chunk
            if version is None:version=c.version
            if c.version!=version:raise ValueError('Mixed retrieval versions')
            if c.id in seen:continue
            seen.add(c.id);chunks[c.id]=c;scores[c.id]=scores.get(c.id,0)+1/(constant+rank)
    return [Hit(chunks[i],scores[i]) for i in sorted(scores,key=lambda i:(-scores[i],i))[:k]]


@dataclass(frozen=True)
class SearchConfig:
    mode: str = 'bm25'
    fallback: str = 'error'
    k: int = 10

    def __post_init__(self):
        if self.mode not in ('bm25','dense','hybrid') or self.fallback not in ('error','bm25') or self.k<1:
            raise ValueError('Invalid retrieval config')


@dataclass(frozen=True)
class SearchResult:
    hits: object
    mode: str
    degraded: bool = False
    reason: str | None = None


def search(query, version, lexical, *, index=None, provider=None, config=SearchConfig()):
    # Identity-preserving default adapter: does not call dense or alter BM25 values.
    if config.mode=='bm25':return SearchResult(lexical(query),'bm25')
    try:
        if index is None or provider is None:raise IndexNotReady('Dense index unavailable')
        dense=index.search(query,version,provider,config.k)
    except (IndexNotReady,ProviderError) as exc:
        if config.fallback!='bm25':raise
        return SearchResult(lexical(query),'bm25',True,type(exc).__name__)
    if config.mode=='dense':return SearchResult(dense,'dense')
    lexical_hits=lexical(query)
    return SearchResult(rrf([lexical_hits,dense],k=config.k),'hybrid')
