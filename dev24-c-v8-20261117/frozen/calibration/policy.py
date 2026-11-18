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

# Conservative lexical guard, not a semantic truth oracle. Any violation discards
# the WHOLE answer; rejected claims are kept in a sidecar, never forwarded to coding.
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
                        visit(child, name + '.')
                    else:
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


def sections(answer):
    rows = answer.splitlines()
    positions = [i for i, row in enumerate(rows) if row.strip() in HEADINGS]
    if len(positions) != 3 or [rows[i].strip() for i in positions] != list(HEADINGS) or positions[0] != 0:
        return None
    return {h: '\n'.join(rows[a + 1:b]).strip() for h, a, b in zip(HEADINGS, positions, positions[1:] + [len(rows)])}


def violations(packet, ledger):
    answer = packet['answer']; failures = []
    parts = sections(answer)
    if parts is None or not all(parts.values()):
        failures.append('R2_three_sections')
    if STRONG.search(answer):
        failures.append('R3_unverified_strong_claim')
    for match in CITATION.finditer(answer):
        if not ledger.covers(match['path'], int(match['start']), int(match['end'] or match['start'])):
            failures.append('R4_citation_not_delivered:' + match[0])
    referenced = set(packet['entities']) | set(ENTITY.findall(answer))
    # Also catch bare qualified/leaf function mentions instead of letting prose
    # evade the path:QualifiedName convention. Ambiguities remain conservative.
    for entity in ledger.spans:
        name = entity.split(':', 1)[1]
        leaf = name.rsplit('.', 1)[-1]
        if re.search(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])', answer) or re.search(r'`' + re.escape(leaf) + r'`|(?<![A-Za-z0-9_])' + re.escape(leaf) + r'\(', answer):
            referenced.add(entity)
    for entity in sorted(referenced):
        if not ledger.complete_entity(entity) and not re.search(re.escape(entity) + r'[^\n]*未读完', answer):
            failures.append('R1_body_incomplete_unmarked:' + entity)
    if ledger.pending and (parts is None or '未读完' not in parts[HEADINGS[2]] or '分页' not in parts[HEADINGS[2]]):
        failures.append('R1_cursor_unfinished_unmarked')
    if parts:
        for line in parts[HEADINGS[0]].splitlines():
            if line.strip() and not CITATION.search(line) and line.strip() != '尚无可引用的完整源码行。':
                failures.append('R4_fact_without_citation')
        for line in parts[HEADINGS[1]].splitlines():
            if line.strip() and not line.strip().startswith('待验证假设：'):
                failures.append('R3_inference_not_hypothesis')
        if not re.search(r'最小验证：[ \t]*`[^`\n]+`', parts[HEADINGS[2]]):
            failures.append('R3_missing_minimal_validation')
    return list(dict.fromkeys(failures))


def calibrate(packet, ledger):
    """Keep B's candidate lists intact; fail closed on unsupported answer content."""
    result = copy.deepcopy(packet)
    rejected = violations(packet, ledger)
    if rejected:
        facts = [f'{p}:{a}-{b} 已收到这些完整源码行；仅表示阅读覆盖。' for p, a, b in ledger.ranges()[:12]]
        result['answer'] = '\n'.join([
            HEADINGS[0], '\n'.join(facts) or '尚无可引用的完整源码行。',
            HEADINGS[1], '待验证假设：候选位置可能与问题有关；当前证据不足以提出可靠的具体根因判断。',
            HEADINGS[2], '原诊断未通过证据校验；关键调用链未核验。',
            *[f'{e}：' + ('函数/实体源码已读完，行为未验证。' if ledger.complete_entity(e) else '未读完，不能作为确定根因依据。') for e in result['entities']],
            *[f'{p}：分页未读完，仍有 next_cursor。' for p in sorted(set(ledger.pending.values()))],
            '最小验证：`python -m pytest -q`（未运行；一般回归入口，不能单独验证具体根因）。'])
    else:
        result['answer'] += '\n关键调用链穷尽性及运行行为未核验；以上推断均为待验证假设。'
    assert not violations(result, ledger), violations(result, ledger)
    return result, {'policy': 'locator-diagnostic-calibration-v8', 'raw_packet': packet,
                    'violations': rejected, 'fallback': bool(rejected),
                    'delivered_full_line_ranges': ledger.ranges(),
                    'pending_read_pages': dict(ledger.pending),
                    'entity_body_complete': {e: ledger.complete_entity(e) for e in packet['entities']},
                    'call_chain_complete': False, 'behavior_verified': False,
                    'quality_measured': False}
