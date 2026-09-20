# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Display model prose as readable plain text in the Test Lab."""
import re


def readable_diagnosis(text):
    """Remove common Markdown markers without interpreting model output as markup."""
    if not isinstance(text, str):
        return ''
    text = re.sub(r'(?m)^[ ]{0,3}#{1,6}[ \t]+', '', text)
    for marker in (r'\*\*', r'`'):
        text = re.sub(rf'{marker}(?=\S)(.+?)(?<=\S){marker}', r'\1', text)
    return text.strip()


def unavailable_message(provider, error):
    """Return a clear, actionable message when optional AI analysis cannot run."""
    detail = str(error).strip() or 'The AI service did not return a diagnosis.'
    if provider == 'ollama':
        if getattr(error, 'kind', None) == 'configuration':
            action = 'Enter the name of a downloaded Ollama model in Test Lab.'
        elif getattr(error, 'kind', None) == 'network':
            action = ('Ollama must be installed and running on this computer; '
                      'then download the selected model and try again.')
        else:
            action = 'Check Ollama and the selected local model, then try again.'
        return f'Local AI unavailable: {detail} {action}'
    return f'Cloud AI unavailable: {detail} Check the provider settings and try again.'
