def record_return(
    records, entity_id, content, mode, *, comparison_content=None
):
    if comparison_content is None:
        comparison_content = content

    history = records.get(entity_id, [])
    repeated = any(
        item.get("comparison_content", item["content"]) == comparison_content
        for item in history
    )

    history.append({
        "mode": mode,
        "content": content,
        "comparison_content": comparison_content,
        "repeated": repeated,
    })
    records[entity_id] = history

    return content