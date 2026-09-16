# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Generate a private C64 BASIC link probe without committing its pairing token."""
import ipaddress


def _quoted(value):
    if (not isinstance(value, str) or not value or '"' in value
            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
        raise ValueError('C64 bridge values must be printable ASCII.')
    return '"' + value + '"'


def _render_client(host, port, token, interactive):
    host = str(ipaddress.IPv4Address(host))
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Use a bridge port from 1024 to 65535.')
    if (not isinstance(token, str) or not 32 <= len(token) <= 96
            or not token.isascii() or not token.isalnum()
            or token != token.upper()):
        raise ValueError('Use a 32 to 96 character uppercase alphanumeric bridge token.')
    # PETCAT converts lowercase source letters to unshifted ASCII-range PETSCII.
    # Uppercase source letters use shifted codes above 127, unsuitable on TCP.
    question = 'say hello to bruce in five words.'
    if interactive:
        request = (_quoted('argonaut/1 ' + token.lower() + ' ')
                   + '+mid$(str$(len(q$)),2)+chr$(10)+q$')
        title = 'argonaut local ai'
        question_line = '40 input "ask argonaut (blank exits)";q$:if q$="" then end'
        request_line = '45 if len(q$)>80 then print "question is too long":goto 40'
    else:
        request = (_quoted('argonaut/1 ' + token.lower() + ' ' + str(len(question)))
                   + '+chr$(10)+' + _quoted(question))
        title = 'argonaut local ai link probe'
        question_line = f'40 q$={_quoted(question)}'
        request_line = None
    lines = [
        f'10 print chr$(147);{_quoted(title)}',
        f'20 c=57116:d=57117:r=57118:s=57119:h$={_quoted(host)}:p={port}',
        '30 i=peek(d):if i<>201 and i<>73 then print "command interface not found":end',
        question_line,
        '50 x$=' + request,
        '60 m$=chr$(3)+chr$(7)+chr$(p and 255)+chr$(int(p/256))+h$+chr$(0):gosub 5000',
        '70 if left$(s$,2)<>"00" or len(a$)<1 then print "could not open bridge":print s$:goto 900',
        '80 k=asc(left$(a$,1))',
        '90 m$=chr$(3)+chr$(17)+chr$(k)+x$:gosub 5000',
        '100 if left$(s$,2)<>"00" then print "could not send question":print s$:goto 800',
        '110 w$="":e$=chr$(10):h=0',
        '112 for x=1 to 240',
        '115 m$=chr$(3)+chr$(16)+chr$(k)+chr$(250)+chr$(0):gosub 5000',
        '117 if left$(s$,2)="02" then gosub 7000:goto 145',
        '118 if left$(s$,2)<>"00" and left$(s$,2)<>"01" then print "no bridge reply":print s$:goto 800',
        '120 b$="":if len(a$)>2 then b$=mid$(a$,3)',
        '121 if h=1 and len(b$)>0 then print b$:goto 800',
        '122 if h=0 and len(b$)>0 then w$=w$+b$',
        '130 z=0:for y=1 to len(w$):if mid$(w$,y,1)=e$ then z=y:y=len(w$)',
        '135 next:if z=0 then 140',
        '136 if left$(w$,3)<>"ok " then print "bridge error: ";left$(w$,z-1):goto 800',
        '137 h=1:print "local ai replied:";chr$(13):if len(w$)>z then print mid$(w$,z+1):goto 800',
        '138 w$=""',
        '140 gosub 7000',
        '145 next:print "bridge reply timed out":goto 800',
        '800 m$=chr$(3)+chr$(9)+chr$(k):gosub 5000',
        '900 ' + ('goto 40' if interactive else 'end'),
        '5000 a$="":s$="":if (peek(c) and 48)<>0 then poke c,4',
        '5010 for j=1 to len(m$):poke d,asc(mid$(m$,j,1)):next:poke c,1:t=ti',
        '5020 v=peek(c):if (v and 48)>=32 then 5040',
        '5030 if ti-t>3600 then poke c,4:s$="timeout":return',
        '5035 goto 5020',
        '5040 if (peek(c) and 128)<>0 then a$=a$+chr$(peek(r)):goto 5040',
        '5050 if (peek(c) and 64)<>0 then s$=s$+chr$(peek(s)):goto 5050',
        '5060 if (peek(c) and 48)=48 then poke c,2:t=ti:goto 5020',
        '5070 poke c,2:return',
        '7000 t=ti',
        '7010 if ti-t<15 then 7010',
        '7020 return',
    ]
    if request_line is not None:
        lines.insert(4, request_line)
    return '\n'.join(lines) + '\n'


def render_link_probe(host, port, token):
    """Return BASIC V2 source for one bounded end-to-end local AI question."""
    return _render_client(host, port, token, False)


def render_chat_client(host, port, token):
    """Return BASIC V2 source for an interactive paired local AI prompt."""
    return _render_client(host, port, token, True)
