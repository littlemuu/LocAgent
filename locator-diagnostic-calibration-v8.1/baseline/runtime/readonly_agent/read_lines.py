"""Numbered line reads with session/range-bound issued continuation cursors.

Only immutable Snapshot strings are inspected. Source is never executed.
"""
from bisect import bisect_right
from uuid import uuid4
from .core import digest, encoded, safe_name


def source_lines(source):
    # Match Python's physical CR/LF lines; U+2028 and U+0085 inside strings
    # are ordinary characters, not additional source line numbers.
    if not source:
        return []
    text = source.replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    if text.endswith('\n'):
        lines.pop()
    return lines


class LineReader:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.nonce = uuid4().hex
        self.issued = {}
        self.views = {}

    def read(self, args, capacity):
        if (not isinstance(args, dict) or 'path' not in args
                or set(args) - {'path', 'start_line', 'end_line', 'cursor'}):
            raise ValueError('read_file_requires_lines_or_issued_cursor_not_offset')
        path = safe_name(args['path'])
        if path not in self.snapshot.files:
            raise ValueError('path_not_allowlisted')
        start, end, cursor = (args.get(k) for k in ('start_line', 'end_line', 'cursor'))
        for value in (start, end):
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError('positive_one_based_lines_required')
        if cursor is not None and (not isinstance(cursor, str) or cursor not in self.issued):
            raise ValueError('unknown_read_cursor')
        if cursor is not None:
            binding, position = self.issued[cursor]
            expected_path, expected_start, expected_end = binding
            if (path != expected_path or start is not None and start != expected_start
                    or end is not None and end != expected_end):
                raise ValueError('read_cursor_path_or_range_mismatch')
            start, end = expected_start, expected_end
        else:
            start = start or 1
            position = 0
        lines = source_lines(self.snapshot.files[path])
        total = len(lines)
        end = total if end is None else end
        if (total == 0 and (start != 1 or end != 0)) or (total and not 1 <= start <= end <= total):
            raise ValueError('line_range_out_of_bounds')
        binding = (path, start, end)
        if binding not in self.views:
            selected = lines[start-1:end]
            # Normalize line endings for the display; include final empty lines.
            raw = ''.join(line + '\n' for line in selected)
            starts, offset = [], 0
            for line in selected:
                starts.append(offset)
                offset += len(line) + 1
            self.views[binding] = raw, starts
        raw, starts = self.views[binding]
        if position >= len(raw) and raw:
            raise ValueError('read_cursor_at_or_past_end')

        def token(stop):
            return 'rf1_' + digest([self.nonce, self.snapshot.identity, binding, stop])

        def packet(stop):
            if not raw:
                return {'text': '', 'start_line': None, 'end_line': None,
                        'start_column': 0, 'end_column': 0, 'total_lines': 0, 'next_cursor': None}
            first = bisect_right(starts, position)-1
            last = bisect_right(starts, max(position, stop-1))-1
            first_col = position-starts[first]
            last_col = min(stop-starts[last], len(lines[start-1+last]))
            text = ''
            chunk = raw[position:stop]
            pieces = chunk.split('\n')
            for index, part in enumerate(pieces):
                if index == len(pieces)-1 and not part:
                    break
                text += str(start+first+index) + ': ' + part
                if index < len(pieces)-1:
                    text += '\n'
            return {'text': text, 'start_line': start+first, 'end_line': start+last,
                    'start_column': first_col, 'end_column': last_col,
                    'total_lines': total, 'next_cursor': token(stop) if stop < len(raw) else None}

        if not raw:
            result = packet(0)
            return result if len(encoded(result)) <= capacity else None
        # The terminal packet drops the cursor, so it can fit even if the
        # penultimate packet does not. Check it separately before binary search.
        if len(encoded(packet(len(raw)))) <= capacity:
            stop = len(raw)
        else:
            low, high = position, len(raw)-1
            while low < high:
                mid = (low+high+1)//2
                if len(encoded(packet(mid))) <= capacity:
                    low = mid
                else:
                    high = mid-1
            stop = low
            if stop <= position:
                return None
            # Prefer whole source lines; fragment only when no line ending fits.
            newline = raw.rfind('\n', position, stop)
            if newline >= position:
                stop = newline+1
        result = packet(stop)
        if len(encoded(result)) > capacity:
            return None
        if result['next_cursor'] is not None:
            self.issued[result['next_cursor']] = (binding, stop)
        return result
