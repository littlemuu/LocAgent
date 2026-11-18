from pathlib import Path
R=Path(__file__).resolve().parents[2];p=R/'locator-diagnostic-calibration-v8.2/calibration/policy.py'
s=p.read_text().replace('# Conservative lexical guard, not a semantic truth oracle. Any violation discards\n# the WHOLE answer; rejected claims are kept in a sidecar, never forwarded to coding.','# Lexical evidence guard, not a semantic truth oracle. v8.2 scopes findings\n# and discloses R1/R3/R4 without deleting original prose.')
s=s.replace('        self.spans = {}','        self.spans = {}\n        self.def_spans = {}\n        self.search_hits = {}\n        self.non_body_entities = set()')
s=s.replace("                        self.spans.setdefault(path + ':' + name, []).append((start, child.end_lineno))","                        self.spans.setdefault(path + ':' + name, []).append((start, child.end_lineno))\n                        self.def_spans.setdefault(path + ':' + name, []).append((child.lineno, child.end_lineno))")
s=s.replace("                    else:\n                        visit(child, prefix)","                    else:\n                        if isinstance(child, (ast.Assign, ast.AnnAssign)):\n                            targets = child.targets if isinstance(child, ast.Assign) else [child.target]\n                            for target in targets:\n                                if isinstance(target, ast.Name):\n                                    self.non_body_entities.add(path + ':' + prefix + target.id)\n                        visit(child, prefix)")
s=s.replace("        elif name == 'locagent_retrieve':","        elif name == 'search_text':\n            self.observe_search(args, result)\n        elif name == 'locagent_retrieve':",1)
a=s.index('\ndef violations(');b=s.index('\ndef fallback_answer(',a)
s=s[:a]+'''\n# Only final-answer gates use these permissive helpers. complete_entity(), notice()
# and read_priority() above retain v8.1 behavior, including decorator coverage.
UNREAD = re.compile(r'未读(?:完|到)?|未收到|未续读|被截断|正文未核验|函数体未核验')
TOKEN = re.compile(r'(?<![\\w./])([A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)*)(?![\\w./])')
PATH = re.compile(r'[\\w./-]+\\.py')
DISCLOSURE_HEADING = '以下内容未在阅读记录中核验：'


def prose_line(line):
    return re.sub(r'^[-*+•]\\s+', '', line.strip())


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
            text = re.sub(r'`(?:python|pytest|rg|grep|sed|cat|make|git|cd)\\b[^`]*`', '', line)
            refs.update(ENTITY.findall(text))
    return {canonical_entity(e, packet, ledger) for e in refs}


def unread_entities(packet, ledger, refs):
    """Resolve explicit unread statements against already qualified references.

    Short names can MARK an existing unique identity; they never CREATE an entity.
    A path supplied in the statement restricts matching to that file. This avoids
    the old whole-answer scan for every bare AST name, directories and commands.
    """
    marked = set()
    for line in packet['answer'].splitlines():
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
            text = re.sub(r'`(?:python|pytest|rg|grep|sed|cat|make|git|cd)\\b[^`]*`', '', text)
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
        text = re.sub(r'根因(?:就是|是|在)|\\broot cause\\b', '', text, flags=re.I)
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
        if not re.search(r'最小验证：[ \\t]*`[^`\\n]+`', parts[HEADINGS[2]]):
            failures.append('R3_missing_minimal_validation')
    return list(dict.fromkeys(failures))

''' +s[b:]
a=s.index('\ndef calibrate(');s=s[:a]
p.write_text(s)
