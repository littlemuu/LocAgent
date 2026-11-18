"""Diagnostic calibration only. Never imports/executes repository code or calls an API.

Coverage is credited only to bytes delivered by tools, not requested ranges or
retriever metadata. AST spans are used solely to check completeness; unseen source
is never supplied as diagnostic evidence. Unknown call chains stay unverified.
"""
import ast
import copy
import re

HEADINGS = ('已读到的事实（附文件:行号）', '推断', '未核验点')
INSTRUCTION = '''定位诊断校准 v8（不是完整混合检索 v8）。保持 files/entities 格式和排序规则。
总预算不变。根因依据涉及的每个函数必须读完整函数体（包括 docstring）；收到 next_cursor 就继续用该 cursor，
或在终答明确标为“未读完”。源码预览、搜索命中、请求行范围均不等于已读完整正文。
剩余请求不足时，优先补读候选函数和关键调用链，不再扩大检索。工具关闭后不得再读。
answer 严格按三个独立标题输出：
已读到的事实（附文件:行号）
推断
未核验点
事实每行附完整相对路径:起始行-结束行；每一行引用都必须实际收到，片段缺口不得连成范围。
推断中的函数用 path.py:QualifiedName 标识；每行以“待验证假设：”开头。
本只读定位未执行行为验证，也不能证明关键调用链穷尽，因此只能给待验证假设，禁止已确认根因、
不是 bug、无需修改及其英文同义强断言。不得把对未读函数的推测写成事实。
未核验点逐一标注未读完的函数、未续读的分页、缺失调用链和未运行的验证。
必须给出“最小验证：`一条命令或一个断言`”，只建议，不执行；验证应针对假设。
如无具体假设可用 python -m pytest -q 作一般回归入口，但不得声称其能单独验证根因。
约1200字是风格目标；原2048输出token上限不变。'''

# Lexical evidence guard, not a semantic truth oracle. v8.2 scopes findings
# and discloses R1/R3/R4 without deleting original prose.
STRONG = re.compile(
    r'已确认|确认.{0,8}根因|根因(?:就是|是|在)|不是\s*(?:bug|缺陷|问题)|无需(?:修改|修复)|不(?:需要|应)(?:修改|修复)|'
    r'确定.{0,8}(?:原因|错误)|必然|肯定|毫无疑问|'
    r'\b(?:root cause|confirmed|definitely|certainly|not a bug|no bug|not a misunderstanding|'
    r'misunderstanding|no (?:code )?(?:change|fix|modification) (?:is )?(?:needed|required|warranted)|'
    r'(?:does not|doesn.t) need (?:a )?(?:fix|change)|correct(?:ly)?|unrelated)\b', re.I)
CITATION = re.compile(r'(?P<path>[\w./-]+\.py):(?P<start>\d+)(?:[-–](?P<end>\d+))?')
ENTITY = re.compile(r'[\w./-]+\.py:(?!\d)\w+(?:\.(?!\d)\w+)*')


def physical_lines(source):
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    if not source:
        return []
    lines = source.split('\n')
    return lines[:-1] if source.endswith('\n') else lines


class EvidenceLedger:
    def __init__(self, snapshot):
        self.lines = {p: physical_lines(s) for p, s in snapshot.files.items()}
        self.fragments = {}  # (path, line) -> [(column_start, column_end)]
        self.spans = {}
        self.def_spans = {}
        self.search_hits = {}
        self.non_body_entities = set()
        self.pending = {}
        self.streams = {}
        self.candidates = set()
        self.audit = []
        for path, source in snapshot.files.items():
            try:
                tree = ast.parse(source.lstrip('\ufeff'))
            except (SyntaxError, RecursionError):
                continue
            def visit(node, prefix=''):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        name = prefix + child.name
                        start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                        self.spans.setdefault(path + ':' + name, []).append((start, child.end_lineno))
                        self.def_spans.setdefault(path + ':' + name, []).append((child.lineno, child.end_lineno))
                        visit(child, name + '.')
                    else:
                        if isinstance(child, (ast.Assign, ast.AnnAssign)):
                            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                            for target in targets:
                                if isinstance(target, ast.Name):
                                    self.non_body_entities.add(path + ':' + prefix + target.id)
                        visit(child, prefix)
            visit(tree)

    def credit(self, path, number, text, column=0):
        lines = self.lines.get(path, [])
        if not 1 <= number <= len(lines) or column < 0:
            return
        line = lines[number - 1]
        if column + len(text) > len(line) or line[column:column + len(text)] != text:
            return
        self.fragments.setdefault((path, number), []).append((column, column + len(text)))

    def observe(self, item):
        self.audit.append(copy.deepcopy(item))
        name = item.get('tool', item.get('name'))
        args, result = item['arguments'], item['result']
        if not isinstance(result, dict) or 'error' in result:
            return
        if name == 'read_file':
            path = args['path']
            self.pending.pop(args.get('cursor'), None)
            if result.get('next_cursor'):
                self.pending[result['next_cursor']] = path
            for row in result.get('text', '').split('\n'):
                match = re.fullmatch(r'(\d+): (.*)', row)
                if match:
                    number = int(match[1])
                    col = result.get('start_column', 0) if number == result.get('start_line') else 0
                    self.credit(path, number, match[2], col)
        elif name == 'search_text':
            self.observe_search(args, result)
        elif name == 'locagent_retrieve':
            # Offset pages may split header/line text. Only reconstruct delivered
            # contiguous bytes starting at zero; never fetch missing pages locally.
            key = (name, args['query'])
            stream = self.streams.setdefault(key, {})
            stream[args.get('offset', 0) or 0] = result.get('text', '')
            text, offset = '', 0
            while offset in stream and stream[offset]:
                chunk = stream[offset]; text += chunk; offset += len(chunk)
            path = None
            for row in text.split('\n')[:-1]:
                candidate = re.match(r'#\d+ ([^ ]+\.py:[^ ]+) \[', row)
                if candidate:
                    self.candidates.add(candidate[1])
                header = re.match(r'path=([^;]+);', row)
                if header:
                    path = header[1]
                match = re.fullmatch(r'(\d+): (.*)', row)
                if path and match:
                    # Excerpts never count as full lines. credit verifies exact bytes.
                    self.credit(path, int(match[1]), match[2])

    def complete_line(self, path, number):
        spans = sorted(self.fragments.get((path, number), []))
        if not spans:
            return False
        stop = 0
        for start, end in spans:
            if start > stop:
                return False
            stop = max(stop, end)
        return stop == len(self.lines[path][number - 1])

    def covers(self, path, start, end):
        return 1 <= start <= end <= len(self.lines.get(path, [])) and all(
            self.complete_line(path, n) for n in range(start, end + 1))

    def complete_entity(self, entity):
        spans = self.spans.get(entity, [])
        # Ambiguous duplicate definitions are not silently resolved to the last one.
        return bool(spans) and all(self.covers(entity.split(':')[0], a, b) for a, b in spans)

    def ranges(self):
        result = []
        for path in sorted({p for p, _ in self.fragments}):
            numbers = sorted(n for p, n in self.fragments if p == path and self.complete_line(p, n))
            for n in numbers:
                if result and result[-1][0] == path and result[-1][2] == n - 1:
                    result[-1][2] = n
                else:
                    result.append([path, n, n])
        return result

    def notice(self):
        # Only describe delivered coverage and issued cursors, never unseen code.
        ranges = '; '.join(f'{p}:{a}-{b}' for p, a, b in self.ranges()) or '无完整源码行'
        pending = '; '.join(f'{p} cursor={c}' for c, p in self.pending.items()) or '无'
        incomplete = '; '.join(self.incomplete_candidates()) or '无已返回的实体候选缺口'
        return ('CALIBRATION CONTROLLER: 实际完整行（非已请求范围）: ' + ranges +
                '。未续读分页: ' + pending + '。候选未读完: ' + incomplete +
                '。优先补读候选函数体，不扩大搜索；预算不足则标为未读完。')

    def incomplete_candidates(self):
        return sorted(e for e in self.candidates if not self.complete_entity(e))

    def read_priority(self, name, turn, maximum):
        return (name in {'list_files', 'search_text', 'locagent_retrieve'}
                and turn >= maximum - 2
                and bool(self.pending or self.incomplete_candidates()))


    def observe_search(self, args, result):
        key = ('search_text', args['query'])
        stream = self.streams.setdefault(key, {})
        stream[args.get('offset', 0) or 0] = result.get('text', '')
        text, offset = '', 0
        while offset in stream and stream[offset]:
            chunk = stream[offset]; text += chunk; offset += len(chunk)
        rows = text.split('\n')
        # A page ending mid-row does not certify that row. Earlier complete rows
        # are still retained. No requests are issued to complete a stream.
        if result.get('next_offset') is not None:
            rows = rows[:-1]
        for row in rows:
            match = re.fullmatch(r'([\w./-]+\.py):(\d+): (.*)', row)
            if match:
                key = (match[1], int(match[2]))
                self.search_hits.setdefault(key, set()).add(match[3])

    def supports_search_fact(self, path, start, end, statement):
        # Search never credits fragments, complete_line(), covers() or entities.
        # Even adjacent search hits cannot certify a continuous range.
        hits = self.search_hits.get((path, start), set())
        if start != end or not hits:
            return False
        clauses = re.split(r'[；;]', statement)
        relevant = [c for c in clauses if any(int(m['start']) == start and (m['path'] == path or path.endswith('/' + m['path'])) for m in CITATION.finditer(c))]
        text = CITATION.sub('', '；'.join(relevant) if relevant else statement)
        if re.search(r'整个函数|完整函数|全部|所有|唯一|只覆盖|完全|穷尽|已验证|必然|肯定|entire function|all branches', text, re.I):
            return False
        source = '\n'.join(hits)
        # Explicit literals/defaults and quoted assignments must actually appear.
        for value in re.findall(r'(?:默认|等于|返回)\s*`?(True|False|None|\d+)\b', text):
            if not re.search(r'\b' + re.escape(value) + r'\b', source):
                return False
        for code in re.findall(r'`([^`\n]+)`', text):
            if re.search(r'(?<![=!<>])=(?!=)', code):
                compact = lambda x: re.sub(r'\s+', '', x)
                if compact(code) not in compact(source):
                    return False
        words = set(re.findall(r'[A-Za-z_]\w*', text)) - {'py', 'True', 'False', 'None'}
        source_words = set(re.findall(r'[A-Za-z_]\w*', source))
        return bool(words & source_words)

    def validation_complete_entity(self, entity):
        spans = self.def_spans.get(entity, [])
        return bool(spans) and all(self.covers(entity.split(':')[0], a, b) for a, b in spans)

    def is_non_body_entity(self, entity):
        return entity in self.non_body_entities and entity not in self.spans

    @classmethod
    def from_recorded(cls, audit, tool_audit):
        """Offline reconstruction with explicit limitations; no fake full source.

        v8.1 persisted complete-line ranges and candidate completeness but not
        every AST span. Use those observations plus original C retrieval metadata.
        Unknown spans stay unknown. No manual review labels/B reads are consumed.
        """
        return RecordedEvidenceLedger(audit, tool_audit)


def sections(answer):
    rows = answer.splitlines()
    positions = [i for i, row in enumerate(rows) if row.strip() in HEADINGS]
    if len(positions) != 3 or [rows[i].strip() for i in positions] != list(HEADINGS) or positions[0] != 0:
        return None
    return {h: '\n'.join(rows[a + 1:b]).strip() for h, a, b in zip(HEADINGS, positions, positions[1:] + [len(rows)])}


# Only final-answer gates use these permissive helpers. complete_entity(), notice()
# and read_priority() above retain v8.1 behavior, including decorator coverage.
UNREAD = re.compile(r'未读(?:完|到)?|未收到|未续读|被截断|正文未核验|函数体未核验')
TOKEN = re.compile(r'(?<![\w./])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?![\w./])')
PATH = re.compile(r'[\w./-]+\.py')
DISCLOSURE_HEADING = '以下内容未在阅读记录中核验：'


def prose_line(line):
    return re.sub(r'^[-*+•]\s+', '', line.strip())


def validation_line(line):
    # Recommendations/commands are not assertions that the cited source was read.
    return bool(re.match(r'(?:最小验证|验证命令|通用验证)：', prose_line(line)))


def candidate_paths(packet, ledger):
    return set(packet['files']) | {e.split(':')[0] for e in packet['entities']} | {
        e.split(':')[0] for e in ledger.candidates}


def resolve_path(path, packet, ledger):
    paths = candidate_paths(packet, ledger)
    if path in paths:
        return path
    matches = [p for p in paths if p.endswith('/' + path)]
    # A short filename is accepted only when unique among this task's candidates.
    return matches[0] if len(matches) == 1 else path


def canonical_entity(entity, packet, ledger):
    path, sep, name = entity.partition(':')
    return resolve_path(path, packet, ledger) + sep + name


def referenced_entities(packet, ledger):
    refs = set(packet['entities'])
    for line in packet['answer'].splitlines():
        if not validation_line(line):
            # Do not match paths/qualified names inside shell commands.
            text = re.sub(r'`(?:python|pytest|rg|grep|sed|cat|make|git|cd)\b[^`]*`', '', line)
            refs.update(ENTITY.findall(text))
    return {canonical_entity(e, packet, ledger) for e in refs}


def unread_entities(packet, ledger, refs):
    """Resolve explicit unread statements against already qualified references.

    Short names can MARK an existing unique identity; they never CREATE an entity.
    A path supplied in the statement restricts matching to that file. This avoids
    the old whole-answer scan for every bare AST name, directories and commands.
    """
    marked = set()
    scope = None
    for line in packet['answer'].splitlines():
        if line.strip() in HEADINGS:
            scope = line.strip(); continue
        if scope != HEADINGS[2] and not re.search(r'未读完|函数体|函数头|正文', line):
            # A different allocation/call site being unread does not mark the
            # containing function (e.g. __init__ versus _init) unread.
            continue
        if validation_line(line) or not UNREAD.search(line):
            continue
        for clause in re.split(r'[；;。]', line):
            if not UNREAD.search(clause):
                continue
            paths = {resolve_path(p, packet, ledger) for p in PATH.findall(clause)}
            explicit = {canonical_entity(e, packet, ledger) for e in ENTITY.findall(clause)}
            marked.update(explicit & refs)
            # Remove file paths, full entity IDs and command spans before tokenizing.
            text = ENTITY.sub(' ', clause)
            text = PATH.sub(' ', text)
            text = re.sub(r'`(?:python|pytest|rg|grep|sed|cat|make|git|cd)\b[^`]*`', '', text)
            for token in TOKEN.findall(text):
                matches = [e for e in refs if (not paths or e.split(':')[0] in paths)
                           and (e.split(':')[1] == token or e.split(':')[1].endswith('.' + token))]
                if len(matches) == 1:
                    marked.add(matches[0])
    return marked


def pending_marked(answer, ledger):
    lines = [line for line in answer.splitlines() if UNREAD.search(line) and not validation_line(line)]
    return all(any(cursor in line for line in lines) for cursor in ledger.pending)


def strong_claim(line):
    text = prose_line(line)
    if validation_line(text):
        return False
    if text.startswith('待验证假设：'):
        # Hypothetical root-cause statements are allowed. Claims of certainty
        # remain findings even when mechanically prefixed as a hypothesis.
        text = re.sub(r'根因(?:就是|是|在)|\broot cause\b', '', text, flags=re.I)
    return bool(STRONG.search(text))


def violations(packet, ledger):
    answer = packet['answer']; failures = []
    parts = sections(answer)
    if parts is None or not all(parts.values()):
        failures.append('R2_three_sections')
    scope = None
    for line in answer.splitlines():
        if line.strip() in HEADINGS:
            scope = line.strip(); continue
        if strong_claim(line):
            failures.append('R3_unverified_strong_claim')
        if validation_line(line):
            continue
        # A disclosed gap is not a claim of having read those lines. Fact and
        # inference sections still have their citations checked independently.
        if scope == HEADINGS[2] and UNREAD.search(line):
            continue
        for match in CITATION.finditer(line):
            path = resolve_path(match['path'], packet, ledger)
            start, end = int(match['start']), int(match['end'] or match['start'])
            if not ledger.covers(path, start, end) and not ledger.supports_search_fact(path, start, end, line):
                failures.append('R4_citation_not_delivered:' + match[0])
    refs = referenced_entities(packet, ledger)
    unread = unread_entities(packet, ledger, refs)
    for entity in sorted(refs):
        if (not ledger.validation_complete_entity(entity)
                and not ledger.is_non_body_entity(entity) and entity not in unread):
            failures.append('R1_body_incomplete_unmarked:' + entity)
    if ledger.pending and not pending_marked(answer, ledger):
        failures.append('R1_cursor_unfinished_unmarked')
    if parts:
        for line in parts[HEADINGS[0]].splitlines():
            if line.strip() and not CITATION.search(line) and line.strip() != '尚无可引用的完整源码行。':
                failures.append('R4_fact_without_citation')
        for line in parts[HEADINGS[1]].splitlines():
            if line.strip() and not prose_line(line).startswith('待验证假设：'):
                failures.append('R3_inference_not_hypothesis')
        if not re.search(r'最小验证：[ \t]*`[^`\n]+`', parts[HEADINGS[2]]):
            failures.append('R3_missing_minimal_validation')
    return list(dict.fromkeys(failures))


def fallback_answer(packet):
    """Fixed, evidence-independent delivery. No validator or ledger callbacks."""
    return '\n'.join([
        HEADINGS[0], '尚无可引用的完整源码行。',
        HEADINGS[1], '待验证假设：候选位置可能与问题有关，需补读源码并验证。',
        HEADINGS[2],
        *['候选文件：' + p for p in packet['files']],
        *['候选实体：' + e + '：未读完（保守标注，阅读完整性未确认）。' for e in packet['entities']],
        '分页未读完与调用链完整性均待核验。',
        '最小验证：`python -m pytest -q`（未运行；通用回归入口）。'])


class RecordedEvidenceLedger(EvidenceLedger):
    """A recorded-coverage adapter, never a reconstructed source snapshot."""
    def __init__(self, audit, tool_audit):
        self.lines = {}; self.fragments = {}; self.spans = {}; self.def_spans = {}
        self.search_hits = {}; self.non_body_entities = set(); self.streams = {}
        self.candidates = set(); self.audit = copy.deepcopy(tool_audit)
        self.pending = dict(audit['pending_read_pages'])
        self.recorded_ranges = copy.deepcopy(audit['delivered_full_line_ranges'])
        self.recorded_complete = dict(audit['entity_body_complete'])
        # v8.1 also checked full IDs occurring only in prose, but persisted
        # booleans for structured candidates only. Its exact predicate lets us
        # recover a positive result when neither an R1 flag nor an exact unread
        # exemption existed. This uses recorded validator output, not review labels.
        raw = audit['raw_packet']
        if audit.get('validator_error') is None:
            old_refs = set(raw['entities']) | set(ENTITY.findall(raw['answer']))
            exempt = {e for line in raw['answer'].splitlines() if '未读完' in line for e in ENTITY.findall(line)}
            for entity in old_refs - exempt:
                if 'R1_body_incomplete_unmarked:' + entity not in audit['violations']:
                    self.recorded_complete.setdefault(entity, True)
        for item in tool_audit:
            name, args, result = item['tool'], item['arguments'], item['result']
            if not isinstance(result, dict) or 'error' in result:
                continue
            if name == 'search_text':
                self.observe_search(args, result)
            elif name == 'locagent_retrieve':
                self.streams.setdefault((name, args['query']), {})[args.get('offset', 0) or 0] = result.get('text', '')
        for (name, _), stream in self.streams.items():
            if name != 'locagent_retrieve':
                continue
            text, offset = '', 0
            while offset in stream and stream[offset]:
                chunk = stream[offset]; text += chunk; offset += len(chunk)
            entity = None
            for row in text.split('\n')[:-1]:
                header = re.fullmatch(r'#\d+ ([^ ]+\.py:[^ ]+) \[[^\n]+\]', row)
                if header:
                    entity = header[1]; self.candidates.add(entity)
                span = re.match(r'path=([^;]+); lines=(\d+)-(\d+);', row)
                if span and entity and entity.split(':')[0] == span[1]:
                    pair = (int(span[2]), int(span[3]))
                    bucket = self.def_spans.setdefault(entity, [])
                    if pair not in bucket:
                        bucket.append(pair)
                    entity = None
        # A directly observed simple alias/assignment is not a function body.
        # Do not infer this from bare names elsewhere in an answer.
        for (path, _), hits in self.search_hits.items():
            for hit in hits:
                assignment = re.fullmatch(r'\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(?:#.*)?', hit)
                if assignment:
                    self.non_body_entities.add(path + ':' + assignment[1])

    def covers(self, path, start, end):
        if not 1 <= start <= end:
            return False
        next_line = start
        for p, a, b in sorted(self.recorded_ranges):
            if p != path or b < next_line:
                continue
            if a > next_line:
                return False
            next_line = max(next_line, b + 1)
            if next_line > end:
                return True
        return False

    def complete_entity(self, entity):
        return self.recorded_complete.get(entity, False)

    def validation_complete_entity(self, entity):
        # Strict v8.1 completeness implies relaxed completeness. Otherwise only
        # independently logged def spans can establish it, not a guessed boundary.
        return self.complete_entity(entity) or super().validation_complete_entity(entity)

    def ranges(self):
        return copy.deepcopy(self.recorded_ranges)


def disclosure_items(packet, ledger, failures):
    items = []
    lines = packet['answer'].splitlines()
    for failure in failures:
        rule = failure[:2]
        if rule == 'R2':
            continue
        target = failure.partition(':')[2]
        if target:
            if rule == 'R1':
                targets = [canonical_entity(target, packet, ledger)]
            else:
                match = CITATION.fullmatch(target)
                targets = [resolve_path(match['path'], packet, ledger) + ':' + str(match['start']) +
                           ('-' + match['end'] if match['end'] else '')] if match else [target]
        elif failure == 'R1_cursor_unfinished_unmarked':
            targets = [p + '（未续读分页 ' + c + '）' for c, p in sorted(ledger.pending.items())]
        else:
            affected = []
            for n, line in enumerate(lines, 1):
                if failure == 'R3_unverified_strong_claim' and strong_claim(line):
                    affected.append((n, line))
                elif failure == 'R3_inference_not_hypothesis' and sections(packet['answer']):
                    if line in sections(packet['answer'])[HEADINGS[1]].splitlines() and line.strip() and not prose_line(line).startswith('待验证假设：'):
                        affected.append((n, line))
                elif failure == 'R4_fact_without_citation' and sections(packet['answer']):
                    if line in sections(packet['answer'])[HEADINGS[0]].splitlines() and line.strip() and not CITATION.search(line):
                        affected.append((n, line))
            targets = sorted({canonical_entity(e, packet, ledger) for _, line in affected for e in ENTITY.findall(line)})
            if not targets:
                targets = list(packet['entities']) or list(packet['files'])
            if not targets:
                targets = ['answer（未定位到文件/实体）']
        items.append({'rule': rule, 'violation': failure, 'targets': targets})
    return items


def calibrate(packet, ledger):
    """R2/errors alone hard-fallback; all other findings append disclosures."""
    result = copy.deepcopy(packet)
    rejected = []; validator_error = None
    ranges, pending, complete, spans, disclosures = [], {}, {}, {}, []
    try:
        rejected = violations(packet, ledger)
        ranges = ledger.ranges()
        pending = dict(ledger.pending)
        complete = {e: ledger.validation_complete_entity(canonical_entity(e, packet, ledger)) for e in packet['entities']}
        spans = copy.deepcopy(ledger.def_spans)
        disclosures = disclosure_items(packet, ledger, rejected)
    except Exception as error:
        validator_error = type(error).__name__
        ranges, pending, complete, spans, disclosures = [], {}, {}, {}, []
    fallback = any(v.startswith('R2_') for v in rejected) or validator_error is not None
    if fallback:
        result['answer'] = fallback_answer(result)
    elif disclosures:
        result['answer'] += '\n\n' + DISCLOSURE_HEADING + '\n' + '\n'.join(
            '- [' + d['rule'] + '] ' + '；'.join(d['targets']) for d in disclosures)
    counts = {r: sum(v.startswith(r + '_') for v in rejected) for r in ('R1', 'R2', 'R3', 'R4')}
    return result, {'policy': 'locator-diagnostic-calibration-v8.2', 'raw_packet': copy.deepcopy(packet),
                    'violations': rejected, 'violation_count': len(rejected), 'rule_counts': counts,
                    'fallback': fallback, 'validator_error': validator_error,
                    'disclosures': disclosures, 'disclosure_count': 0 if fallback else len(disclosures),
                    'disclosure_attached': bool(disclosures) and not fallback,
                    'original_body_preserved': not fallback,
                    'delivered_full_line_ranges': ranges, 'pending_read_pages': pending,
                    'entity_body_complete': complete, 'entity_def_spans': spans,
                    'evidence_mode': 'recorded_C_logs' if isinstance(ledger, RecordedEvidenceLedger) else 'live_snapshot',
                    'unknown_span_entities': sorted(e for e in complete if not complete[e] and canonical_entity(e, packet, ledger) not in spans),
                    'call_chain_complete': False, 'behavior_verified': False, 'quality_measured': False}
