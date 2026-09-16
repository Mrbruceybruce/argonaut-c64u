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
