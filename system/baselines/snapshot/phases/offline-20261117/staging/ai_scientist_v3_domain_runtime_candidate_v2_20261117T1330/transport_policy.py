"""Fixed-model inference policy including Codex input.additional_tools schemas."""
ALLOWED = {'/v1/responses', '/v1/responses/compact', '/v1/chat/completions'}


def validate(path, payload):
    if path not in ALLOWED or payload.get('model') != 'gpt-6-astra':
        raise ValueError('Only the fixed Astra model inference endpoint is permitted')
    effort = payload.get('reasoning', {}).get('effort', payload.get('reasoning_effort'))
    if effort != 'xhigh': raise ValueError('Fixed reasoning effort is xhigh')
    def tools(items):
        if not isinstance(items, list): raise ValueError('Invalid tool schema')
        for item in items:
            if not isinstance(item, dict) or item.get('type') not in {'function', 'custom', 'namespace', 'local_shell'}:
                raise ValueError('Provider-hosted tools are unavailable')
            if item.get('type') == 'namespace': tools(item.get('tools', []))
    tools(payload.get('tools', []))
    def walk(value):
        if isinstance(value, dict):
            if value.get('type') == 'additional_tools': tools(value.get('tools', []))
            for key, item in value.items():
                if key in {'file_url', 'image_url', 'video_url', 'audio_url'}:
                    address = item.get('url', '') if isinstance(item, dict) else item
                    if isinstance(address, str) and address and not address.startswith('data:'):
                        raise ValueError('Provider remote media fetching is unavailable')
                walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(payload)
    selection = payload.get('tool_choice')
    if isinstance(selection, dict):
        if selection.get('type') not in {'function', 'custom', 'allowed_tools'}:
            raise ValueError('Provider-hosted tool choice unavailable')
        if selection.get('type') == 'allowed_tools': tools(selection.get('tools', []))
