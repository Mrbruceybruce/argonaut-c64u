10 print chr$(147);"argonaut uci network info"
20 c=57116:d=57117:r=57118:s=57119
30 i=peek(d):if i<>201 and i<>73 then print "command interface not found":end
40 m$=chr$(3)+chr$(2):gosub 5000
50 if left$(s$,2)<>"00" or len(a$)<1 then print "interface count failed: ";s$:end
60 n=asc(left$(a$,1)):print "interfaces:";n
70 if n=0 then print "no uci network interfaces":end
80 for i=0 to n-1
90 m$=chr$(3)+chr$(5)+chr$(i):gosub 5000
100 print "interface";i;" status ";s$
110 if left$(s$,2)<>"00" or len(a$)<12 then 150
120 print "ip ";:o=1:gosub 6000
130 print "mask ";:o=5:gosub 6000
140 print "gateway ";:o=9:gosub 6000
150 next:end
5000 a$="":s$="":if (peek(c) and 48)<>0 then poke c,4
5010 for j=1 to len(m$):poke d,asc(mid$(m$,j,1)):next:poke c,1:t=ti
5020 v=peek(c):if (v and 48)>=32 then 5040
5030 if ti-t>300 then poke c,4:s$="timeout":return
5035 goto 5020
5040 if (peek(c) and 128)<>0 then a$=a$+chr$(peek(r)):goto 5040
5050 if (peek(c) and 64)<>0 then s$=s$+chr$(peek(s)):goto 5050
5060 if (peek(c) and 48)=48 then poke c,2:t=ti:goto 5020
5070 poke c,2:return
6000 for j=0 to 3:print asc(mid$(a$,o+j,1));:if j<3 then print ".";
6010 next:print:return
