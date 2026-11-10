"""Shared completion checks for LeadFinder's DeepSeek generators."""

MODEL = "deepseek-flash"


def completion_text(response):
    choices = getattr(response, 'choices', None)
    if not choices:
        raise RuntimeError('DeepSeek returned no completion. Try generating again.')
    choice = choices[0]
    reason = getattr(choice, 'finish_reason', None)
    if reason == 'length':
        raise RuntimeError('The AI response was cut short before completion. Try generating again with a smaller brief.')
    if reason not in (None, 'stop'):
        raise RuntimeError(f'DeepSeek stopped before completing the response ({reason}). Try generating again.')
    content = getattr(getattr(choice, 'message', None), 'content', None)
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError('DeepSeek returned an empty response. Try generating again.')
    return content
