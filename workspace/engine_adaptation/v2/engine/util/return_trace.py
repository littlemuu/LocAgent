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

    previously_in_context = any(
        item.get("in_context", False)
        and item.get("comparison_content", item["content"])
        == comparison_content
        for item in history
    )

    entry = {
        "mode": mode,
        "content": content,
        "comparison_content": comparison_content,
        "repeated": repeated,
        "in_context": False,
        "previously_in_context": previously_in_context,
    }
    history.append(entry)
    records[entity_id] = history

    return entry


def mark_returns_in_context(records, message_content):
    for history in records.values():
        for entry in history:
            content = entry["content"]
            if content and content in message_content:
                entry["in_context"] = True


def refresh_returns_in_context(records, messages):
    # 先清除旧标记，再根据当前消息重新确认。
    for history in records.values():
        for entry in history:
            entry["in_context"] = False

    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            continue

        role = message.get("role")
        if role == "tool" or (
            role == "user" and content.startswith("OBSERVATION:\n")
        ):
            mark_returns_in_context(records, content)
