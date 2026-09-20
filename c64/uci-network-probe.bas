10 print chr$(147);"argonaut network interface probe"
20 c=57116:d=57117:r=57118:s=57119:a$="":b$=""
30 i=peek(d):if i<>201 and i<>73 then print "command interface not found":end
40 if (peek(c) and 48)<>0 then print "uci busy; retry later":end
50 poke d,3:poke d,1:poke c,1
60 t=ti
70 v=peek(c):if (v and 48)>=32 then 100
80 if ti-t>300 then poke c,4:print "network probe timed out":end
90 goto 70
100 if (peek(c) and 128)<>0 then a$=a$+chr$(peek(r)):goto 100
110 if (peek(c) and 64)<>0 then b$=b$+chr$(peek(s)):goto 110
120 if (peek(c) and 48)=48 then poke c,2:goto 60
150 poke c,2
160 if left$(b$,2)="00" then print "uci network ready":print a$:end
170 print "network target unavailable":print "status: ";b$:end
