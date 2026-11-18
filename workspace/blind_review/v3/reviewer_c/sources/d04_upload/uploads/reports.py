def upload_label(session):
    return 'complete' if session['completed'] else 'pending'
