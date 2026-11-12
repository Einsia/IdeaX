def get_content_between_a_b(start_tag, end_tag, text):
    import re
    # Only independent opening tags are fields. Inline mentions in explanations
    # cannot start a field; repeated valid fields retain the last native value.
    pattern = r"(?m)^[ \t]*" + re.escape(start_tag) + r"(.*?)" + re.escape(end_tag)
    values = re.findall(pattern, text, re.S)
    if not values:
        return ""
    value = values[-1]
    if start_tag in value:
        value = value.rsplit(start_tag, 1)[-1]
    return value.strip()


def extract(text, type,hard = True):
    if text:
        target_str = get_content_between_a_b(f"<{type}>", f"</{type}>", text)
        if target_str:
            return target_str
        elif hard:
            return text
        else:
            return ""
    else:
        return ""


def extract_json(text):
    if "```json" in text:
        target_str = get_content_between_a_b("```json", "```", text)
        return target_str
    else:
        return text



