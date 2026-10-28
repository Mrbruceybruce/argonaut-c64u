"""Independent expectations from Issue #49 QUALIFIED PASS; model-only coverage."""
import unittest
from led_characterization import LED, InvalidFixture

CHARACTERIZATION_TRACES = {}


def events(m, kind):
    return [e[2:] for e in m.trace if e[2] == kind]


def writes(m, actor=None):
    return [e[2:] for e in m.trace if e[2] == 'write' and (actor is None or e[1] == actor)]


class LEDCharacterization(unittest.TestCase):
    def test_strip_off_four_schedules(self):
        for active, callback in [(True, False), (False, False), (True, True), (False, True)]:
            with self.subTest(active=active, callback=callback):
                m = LED('strip', autosid=1, pattern=3)
                m.envelopes[0] = int(active)
                m.start()
                self.assertEqual(m.wait, ('delay', 200))
                m.advance_blocked(100)
                m.envelopes[0] = int(not active)
                if callback:
                    m.callback('mode', 'Fixed')
                m.wake(200)
                self.assertEqual(events(m, 'off_resume'), [('off_resume', int(active), 'Fixed' if callback else 'Off', 1, 3)])
                self.assertEqual(events(m, 'off_boundary'), [('off_boundary', 'SID' if active else ('Fixed' if callback else 'Off'), 600 if active else 0)])
                self.assertEqual(m.wait, ('delay', 203 if active else (250 if callback else 400)))
                self.assertEqual((m.mode, m.timeout), ('SID', 597) if active else (('SID', 600) if callback else ('Off', 0)))
                self.assertEqual(events(m, 'sample'), [('sample', 0, (int(active), 0, 0)), ('sample', 0, (int(not active), 0, 0))])
                # Independently stated raw oracle: strip mappings and RGB order.
                def reg(name, value, context=0):
                    return ('write', name, None, value, context)
                def data(values):
                    return [('write','DATA',a,v,0) for a,v in enumerate(values)]
                def mapping(pairs):
                    return [reg('MAP',1)]+[('write','DATA',a,v,1) for a,v in pairs]+[reg('MAP',0,1)]
                # Serpentine destination order from the reviewed source contract.
                dest = [*range(60,84), *range(59,29,-1), *range(30)]
                serp = mapping([(3*led+c,3*i+c) for i,led in enumerate(dest) for c in range(3)])
                off = [reg('INTENSITY',4),reg('INTENSITY',0)]+data([0,0,0])+[reg('FROM',0),reg('START',0)]
                expected = off[:]
                if callback:
                    expected += mapping([(a,a%3) for a in range(252)])
                if active:
                    expected += serp
                expected += [reg('EN',0)]
                if active:
                    expected += [reg('INTENSITY',4),reg('EN',1),reg('INTENSITY',4)]+data([0,0,0])+[reg('FROM',0),reg('START',0)]
                elif callback:
                    expected += [reg('INTENSITY',4),reg('EN',1),reg('INTENSITY',4)]+data([255,0,0])+[reg('FROM',0),reg('START',0)]+serp
                else:
                    expected += off
                self.assertEqual(writes(m),expected)
                CHARACTERIZATION_TRACES[f'strip-{active}-{callback}'] = m.trace[:]
                en = [w[3] for w in writes(m) if w[1] == 'EN']
                self.assertEqual(en, [0, 1] if active or callback else [0])
                self.assertTrue(all(e[1] == 'renderer' for e in m.trace if e[0] == 200 and e[2] != 'wake'))
                if not active and not callback:
                    m.wake(400)
                    self.assertEqual((m.mode, m.timeout, m.wait), ('SID', 600, ('delay', 403)))

    def test_strip_off_live_autosid_and_pattern(self):
        for before, after, expected in [(1, 0, 'Off'), (0, 1, 'SID')]:
            m = LED('strip', autosid=before, pattern=3)
            m.envelopes[0] = 1
            m.start(); m.advance_blocked(100)
            m.callback('autosid', after)
            m.callback('pattern', 2)
            m.wake(200)
            self.assertEqual(events(m, 'off_boundary'), [('off_boundary', expected, 600 if after else 0)])
            if after:
                self.assertEqual(m.mapping_name, 'Right')

    def test_strip_selector_keeps_old_sample(self):
        m = LED('strip', autosid=1, pattern=3)
        m.envelopes[0] = 1
        m.start(); m.advance_blocked(100); m.callback('selector', 7); m.wake(200)
        self.assertEqual(events(m, 'sample'), [('sample', 0, (1, 0, 0)), ('sample', 7, (0, 0, 0))])
        self.assertEqual((m.mode, m.timeout), ('SID', 597))

    def test_keyboard_mapping_preemption_exact_trace(self):
        for wake in ('key', 'timeout', 'none'):
            with self.subTest(wake=wake):
                m = LED('keyboard', mode='Fixed')
                m.start(); m.advance_blocked(1)
                if wake != 'none':
                    m.cut = lambda: m.wake(1, 0x41) if wake == 'key' else m.wake(10)
                m.callback('intensity', 1)
                render = writes(m, 'renderer')
                expected = []
                if wake == 'key':
                    expected += [('write', 'DATA', a, v, 1) for a, v in [(250,192),(249,160),(251,0)]]
                    self.assertIn(('irq', 'RX_GET', 1, 'RX_DATA_AVAILABLE', 0), events(m, 'irq'))
                if wake != 'none':
                    expected += [('write','INTENSITY',None,4,1)]
                    expected += [('write','DATA',a,v,1) for a,v in enumerate([0,255,0,255,0,0])]
                    expected += [('write','FROM',None,0,1),('write','START',None,0,1)]
                self.assertEqual(render, expected)
                CHARACTERIZATION_TRACES['keyboard-'+wake] = m.trace[:]
                http = writes(m, 'http')
                expected_http = [('write','MAP',None,1,2)]
                expected_http += [('write','DATA',a,a%3,1) for a in range(252)]
                expected_http += [('write','DATA',a,v,1) for a,v in [(210,3),(211,4),(212,5)]]
                expected_http += [('write','MAP',None,0,1),('write','MAP',None,2,0),('write','MAP',None,2,2)]
                self.assertEqual(http, expected_http)
                self.assertEqual((m.hooks,m.effects,m.regs['MAP']), (1,1,2))
                self.assertEqual(m.mapping, [a%3 if not 210<=a<=212 else a-207 for a in range(252)])
                if wake != 'none':
                    block = max(i for i,e in enumerate(m.trace) if e[2]=='block')
                    first_http_data = next(i for i,e in enumerate(m.trace) if e[1]=='http' and e[2:4]==('write','DATA'))
                    self.assertLess(block, first_http_data)
                    self.assertEqual(m.wait, ('queue',11 if wake=='key' else 20))

    def test_keyboard_pending_deadline_and_queue_drain(self):
        m = LED('keyboard', pattern=1)
        m.start(); m.advance_blocked(1); m.callback('mode','SID')
        self.assertEqual((m.speed,m.wait),(12,('queue',10)))
        m.wake(10)
        self.assertEqual(len(events(m,'sample')),1)
        self.assertEqual(m.wait,('queue',22))
        burst=LED('keyboard',mode='Fixed');burst.start()
        burst.wake(1,0x41,burst=(0x41,0x41))
        self.assertEqual(len(events(burst,'sample')),3)
        self.assertEqual(burst.wait,('queue',11))
        self.assertEqual([e[-1] for e in events(burst,'irq') if e[1]=='RX_GET'],[1,1,0])
        for pattern, speed in [(0,16),(1,12),(3,12)]:
            k=LED('keyboard',mode='SID',pattern=pattern);k.start()
            self.assertEqual(k.wait,('queue',speed))
        k=LED('keyboard',autosid=1,pattern=3);k.envelopes[0]=1;k.start();k.wake(1,0x41)
        self.assertEqual(k.wait,('queue',6))

    def test_invalid_schedule_rejected(self):
        m=LED('strip');m.start()
        for tick,key in [(199,None),(200,0x41),(201,None)]:
            with self.assertRaises(InvalidFixture):m.wake(tick,key)
        m.actor='renderer'
        with self.assertRaises(InvalidFixture):m.callback('intensity',1)

    def test_mode_pattern_order_and_color_clear(self):
        for fields,speed in [([('mode','Off'),('pattern',3)],16),([('pattern',3),('mode','Off')],5)]:
            m=LED('keyboard',mode='Rainbow')
            m.colors=[123]*252
            self.assertTrue(m.post(fields))
            self.assertEqual((m.mode,m.pattern,m.speed,m.mapping_name),('Off',3,speed,'Single'))
            self.assertEqual(m.colors,[0]*252)
            self.assertEqual((m.hooks,m.effects),(2,2))

    def test_explicit_automatic_pattern_and_callback(self):
        explicit=LED('keyboard',mode='SID',pattern=3)
        self.assertEqual((explicit.mapping_name,explicit.speed),('Circular1',12))
        for mode in ('Off','Fixed'):
            m=LED('keyboard',mode=mode,autosid=1,pattern=3)
            m.envelopes[0]=1;m.start();m.wake(10)
            self.assertEqual((m.mode,m.mapping_name,m.speed,m.timeout),('SID','Circular2',5,600))
            m.advance_blocked(11);m.callback('intensity',1)
            self.assertEqual((m.mode,m.mapping_name,m.speed,m.timeout),(mode,'Single',5,600))
            m.envelopes[0]=0;m.wake(15)
            self.assertEqual(m.mode,mode)
            m.envelopes[0]=1;m.wake(20)
            self.assertEqual((m.mode,m.timeout),('SID',600))

    def test_same_value_and_valid_invalid_valid(self):
        for bank in ('strip','keyboard'):
            m=LED(bank)
            self.assertTrue(m.post([('intensity',1)]))
            self.assertEqual((m.hooks,m.effects),(1,1))
            self.assertFalse(m.post([('intensity',31),('mode','INVALID'),('tint',1)]))
            self.assertEqual((m.stored.intensity,m.stored.mode,m.stored.tint,m.hooks,m.effects),(31,'Off',1,3,3))

    def test_timeout_boundaries(self):
        for bank,pattern,d in [('keyboard',0,16),('keyboard',3,12),('strip',3,3)]:
            for initial,steps in [(0,1),(1,2),(d,2),(d+1,3),(600,{16:39,12:51,3:201}[d])]:
                m=LED(bank,mode='SID',autosid=1,pattern=pattern)
                m.timeout=initial
                # Strip first iteration runs before its first delay; keyboard after receive.
                if bank=='keyboard':m.start()
                for i in range(steps):
                    if bank=='strip' and i==0:m.start()
                    else:m.wake(m.wait[1])
                    self.assertEqual(m.effects, int(i==steps-1))
                m.wake(m.wait[1]);self.assertEqual(m.effects,2)
        m=LED('keyboard',autosid=1,pattern=3);m.envelopes[0]=1;m.start();m.wake(10)
        m.envelopes[0]=0
        for i in range(121):
            m.wake(m.wait[1]);self.assertEqual(m.effects,int(i==120))
        self.assertEqual(m.mode,'Off')

    def test_intensity_selector_and_envelope_boundaries(self):
        for bank in ('keyboard','strip'):
            for j in range(8):
                for intensity in (0,1,31):
                    m=LED(bank,mode='SID',selector=j,intensity=intensity,autosid=1)
                    m.envelopes=[255]*32
                    m.envelopes[4*j:4*j+3]=[0,0,0]
                    m.start()
                    if bank=='keyboard':m.wake(m.wait[1])
                    self.assertEqual(events(m,'sample')[-1],('sample',j,(0,0,0)))
                    self.assertEqual(m.effects,1)
                    m.envelopes[4*j:4*j+3]=[255]*3;m.wake(m.wait[1])
                    self.assertEqual((m.timeout,m.regs['INTENSITY']),(600,4*intensity))
                    self.assertEqual(events(m,'sample')[-1],('sample',j,(255,255,255)))
            m=LED(bank,mode='SID',autosid=0);m.timeout=7;m.start()
            if bank=='keyboard':m.wake(m.wait[1])
            self.assertEqual((m.timeout,m.effects),(7,0))

    def test_strip_mapping_full_independent_oracle(self):
        holes=[72,73,74,162,163,164]
        for prior,retained in [('Direct',[72,73,74,162,163,164]),('Single',[0,1,2,0,1,2]),('Right',[30,31,32,33,34,35])]:
            m=LED('strip');m.map(prior);before=m.mapping[:];m.trace.clear();m.map('Left')
            expected=before[:];ordered=[]
            for i in range(24):
                for base,value in [(3*i,9*i),(90+3*i,9*i+3),(180+3*i,9*i+6)]:
                    for c in range(3):expected[base+c]=value+c;ordered.append((base+c,value+c))
            for i in range(25,30):
                for base,value in [(3*i,216+6*(i-25)),(90+3*i,219+6*(i-25))]:
                    for c in range(3):expected[base+c]=value+c;ordered.append((base+c,value+c))
            self.assertEqual(m.mapping,expected)
            self.assertEqual([m.mapping[a] for a in holes],retained)
            self.assertEqual(writes(m),[('write','MAP',None,1,0)]+[('write','DATA',a,v,1) for a,v in ordered]+[('write','MAP',None,0,1)])
            self.assertEqual(len(set(a for a,v in ordered)),246)

    def test_pattern_dispatch_controls(self):
        for mode in ('SID','Rainbow'):
            for p,name in enumerate(['Single','Left','Right','Circular1' if mode=='SID' else 'Circular2','Center']):
                m=LED('keyboard',mode=mode,pattern=p)
                self.assertEqual((m.mapping_name,m.speed),(name,[16,12,12,12 if mode=='SID' else 5,12][p]))
        for p,name in enumerate(['Single','Left','Right','Serpentine','Center']):
            self.assertEqual(LED('strip',mode='SID',pattern=p).mapping_name,name)
