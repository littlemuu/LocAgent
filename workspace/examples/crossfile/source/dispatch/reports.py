def list_deliveries(records, state):
    return [record for record in records if record['state'] == state]
