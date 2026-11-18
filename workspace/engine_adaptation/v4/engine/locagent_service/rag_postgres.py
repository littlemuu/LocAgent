"""Opt-in persistent exact-vector adapter. No provider transport or automatic DDL."""
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4
import json
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from locagent_service.rag_offline import Version, Hit, IndexNotReady, embed, key, vector


class BuildConflict(ValueError): pass


@dataclass(frozen=True)
class BuildSpec:
    version: Version
    dimensions: int
    chunks: tuple

    def __post_init__(self):
        if type(self.dimensions) is not int or not 1 <= self.dimensions <= 2000:
            raise ValueError('Explicit dimensions in 1..2000 required')
        if not isinstance(self.chunks,tuple) or not 1 <= len(self.chunks) <= 20000:
            raise ValueError('Bounded immutable membership required')
        if any(c.version != self.version for c in self.chunks) or len({c.id for c in self.chunks}) != len(self.chunks):
            raise ValueError('Mixed or duplicate membership')

    @property
    def identity(self):
        return key('pg-exact-entity-v1',asdict(self.version),self.dimensions,sorted(c.id for c in self.chunks))


def vector_text(value, dimensions):
    return json.dumps(vector(value,dimensions),allow_nan=False,separators=(',',':'))


class PgVectorStore:
    def __init__(self, settings, *, enabled=False, connect=None):
        if enabled is not True or not settings.schema.startswith('public_preview_'):
            raise ValueError('Explicit isolated vector preview required')
        self.settings=settings
        self.builds=sql.Identifier(settings.schema,'rag_vector_builds')
        self.rows=sql.Identifier(settings.schema,'rag_vector_rows')
        self._connect=connect

    def connect(self):
        if self._connect is not None:return self._connect()
        return psycopg.connect(self.settings.database_url,row_factory=dict_row,connect_timeout=3,
            options='-c statement_timeout=5000 -c lock_timeout=1000',application_name='locagent-vector-preview')

    def initialize(self):
        """Explicit operator action only; never creates/installs the extension."""
        with self.connect() as c:
            present=c.execute("SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector' AND n.nspname='public'").fetchone()
            if not present:raise IndexNotReady('Operator-installed public.vector extension required')
            c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(self.settings.schema+':vector-init',))
            source=Path(__file__).with_name('migrations')/'004_vector_preview.sql'
            c.execute(sql.SQL(source.read_text()).format(schema=sql.Identifier(self.settings.schema)))

    def begin(self,spec,*,lease_seconds=120):
        if type(lease_seconds) is not int or not 5 <= lease_seconds <= 600:raise ValueError('Invalid lease')
        token=uuid4()
        with self.connect() as c:
            # Serialize same-build admission before INSERT: ON CONFLICT(build_key)
            # does not arbitrate the separate (build_key,dimensions) unique index.
            # Transaction scope releases this lock on commit AND rollback.
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                (self.settings.schema+':vector-build:'+spec.identity,))
            row=c.execute(sql.SQL('''INSERT INTO {} AS b (build_key,version,dimensions,state,token,lease_until)
                VALUES (%s,%s,%s,'building',%s,clock_timestamp()+%s*interval '1 second')
                ON CONFLICT(build_key) DO UPDATE SET state='building',token=EXCLUDED.token,
                lease_until=EXCLUDED.lease_until
                WHERE b.state IN ('failed','cancelled') OR (b.state='building' AND b.lease_until<=clock_timestamp())
                RETURNING token''').format(self.builds),
                (spec.identity,Jsonb(asdict(spec.version)),spec.dimensions,token,lease_seconds)).fetchone()
            if row is None:raise BuildConflict('Build already active or ready')
        return token

    def _fence(self,c,spec,token):
        row=c.execute(sql.SQL("SELECT build_key FROM {} WHERE build_key=%s AND token=%s AND state='building' AND lease_until>clock_timestamp() FOR UPDATE").format(self.builds),(spec.identity,token)).fetchone()
        if row is None:raise BuildConflict('Build claim lost or expired')

    def publish(self,spec,token,values):
        # All embedding work happens outside this transaction. No partially visible rows.
        if len(values)!=len(spec.chunks):raise ValueError('Complete vector membership required')
        encoded=[vector_text(v,spec.dimensions) for v in values]
        with self.connect() as c:
            self._fence(c,spec,token)
            c.execute(sql.SQL('DELETE FROM {} WHERE build_key=%s').format(self.rows),(spec.identity,))
            with c.cursor() as cur:
                cur.executemany(sql.SQL('INSERT INTO {} (build_key,dimensions,chunk_id,entity_id,embedding) VALUES (%s,%s,%s,%s,%s::public.vector)').format(self.rows),
                    [(spec.identity,spec.dimensions,ch.id,ch.path+(':'+ch.entity if ch.entity else ''),v) for ch,v in zip(spec.chunks,encoded)])
            row=c.execute(sql.SQL("UPDATE {} SET state='ready',lease_until=NULL WHERE build_key=%s AND token=%s AND state='building' AND lease_until>clock_timestamp() RETURNING build_key").format(self.builds),(spec.identity,token)).fetchone()
            if row is None:raise BuildConflict('Publication lease expired; transaction rolls back')

    def terminate(self,spec,token,*,cancelled=False):
        with self.connect() as c:
            self._fence(c,spec,token)
            c.execute(sql.SQL('UPDATE {} SET state=%s,lease_until=NULL WHERE build_key=%s AND token=%s').format(self.builds),('cancelled' if cancelled else 'failed',spec.identity,token))

    def status(self,spec):
        try:
            with self.connect() as c:
                row=c.execute(sql.SQL('SELECT state,lease_until FROM {} WHERE build_key=%s').format(self.builds),(spec.identity,)).fetchone()
            return row
        except psycopg.Error:
            raise IndexNotReady('Vector storage unavailable') from None

    def query(self,spec,value,k):
        if type(k) is not int or not 1<=k<=20000:raise ValueError('Invalid query bound')
        encoded=vector_text(value,spec.dimensions)
        try:
            with self.connect() as c:
                # Ready rows are immutable, so no ready->building transition can race this read.
                state=c.execute(sql.SQL("SELECT 1 FROM {} WHERE build_key=%s AND state='ready'").format(self.builds),(spec.identity,)).fetchone()
                if state is None:raise IndexNotReady('Exact version is not ready')
                rows=c.execute(sql.SQL('''WITH distances AS (
                    SELECT chunk_id,entity_id,embedding OPERATOR(public.<=>) %s::public.vector AS distance
                    FROM {} WHERE build_key=%s), ranked AS (
                    SELECT *,row_number() OVER (PARTITION BY entity_id ORDER BY distance,chunk_id) AS rank
                    FROM distances)
                    SELECT chunk_id,1-distance AS score FROM ranked WHERE rank=1
                    ORDER BY distance,chunk_id LIMIT %s''').format(self.rows),(encoded,spec.identity,k)).fetchall()
        except psycopg.Error:
            raise IndexNotReady('Vector storage unavailable') from None
        members={ch.id:ch for ch in spec.chunks}
        if any(row['chunk_id'] not in members for row in rows):raise ValueError('Stored membership mismatch')
        return [Hit(members[row['chunk_id']],row['score']) for row in rows]


class PgExactIndex:
    def __init__(self,store,spec):self.store=store;self.spec=spec

    def search(self,query,version,provider,k=10):
        if version!=self.spec.version or provider.model!=version.model or provider.dimensions!=self.spec.dimensions:
            raise ValueError('Persistent index version mismatch')
        if not query.strip():return []
        state=self.store.status(self.spec)
        if not state or state['state']!='ready':raise IndexNotReady('Exact version is not ready')
        value=embed(provider,[query])[0]
        return self.store.query(self.spec,value,k)


def module_retriever(lexical, *, config, enabled=False, store=None, spec=None, provider=None, graph_nodes=()):
    """Explicit Python integration; BM25 default needs no DB/provider construction."""
    if config.mode=='bm25':return lexical
    if enabled is not True:raise ValueError('Vector preview is disabled')
    if store is None or spec is None:raise ValueError('Explicit storage and version required')
    from locagent_service.rag_graph_adapter import GraphModuleRetriever
    return GraphModuleRetriever(lexical,spec.version,spec.chunks,graph_nodes,
        index=PgExactIndex(store,spec),provider=provider,config=config)
