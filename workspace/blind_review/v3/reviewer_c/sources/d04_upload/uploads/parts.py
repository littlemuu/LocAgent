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
