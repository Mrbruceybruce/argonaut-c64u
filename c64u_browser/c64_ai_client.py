# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Generate a private C64 BASIC link probe without committing its pairing token."""
import ipaddress


def _quoted(value):
    if (not isinstance(value, str) or not value or '"' in value
            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
        raise ValueError('C64 bridge values must be printable ASCII.')
    return '"' + value + '"'


def render_link_probe(host, port, token):
    """Return BASIC V2 source for one bounded end-to-end local AI question."""
    host = str(ipaddress.IPv4Address(host))
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Use a bridge port from 1024 to 65535.')
    if (not isinstance(token, str) or not 32 <= len(token) <= 96
            or not token.isascii() or not token.isalnum()):
        raise ValueError('Use a 32 to 96 character alphanumeric bridge token.')
    question = 'Say hello to Bruce in five words.'
    crlf = 'chr$(13)+chr$(10)'
    request_start = (_quoted('POST /v1/chat HTTP/1.0') + '+' + crlf + '+'
                     + _quoted('Authorization: Bearer ' + token) + '+' + crlf)
    request_end = (_quoted('Content-Type: text/plain') + '+' + crlf + '+'
                   + _quoted('Content-Length: ' + str(len(question))) + '+'
                   + crlf + '+' + crlf + '+' + _quoted(question))
    lines = [
        '10 print chr$(147);"argonaut local ai link probe"',
        f'20 c=57116:d=57117:r=57118:s=57119:h$={_quoted(host)}:p={port}',
        '30 i=peek(d):if i<>201 and i<>73 then print "command interface not found":end',
        f'40 q$={_quoted(question)}',
        '50 x$=' + request_start,
        '55 x$=x$+' + request_end,
        '60 m$=chr$(3)+chr$(7)+chr$(p and 255)+chr$(int(p/256))+h$+chr$(0):gosub 5000',
        '70 if left$(s$,2)<>"00" or len(a$)<1 then print "could not open bridge":print s$:goto 900',
        '80 k=asc(left$(a$,1))',
        '90 m$=chr$(3)+chr$(17)+chr$(k)+x$:gosub 5000',
        '100 if left$(s$,2)<>"00" then print "could not send question":print s$:goto 800',
        '110 m$=chr$(3)+chr$(16)+chr$(k)+chr$(250)+chr$(0):gosub 5000',
        '120 if left$(s$,2)<>"00" or len(a$)<3 then print "no bridge reply":print s$:goto 800',
        '130 e$=chr$(13)+chr$(10)+chr$(13)+chr$(10):z=0',
        '135 for y=3 to len(a$)-3:if mid$(a$,y,4)=e$ then z=y:y=len(a$)',
        '137 next',
        '140 if z=0 then print "invalid bridge reply":goto 800',
        '150 print "local ai replied:";chr$(13):print mid$(a$,z+4)',
        '800 m$=chr$(3)+chr$(9)+chr$(k):gosub 5000',
        '900 end',
        '5000 a$="":s$="":if (peek(c) and 48)<>0 then poke c,4',
        '5010 for j=1 to len(m$):poke d,asc(mid$(m$,j,1)):next:poke c,1:t=ti',
        '5020 v=peek(c):if (v and 48)>=32 then 5040',
        '5030 if ti-t>3600 then poke c,4:s$="timeout":return',
        '5035 goto 5020',
        '5040 if (peek(c) and 128)<>0 then a$=a$+chr$(peek(r)):goto 5040',
        '5050 if (peek(c) and 64)<>0 then s$=s$+chr$(peek(s)):goto 5050',
        '5060 if (peek(c) and 48)=48 then poke c,2:t=ti:goto 5020',
        '5070 poke c,2:return',
    ]
    return '\n'.join(lines) + '\n'
