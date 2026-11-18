"""Author self-contained development fixtures. Never import or execute their code."""
import json
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[2] / 'development_suite/v1'


def case(identifier, title, issue, query, files, gold, criteria):
    base = ROOT/'cases'/identifier
    base.mkdir(parents=True, exist_ok=False)
    sources = {}
    for name, text in files.items():
        path = base/'source'/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(text).lstrip(), encoding='utf-8')
        sources[name] = path
    def call(name, args, ident):
        return {'stop_reason':'tool_use','content':[{'type':'tool_use','id':ident,'name':name,'input':args}]}
    scripts = {}
    for arm in ('baseline','retrieval'):
        scripts[arm] = [call('list_files',{'offset':0},'one'),
            call('search_text' if arm=='baseline' else 'locagent_retrieve',{'query':query,'offset':0},'two'),
            call('read_file',{'path':sorted(files)[0],'offset':0},'three'),
            call('finish',{'files':[],'entities':[],
                'answer':'Offline scripted protocol fixture; no model-quality answer.'},'end')]
    question = {'root':'source','source_files':sorted(files),'issue':issue+
        ' Trace the relevant functions across files, cite source evidence, and state uncertainty. Do not modify or execute source.',
        'scripts':scripts}
    (base/'case.json').write_text(json.dumps(question,indent=2)+'\n')
    return {'id':identifier,'title':title,'gold_files':sorted({e.split(':')[0] for e in gold}),
            'gold_entities':gold,'answer_criteria':criteria}


def main():
    rows=[]
    rows.append(case('d01_cache','租户缓存：版本、过期和写入失败',
        'A profile is fetched repeatedly for one tenant, then updated. Explain the cache key, the exact expiry boundary, how an update changes subsequent reads, and what happens if the database write fails. Does this guarantee fresh reads under concurrent operations?',
        'cache', {
        'profiles/api.py': '''
            from .cache import fetch_profile
            from .writes import replace_profile

            def get_profile(db, cache, versions, tenant, user, now):
                return fetch_profile(db, cache, versions, tenant, user, now)

            def put_profile(db, cache, versions, tenant, user, payload):
                return replace_profile(db, cache, versions, tenant, user, payload)
        ''',
        'profiles/keys.py': '''
            def cache_key(tenant, user, generation):
                return (str(tenant), str(user), generation)
        ''',
        'profiles/cache.py': '''
            from .keys import cache_key
            TTL = 30

            def fetch_profile(db, cache, versions, tenant, user, now):
                generation = versions.get((tenant, user), 0)
                key = cache_key(tenant, user, generation)
                entry = cache.get(key)
                if entry is not None and now < entry['expires_at']:
                    return entry['value']
                value = db.read(tenant, user)
                cache[key] = {'value': value, 'expires_at': now + TTL}
                return value
        ''',
        'profiles/writes.py': '''
            def replace_profile(db, cache, versions, tenant, user, payload):
                db.write(tenant, user, payload)
                identity = (tenant, user)
                versions[identity] = versions.get(identity, 0) + 1
                return versions[identity]
        ''',
        'profiles/cleanup.py': '''
            def discard_expired(cache, now):
                for key in list(cache):
                    if cache[key]['expires_at'] <= now:
                        del cache[key]
        ''',
        'profiles/reports.py': '''
            def cache_report(cache):
                return {'entries': len(cache)}
        '''}, ['profiles/keys.py:cache_key','profiles/cache.py:fetch_profile','profiles/writes.py:replace_profile'], [
        'Key is a tuple of stringified tenant, user and current generation; distinguish raw version-map identity from stringified key.',
        'Hit requires now < expires_at; equality misses; a miss reads db and caches for 30 units.',
        'DB write occurs before generation increment; exception leaves generation unchanged; successful increment makes old key unreachable for later generation lookups without deleting old entries.',
        'No locking/atomic transaction with reader; concurrent stale returns and cross-process shared-state assumptions are not guaranteed.']))
    rows.append(case('d02_config','配置覆盖：优先级、假值和校验',
        'A task starts with default settings, a project mapping, and a request mapping. Explain which values win, whether false and zero are treated as missing, what happens to unknown keys, and whether invalid overridden values reach the worker.',
        'settings', {
        'runner/api.py': '''
            from .settings import resolve_settings
            from .worker import start_worker

            def launch(project, request):
                settings = resolve_settings(project, request)
                return start_worker(settings)
        ''',
        'runner/defaults.py': '''
            DEFAULTS = {'attempts': 3, 'timeout': 10, 'enabled': True}
        ''',
        'runner/settings.py': '''
            from .defaults import DEFAULTS
            from .validation import validate_settings

            def resolve_settings(project, request):
                merged = dict(DEFAULTS)
                for layer in (project, request):
                    for key in DEFAULTS:
                        if key in layer and layer[key] is not None:
                            merged[key] = layer[key]
                validate_settings(merged)
                return merged
        ''',
        'runner/validation.py': '''
            def validate_settings(settings):
                if type(settings['attempts']) is not int or settings['attempts'] < 0:
                    raise ValueError('attempts')
                if type(settings['timeout']) is not int or settings['timeout'] <= 0:
                    raise ValueError('timeout')
                if type(settings['enabled']) is not bool:
                    raise ValueError('enabled')
        ''',
        'runner/worker.py': '''
            def start_worker(settings):
                if not settings['enabled']:
                    return {'started': False}
                return {'started': True, 'attempts': settings['attempts'], 'timeout': settings['timeout']}
        ''',
        'runner/reports.py': '''
            def report_defaults():
                return 'Defaults are documentation, not a runtime override.'
        '''}, ['runner/settings.py:resolve_settings','runner/validation.py:validate_settings','runner/worker.py:start_worker'],[
        'Priority defaults < project < request, only known default keys, None does not override.',
        'False and zero are not missing: false enabled is retained; zero attempts allowed, zero timeout invalid.',
        'Exact types enforced: bool cannot stand in for integer; invalid final value raises before worker call; an invalid lower value may be replaced by a valid higher value.',
        'Enabled false returns started false; valid enabled true uses resolved attempts/timeout; no environment layer or arbitrary unknown setting propagation.']))
    rows.append(case('d03_access','共享文档：租户边界和只读链接',
        'A user opens or edits a document using a tenant-scoped identity and an optional share token. Explain the order of access checks, when ownership or an administrator role helps, what a share token permits, and whether recording an audit event itself grants access.',
        'access', {
        'docs/api.py': '''
            from .access import permitted
            from .audit import record_access

            def open_document(user, document, action, token, audit):
                if not permitted(user, document, action, token):
                    raise PermissionError('denied')
                record_access(audit, user['id'], document['id'], action)
                return document['body']
        ''',
        'docs/access.py': '''
            from .shares import valid_share

            def permitted(user, document, action, token):
                if user['disabled'] or user['tenant'] != document['tenant']:
                    return False
                if action not in ('read', 'write'):
                    return False
                if user['id'] == document['owner'] or user['role'] == 'admin':
                    return True
                return action == 'read' and valid_share(token, document)
        ''',
        'docs/shares.py': '''
            def valid_share(token, document):
                return (token is not None and not token['revoked']
                        and token['document_id'] == document['id']
                        and token['tenant'] == document['tenant'])
        ''',
        'docs/audit.py': '''
            def record_access(audit, user_id, document_id, action):
                audit.append((user_id, document_id, action))
        ''',
        'docs/listing.py': '''
            def list_titles(documents):
                return [document['title'] for document in documents]
        ''',
        'docs/reports.py': '''
            def denied_report(events):
                return len(events)
        '''}, ['docs/access.py:permitted','docs/shares.py:valid_share','docs/api.py:open_document'],[
        'Disabled or cross-tenant user is denied before owner/admin privileges; unknown action denied.',
        'Same-tenant enabled owner or admin can read/write without share token.',
        'Other user gets read only with nonrevoked token matching document id and tenant; token does not bypass tenant or disabled checks.',
        'API checks permission before appending audit and returning body; audit is recording, not a grant. Token cryptographic validation/expiry is not shown.']))
    rows.append(case('d04_upload','分片上传：替换、缺片及完成顺序',
        'An upload receives parts out of order and receives one part number twice. Explain which bytes are eventually assembled, what prevents incomplete or checksum-mismatched uploads from finishing, and what state remains if durable object storage raises during completion.',
        'parts', {
        'uploads/api.py': '''
            from .parts import record_part
            from .finalize import complete_upload

            def receive(session, number, data):
                record_part(session, number, data)

            def finish(session, expected_hash, storage):
                return complete_upload(session, expected_hash, storage)
        ''',
        'uploads/parts.py': '''
            def record_part(session, number, data):
                if session['completed']:
                    raise ValueError('already complete')
                if type(number) is not int or not 0 <= number < session['count']:
                    raise ValueError('part number')
                session['parts'][number] = data

            def assemble_parts(session):
                expected = set(range(session['count']))
                if set(session['parts']) != expected:
                    raise ValueError('missing or extra parts')
                return b''.join(session['parts'][number] for number in range(session['count']))
        ''',
        'uploads/checksum.py': '''
            from hashlib import sha256

            def checksum_matches(data, expected):
                return sha256(data).hexdigest() == expected
        ''',
        'uploads/finalize.py': '''
            from .parts import assemble_parts
            from .checksum import checksum_matches

            def complete_upload(session, expected_hash, storage):
                if session['completed']:
                    return session['object_id']
                data = assemble_parts(session)
                if not checksum_matches(data, expected_hash):
                    raise ValueError('checksum')
                object_id = storage.put(data)
                session['object_id'] = object_id
                session['completed'] = True
                session['parts'].clear()
                return object_id
        ''',
        'uploads/progress.py': '''
            def part_count(session):
                return len(session['parts'])
        ''',
        'uploads/reports.py': '''
            def upload_label(session):
                return 'complete' if session['completed'] else 'pending'
        '''}, ['uploads/parts.py:record_part','uploads/parts.py:assemble_parts','uploads/checksum.py:checksum_matches','uploads/finalize.py:complete_upload'],[
        'Duplicate number replaces earlier bytes; allowed integer index is 0 through count-1; completed uploads reject receive.',
        'Require exact set of indices; concatenate ascending number order regardless of arrival; mismatches raise before storage.',
        'SHA256 of assembled bytes must equal expected; storage.put precedes object_id/completed/parts mutation.',
        'Storage exception leaves completion state/parts unchanged in shown code, though storage may have side effects; later completed calls return object id. No atomic cross-storage transaction/concurrency guarantee.']))
    rows.append(case('d05_lease','任务租约：代次、截止时间及旧确认',
        'A job lease expires and another worker claims the same job. Explain how the claim token changes, which acknowledgements and renewals are accepted at the exact deadline, and whether the implementation prevents two concurrent claimants from both performing work.',
        'lease', {
        'jobs/api.py': '''
            from .leases import claim_lease, renew_lease
            from .completion import acknowledge

            def acquire(job, worker, now):
                return claim_lease(job, worker, now, ttl=20)

            def complete(job, token, now):
                return acknowledge(job, token, now)
        ''',
        'jobs/leases.py': '''
            from .tokens import lease_token

            def claim_lease(job, worker, now, ttl):
                if job['done'] or (job['owner'] is not None and now < job['deadline']):
                    return None
                job['generation'] += 1
                job['owner'] = worker
                job['deadline'] = now + ttl
                return lease_token(job)

            def renew_lease(job, token, now, ttl):
                if job['done'] or token != lease_token(job) or now >= job['deadline']:
                    return False
                job['deadline'] = now + ttl
                return True
        ''',
        'jobs/tokens.py': '''
            def lease_token(job):
                return (job['id'], job['owner'], job['generation'])
        ''',
        'jobs/completion.py': '''
            from .tokens import lease_token

            def acknowledge(job, token, now):
                if job['done'] or token != lease_token(job) or now >= job['deadline']:
                    return False
                job['done'] = True
                return True
        ''',
        'jobs/reports.py': '''
            def owner_label(job):
                return str(job['owner'])
        ''',
        'jobs/metrics.py': '''
            def unfinished_count(jobs):
                return sum(not job['done'] for job in jobs)
        '''}, ['jobs/leases.py:claim_lease','jobs/leases.py:renew_lease','jobs/tokens.py:lease_token','jobs/completion.py:acknowledge'],[
        'Claim refused if done or a current owner before deadline; equality permits reclaim; accepted claim increments generation and sets owner/deadline.',
        'Token includes job id, owner and generation, so a previous generation token is rejected after reclaim.',
        'Ack and renewal require not done, exact token, and now < deadline; equality rejects; ack marks done, renewal sets now+ttl.',
        'Plain mutable dictionary lacks locking/CAS or external fencing of side effects; sequential stale-token checks do not prove exclusive concurrent work.']))
    rows.append(case('d06_import','账目导入：行错误、重复替换及汇总',
        'A batch imports CSV-like rows containing tenant, invoice identifier and amount. Explain the normalization and validation path, how malformed rows are reported, which value wins for repeated invoice keys, and whether replacement rows are added twice to the final totals.',
        'invoice', {
        'imports/api.py': '''
            from .parser import parse_row
            from .index import index_invoice
            from .totals import tenant_totals

            def import_rows(headers, rows):
                invoices = {}
                errors = []
                for number, row in enumerate(rows, 1):
                    try:
                        invoice = parse_row(headers, row)
                        index_invoice(invoices, invoice)
                    except ValueError:
                        errors.append(number)
                return {'totals': tenant_totals(invoices), 'errors': errors}
        ''',
        'imports/parser.py': '''
            from decimal import Decimal, InvalidOperation

            def parse_row(headers, row):
                if len(headers) != len(row):
                    raise ValueError('column count')
                names = [name.strip().lower() for name in headers]
                if len(set(names)) != len(names) or not {'tenant', 'invoice', 'amount'} <= set(names):
                    raise ValueError('headers')
                data = dict(zip(names, row))
                tenant, invoice = data['tenant'].strip(), data['invoice'].strip()
                if not tenant or not invoice:
                    raise ValueError('empty identity')
                try:
                    amount = Decimal(data['amount'].strip())
                except InvalidOperation:
                    raise ValueError('amount') from None
                if not amount.is_finite() or amount < 0:
                    raise ValueError('amount')
                return {'tenant': tenant, 'invoice': invoice, 'amount': amount}
        ''',
        'imports/index.py': '''
            def index_invoice(invoices, invoice):
                key = (invoice['tenant'], invoice['invoice'])
                invoices[key] = invoice
        ''',
        'imports/totals.py': '''
            from decimal import Decimal

            def tenant_totals(invoices):
                totals = {}
                for invoice in invoices.values():
                    tenant = invoice['tenant']
                    totals[tenant] = totals.get(tenant, Decimal('0')) + invoice['amount']
                return totals
        ''',
        'imports/preview.py': '''
            def preview_rows(rows):
                return rows[:3]
        ''',
        'imports/reports.py': '''
            def error_count(result):
                return len(result['errors'])
        '''}, ['imports/parser.py:parse_row','imports/index.py:index_invoice','imports/totals.py:tenant_totals','imports/api.py:import_rows'],[
        'Headers trimmed/lowercased, duplicate or missing required headers and wrong row length rejected; identities trimmed but not lowercased.',
        'Empty identity or malformed/nonfinite/negative Decimal amount rejected; zero allowed; extra columns ignored after mapping.',
        'ValueError records one-based row number and continues; invalid later duplicate does not replace prior valid row; other exception types are not caught.',
        'Key is tenant plus invoice, last valid row wins; totals computed from final dictionary values so replacements are not double-counted; different tenants remain separate.']))
    evaluation=ROOT/'evaluation'
    evaluation.mkdir()
    (evaluation/'rubrics.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    print('Authored six development cases and separate rubrics; no source executed.')


if __name__ == '__main__':
    main()
