def record_return(records, entity_id, content, mode):
    history = records.get(entity_id, [])
    repeated = any(item["content"] == content for item in history)

    history.append({
        "mode": mode,
        "content": content,
        "repeated": repeated,
    })
    records[entity_id] = history

    return content