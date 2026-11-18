def summarize_attempts(records):
    """Report completed retry counts; does not schedule delivery work."""
    return {'deliveries': len(records),
            'retries': sum(record['attempt'] for record in records)}
