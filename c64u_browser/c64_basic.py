# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Minimal Commodore BASIC V2 tokenizer for generated Argonaut programs."""
import re


_TOKENS = {
    'end': 0x80, 'for': 0x81, 'next': 0x82, 'data': 0x83,
    'input#': 0x84, 'input': 0x85, 'dim': 0x86, 'read': 0x87,
    'let': 0x88, 'goto': 0x89, 'run': 0x8A, 'if': 0x8B,
    'restore': 0x8C, 'gosub': 0x8D, 'return': 0x8E, 'rem': 0x8F,
    'stop': 0x90, 'on': 0x91, 'wait': 0x92, 'load': 0x93,
    'save': 0x94, 'verify': 0x95, 'def': 0x96, 'poke': 0x97,
    'print#': 0x98, 'print': 0x99, 'cont': 0x9A, 'list': 0x9B,
    'clr': 0x9C, 'cmd': 0x9D, 'sys': 0x9E, 'open': 0x9F,
    'close': 0xA0, 'get': 0xA1, 'new': 0xA2, 'tab(': 0xA3,
    'to': 0xA4, 'fn': 0xA5, 'spc(': 0xA6, 'then': 0xA7,
    'not': 0xA8, 'step': 0xA9, '+': 0xAA, '-': 0xAB,
    '*': 0xAC, '/': 0xAD, '^': 0xAE, 'and': 0xAF,
    'or': 0xB0, '>': 0xB1, '=': 0xB2, '<': 0xB3,
    'sgn': 0xB4, 'int': 0xB5, 'abs': 0xB6, 'usr': 0xB7,
    'fre': 0xB8, 'pos': 0xB9, 'sqr': 0xBA, 'rnd': 0xBB,
    'log': 0xBC, 'exp': 0xBD, 'cos': 0xBE, 'sin': 0xBF,
    'tan': 0xC0, 'atn': 0xC1, 'peek': 0xC2, 'len': 0xC3,
    'str$': 0xC4, 'val': 0xC5, 'asc': 0xC6, 'chr$': 0xC7,
    'left$': 0xC8, 'right$': 0xC9, 'mid$': 0xCA, 'go': 0xCB,
}
_KEYWORDS = sorted(_TOKENS, key=len, reverse=True)
_LINE = re.compile(r'([0-9]+)[ \t]+(.*)')


def _petscii(char):
    code = ord(char)
    if 97 <= code <= 122:
        return code - 32
    if 32 <= code <= 126:
        return code
    raise ValueError('Generated BASIC must contain printable ASCII only.')


def _tokenize_statement(statement):
    output = bytearray()
    index = 0
    quoted = False
    while index < len(statement):
        char = statement[index]
        if char == '"':
            quoted = not quoted
            output.append(ord('"'))
            index += 1
            continue
        if not quoted:
            folded = statement[index:].casefold()
            keyword = next((word for word in _KEYWORDS
                            if folded.startswith(word)), None)
            if keyword is not None:
                output.append(_TOKENS[keyword])
                index += len(keyword)
                if keyword == 'rem':
                    output.extend(_petscii(item)
                                  for item in statement[index:])
                    break
                continue
        output.append(_petscii(char))
        index += 1
    if quoted:
        raise ValueError('Generated BASIC contains an unterminated string.')
    return bytes(output)


def tokenize_basic_v2(source):
    """Return a loadable $0801 PRG from numbered printable-ASCII source."""
    if not isinstance(source, str) or not source:
        raise ValueError('Generated BASIC source is empty.')
    records = []
    previous = -1
    for raw_line in source.splitlines():
        match = _LINE.fullmatch(raw_line)
        if match is None:
            raise ValueError('Generated BASIC contains an invalid source line.')
        number = int(match.group(1))
        if not 0 <= number <= 63999 or number <= previous:
            raise ValueError('Generated BASIC line numbers must increase.')
        previous = number
        records.append((number, _tokenize_statement(match.group(2))))
    address = 0x0801
    output = bytearray((address & 255, address >> 8))
    for number, statement in records:
        next_address = address + 5 + len(statement)
        if next_address > 0xFFFF:
            raise ValueError('Generated BASIC program is too large.')
        output.extend((next_address & 255, next_address >> 8,
                       number & 255, number >> 8))
        output.extend(statement)
        output.append(0)
        address = next_address
    output.extend((0, 0))
    return bytes(output)
