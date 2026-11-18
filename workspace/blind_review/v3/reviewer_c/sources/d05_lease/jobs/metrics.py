def unfinished_count(jobs):
    return sum(not job['done'] for job in jobs)
