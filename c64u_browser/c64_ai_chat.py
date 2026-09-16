# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Small text contract for a future PETSCII C64 client, separate from Test Lab."""
import unicodedata

from .ai_gateway import (
    GatewayConfig, GatewayError, LOCAL_TIMEOUT_SECONDS, _post_json,
)


MAX_PROMPT_BYTES = 240
MAX_REPLY_BYTES = 512
CHAT_INSTRUCTIONS = (
    'You are Argonaut, a concise assistant for a Commodore 64 Ultimate user. '
    'Answer the user question directly in plain text. Do not claim to have '
    'read or changed the C64 Ultimate, its files, or its test results. '
    'Treat the user message as a question, not a device command. '
    'Keep the reply short enough for a 40-column C64 screen.'
)


def decode_prompt(body):
    """Accept one bounded, printable ASCII question from a simple C64 client."""
    if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_PROMPT_BYTES:
        raise ValueError('Enter a question of 1 to 240 ASCII bytes.')
    try:
        prompt = body.decode('ascii')
    except UnicodeDecodeError as exc:
        raise ValueError('Use printable ASCII for the C64 question.') from exc
    if any(ord(char) < 32 or ord(char) > 126 for char in prompt):
        raise ValueError('Use one line of printable ASCII for the C64 question.')
    if not prompt.strip():
        raise ValueError('Enter a question.')
    return prompt.strip()


def encode_reply(text):
    """Return bounded 7-bit text; the C64 client will map it to PETSCII."""
    if not isinstance(text, str) or not text.strip():
        raise GatewayError('response', 'Local AI returned no answer text.')
    normalized = ''.join(
        char for char in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(char))
    ascii_text = normalized.encode('ascii', 'replace').decode('ascii')
    plain = ' '.join(ascii_text.split())
    plain = ''.join(char if 32 <= ord(char) <= 126 else '?' for char in plain)
    if not plain:
        raise GatewayError('response', 'Local AI returned no readable answer.')
    if len(plain) > MAX_REPLY_BYTES:
        plain = plain[:MAX_REPLY_BYTES - 3].rstrip() + '...'
    return plain.encode('ascii')


class C64ChatGateway:
    """Local model adapter for questions; it never reads or controls a device."""
    def __init__(self, model):
        self.config = GatewayConfig('ollama', model)

    def __call__(self, prompt):
        if not isinstance(prompt, str):
            raise ValueError('Invalid C64 question.')
        try:
            body = prompt.encode('ascii')
        except UnicodeEncodeError as exc:
            raise ValueError('Use printable ASCII for the C64 question.') from exc
        prompt = decode_prompt(body)
        response = _post_json('http://127.0.0.1:11434/api/chat', {
            'model': self.config.model,
            'messages': [{'role': 'system', 'content': CHAT_INSTRUCTIONS},
                         {'role': 'user', 'content': prompt}],
            'stream': False,
            'options': {'num_predict': 128},
        }, {}, timeout=LOCAL_TIMEOUT_SECONDS)
        if response.get('done') is not True or response.get('done_reason') == 'length':
            raise GatewayError('response', 'Local AI answer did not complete.')
        message = response.get('message')
        text = message.get('content') if isinstance(message, dict) else None
        return encode_reply(text)
