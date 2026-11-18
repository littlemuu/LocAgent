def next_delay(attempt):
    return min(60, 2 ** attempt)
