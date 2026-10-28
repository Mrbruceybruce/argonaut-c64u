"""Issue #49 bounded source-derived MODEL, not compiled firmware or FPGA emulation.

Pin: GideonZ/1541ultimate 7b628eb166872965ea59d66f90ffd9bcf7d71d8a.
Only Off/Fixed/SID rendering is implemented. No transport or application imports.
Generators retain stack/local samples across actual source blocking boundaries.
DATA buckets are observational, not a claim about FPGA interpretation.
"""
from dataclasses import dataclass
from pathlib import Path
import json

PIN = '7b628eb166872965ea59d66f90ffd9bcf7d71d8a'
TABLES = json.loads(Path(__file__).with_name('led_mapping_tables.json').read_text())


@dataclass
class Stored:
    mode: str = 'Off'
    autosid: int = 0
    pattern: int = 0
    intensity: int = 1
    selector: int = 0
    color: int = 0  # Red
    tint: int = 0   # Pure


class InvalidFixture(ValueError):
    pass


class LED:
    def __init__(self, bank, **fields):
        if bank not in ('keyboard', 'strip'):
            raise InvalidFixture(bank)
        self.bank = bank
        self.stored = Stored(**fields)
        self.speed = 10
        self.offset = self.timeout = self.rainbow_hue = self.soft_start = 0
        self.model = 2
        self.installed = True
        self.mapping = [0] * 252
        self.colors = [0] * 252
        self.regs = {'MAP': 0, 'EN': 0, 'INTENSITY': 0, 'FROM': 0, 'START': 0}
        self.trace = []
        self.tick = 0
        self.actor = 'setup'
        self.hooks = self.effects = 0
        self.envelopes = [0] * 32
        self.queue = []
        self.shift_lock = True
        self.cut = None
        self.effectuate()
        self.trace.clear()
        self.hooks = self.effects = 0
        self.actor = 'http'
        self.task = self.loop()
        self.wait = None

    def log(self, *event):
        self.trace.append((self.tick, self.actor, *event))

    def write(self, reg, value, address=None):
        context = self.regs['MAP']
        self.log('write', reg, address, value, context)
        if reg == 'DATA':
            if not 0 <= address < 252 or not 0 <= value <= 255:
                raise InvalidFixture('DATA bounds')
            (self.mapping if context == 1 else self.colors)[address] = value
        else:
            self.regs[reg] = value
        if reg == 'MAP' and value == 1 and self.cut is not None:
            action, self.cut = self.cut, None
            action()

    def data(self, address, values):
        for n, value in enumerate(values):
            self.write('DATA', value, address + n)

    def map(self, name):
        self.log('mapping', name)
        self.mapping_name = name
        self.write('MAP', 1)
        if name == 'Single':
            for led in range(84):
                self.data(led * 3, (0, 1, 2))
            if self.bank == 'keyboard':
                self.data(210, (3, 4, 5))
        elif name == 'Direct':
            for i in range(252):
                self.write('DATA', i, i)
        else:
            for address, value in TABLES[self.bank][name]:
                self.write('DATA', value, address)
        self.write('MAP', 0)

    def configure(self):
        names = ['Single', 'Left', 'Right', 'Serpentine', 'Center']
        if self.bank == 'keyboard':
            names[3] = 'Circular1' if self.mode == 'SID' else 'Circular2'
            self.map(names[self.pattern])
            self.speed = [16, 12, 12, 12 if self.mode == 'SID' else 5, 12][self.pattern]
            self.write('MAP', 2)
        else:
            self.map(names[self.pattern])

    def effectuate(self):
        self.effects += 1
        self.log('effectuate')
        for field, value in vars(self.stored).items():
            setattr(self, field, value)
        if self.mode == 'Default':
            self.mode = 'Rainbow' if self.model == 1 else 'Fixed'
            if self.model != 1:
                self.color = 25 if self.bank == 'keyboard' else 3
        if self.mode in ('Off', 'Fixed'):
            self.map('Single')
        elif self.mode == 'Sparkle' and self.bank == 'strip':
            self.map('Direct')
        else:
            self.configure()
        if self.bank == 'keyboard':
            self.write('MAP', 2)

    def callback(self, field, value):
        if self.actor == 'renderer':
            raise InvalidFixture('HTTP cannot interrupt running priority-3 renderer')
        limits = {'autosid': 1, 'pattern': 4, 'intensity': 31, 'selector': 7,
                  'color': 24, 'tint': 3}
        valid = (value in ('Off', 'Fixed', 'SID', 'Rainbow', 'Rainbow Sparkle', 'Default')
                 or (self.bank == 'strip' and value == 'Sparkle')) if field == 'mode' else (
                     field in limits and type(value) is int and 0 <= value <= limits[field])
        if not valid:
            self.log('invalid', field, value)
            return False
        setattr(self.stored, field, value)
        self.hooks += 1
        self.log('hook', field, value)
        self.effectuate()
        self.log('menu_update')
        if self.bank == 'keyboard':
            if field == 'mode':
                self.write('MAP', 0)
                for i in range(252):
                    self.write('DATA', 0, i)
            self.write('MAP', 2)
        return True

    def post(self, fields):
        results = [self.callback(k, v) for k, v in fields]
        self.log('store_close')
        return all(results)

    def sample(self):
        values = tuple(self.envelopes[4 * self.selector + i] for i in range(3))
        self.log('sample', self.selector, values)
        return values

    def enter_sid(self, total, timeout_first=False):
        if self.autosid and total > 0:
            if timeout_first:
                self.timeout = 600
            self.configure()
            self.mode = 'SID'
            self.timeout = 600
            self.log('entry', self.mode, self.mapping_name, self.timeout)

    def fixed_rgb(self):
        # Exact ordinary Red/Pure/Bright fixture only; unsupported colors fail closed.
        if self.color != 0 or self.tint not in (0, 1):
            raise InvalidFixture('Fixed renderer supports Red/Pure/Bright only')
        white = (0, 50)[self.tint]
        rgb = (255, white, white)
        return (rgb[1], rgb[0], rgb[2]) if self.bank == 'keyboard' else rgb

    def loop(self):
        while True:
            if self.bank == 'keyboard':
                key = yield ('queue', self.speed)
                if key == 0x41:
                    self.data(250, (192 if self.shift_lock else 0,))
                    self.data(249, (160 if self.shift_lock else 0,))
                    self.data(251, (0,))
            values = self.sample()
            total = sum(values)
            self.write('INTENSITY', self.intensity << 2)
            branch = self.mode
            if branch in ('Off', 'Fixed'):
                self.offset = 0
                if self.bank == 'strip':
                    if branch == 'Off':
                        self.write('INTENSITY', 0)
                    else:
                        self.write('EN', 1)
                        self.write('INTENSITY', self.intensity << 2)
                self.data(0, (0, 0, 0) if branch == 'Off' else self.fixed_rgb())
                if self.bank == 'keyboard':
                    self.data(3, (255, 0, 0))
                self.write('FROM', 0)
                self.write('START', 0)
                if self.bank == 'strip' and branch == 'Off':
                    yield ('delay', 200)
                    self.log('off_resume', total, self.mode, self.autosid, self.pattern)
                self.enter_sid(total, branch == 'Off')
                if self.bank == 'strip':
                    if branch == 'Off':
                        self.write('EN', 0)
                        self.log('off_boundary', self.mode, self.timeout)
                    else:
                        yield ('delay', 50)
            elif branch == 'SID':
                if self.bank == 'strip':
                    self.write('EN', 1)
                    self.write('INTENSITY', self.intensity << 2)
                data = (values[1], values[0], values[2]) if self.bank == 'keyboard' else values
                self.data(self.offset, data)
                self.write('FROM', self.offset)
                self.offset = (210 if self.bank == 'keyboard' else 249) if self.offset == 0 else self.offset - 3
                self.write('START', 0)
                if self.autosid:
                    if total:
                        self.timeout = 600
                    elif self.timeout <= 0:
                        self.effectuate()
                    else:
                        self.timeout -= self.speed if self.bank == 'keyboard' else 3
                if self.bank == 'strip':
                    yield ('delay', 3)
            else:
                raise InvalidFixture('Renderer branch outside bounded scope: ' + branch)

    def run_to_block(self, key=None, first=False):
        previous, self.actor = self.actor, 'renderer'
        try:
            boundary = next(self.task) if first else self.task.send(key)
            count = 0
            while boundary[0] == 'queue' and self.queue:
                count += 1
                if count > 16:
                    raise InvalidFixture('queue exceeds declared hardware capacity')
                boundary = self.task.send(self.queue.pop(0))
            self.wait = (boundary[0], self.tick + boundary[1])
            self.log('block', *self.wait)
        finally:
            self.actor = previous

    def start(self):
        if self.wait is not None:
            raise InvalidFixture('already started')
        self.run_to_block(first=True)

    def wake(self, tick, key=None, burst=()):
        if self.wait is None or tick < self.tick:
            raise InvalidFixture('missing wait or backwards time')
        kind, deadline = self.wait
        if burst and key is None:
            raise InvalidFixture('burst requires explicit IRQ wake')
        if len(burst) > 15:
            raise InvalidFixture('IRQ burst exceeds queue capacity')
        if key is not None:
            if kind != 'queue' or tick > deadline:
                raise InvalidFixture('key must arrive by pending queue deadline')
            self.tick = tick
            self.actor = 'irq'
            for index, value in enumerate((key, *burst)):
                self.log('irq', 'RX_DATA', value, 'RX_FLAGS', 3 if self.shift_lock else 1)
                self.log('irq', 'RX_GET', 1, 'RX_DATA_AVAILABLE', 0 if index == len(burst) else 1)
            self.queue.extend(burst)
            self.actor = 'http'
        elif tick != deadline:
            raise InvalidFixture('timeout/delay must wake at its deadline')
        self.tick = tick
        self.actor = 'scheduler'
        self.log('wake', 'key' if key is not None else kind)
        self.actor = 'http'
        self.run_to_block(key)

    def advance_blocked(self, tick):
        if self.wait is None or not self.tick <= tick < self.wait[1]:
            raise InvalidFixture('HTTP only runs strictly before renderer deadline')
        self.tick = tick
