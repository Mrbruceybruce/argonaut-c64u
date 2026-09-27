"""Local, deterministic wire fixture. Never connects to a physical device.

Arguments (including synthetic passwords) are retained only for assertions,
never logged. Independent control/data sockets exercise the real client parser.
"""
import socket
import socketserver
import threading


class FakeC64UFtp:
    def __init__(self, *, listing=b'type=file;size=3; game.d64\r\n',
                 list_data=b'-rw-rw-rw- 1 user ftp 3 Sep 07 2026 game.d64\r\n',
                 feat=b'211-Features:\r\n MLSD\r\n MLST type*;size*;modify*;\r\n211 End\r\n',
                 replies=None, files=None, completion=b'226 Complete\r\n',
                 welcome=b'220 C64U fixture\r\n', split=False,
                 data_wait=None, completion_wait=None, coalesced=False):
        self.listing, self.list_data, self.feat = listing, list_data, feat
        self.replies = replies or {}
        self.files = dict(files or {b'/file': b'abc'})
        self.completion, self.welcome, self.split = completion, welcome, split
        self.data_wait, self.completion_wait = data_wait, completion_wait
        self.coalesced = coalesced
        self.commands = []
        self.connections = 0
        self.live = 0
        self.data_started = threading.Event()
        self.closed = threading.Event()
        self.pasv_ports = []
        self._lock = threading.Lock()
        fixture = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                listener = None
                cwd = b'/'
                with fixture._lock:
                    fixture.connections += 1
                    fixture.live += 1
                self.connection.settimeout(3)

                def send(data):
                    if fixture.split:
                        for offset in range(0, len(data), 3):
                            self.connection.sendall(data[offset:offset+3])
                    else:
                        self.connection.sendall(data)
                try:
                    send(fixture.welcome)
                    while True:
                        line = self.rfile.readline(65536)
                        if not line:
                            break
                        verb, _, argument = line[:-2].partition(b' ')
                        with fixture._lock:
                            fixture.commands.append((verb, argument))
                        if verb in fixture.replies:
                            reply = fixture.replies[verb]
                            if reply is None:
                                return
                            send(reply)
                            continue
                        if verb == b'USER':send(b'331 Password required\r\n')
                        elif verb == b'PASS':send(b'230 Welcome\r\n')
                        elif verb == b'FEAT':send(fixture.feat)
                        elif verb == b'TYPE':send(b'200 Type set\r\n')
                        elif verb == b'CWD':
                            cwd=argument;send(b'250 Directory changed\r\n')
                        elif verb == b'PWD':send(b'257 \"'+cwd.replace(b'\"',b'\"\"')+b'\"\r\n')
                        elif verb == b'SIZE':
                            if argument not in fixture.files:send(b'550 Missing\r\n')
                            else:send(b'213 '+str(len(fixture.files[argument])).encode()+b'\r\n')
                        elif verb == b'PASV':
                            if listener:listener.close()
                            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            listener.bind(('127.0.0.1', 0));listener.listen(1);listener.settimeout(2)
                            port = listener.getsockname()[1]
                            fixture.pasv_ports.append(port)
                            # Deliberately unrelated advertised IP: client must use peer.
                            send(f'227 Passive (203,0,113,8,{port//256},{port%256})\r\n'.encode())
                        elif verb in (b'MLSD',b'LIST',b'RETR',b'STOR'):
                            if verb == b'RETR' and argument not in fixture.files:
                                send(b'550 Missing\r\n');continue
                            send(b'150 Opening\r\n' + (fixture.completion if fixture.coalesced else b''))
                            data, _ = listener.accept()
                            with data:
                                data.settimeout(2)
                                fixture.data_started.set()
                                if fixture.data_wait:fixture.data_wait.wait(2)
                                if verb == b'STOR':
                                    content = bytearray()
                                    while True:
                                        block = data.recv(8192)
                                        if not block:break
                                        content.extend(block)
                                    fixture.files[argument] = bytes(content)
                                else:
                                    content = (fixture.listing if verb == b'MLSD' else
                                               fixture.list_data if verb == b'LIST' else fixture.files[argument])
                                    data.sendall(content)
                            if fixture.completion_wait:fixture.completion_wait.wait(2)
                            if fixture.completion is None:return
                            if not fixture.coalesced:send(fixture.completion)
                        else:send(b'502 Unsupported\r\n')
                except (OSError, ValueError):
                    # Expected when the client poisons/closes an interrupted lease.
                    pass
                finally:
                    if listener:listener.close()
                    with fixture._lock:fixture.live -= 1
                    fixture.closed.set()

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = True

        self._server = Server(('127.0.0.1', 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={'poll_interval': .01}, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        if self.data_wait:self.data_wait.set()
        if self.completion_wait:self.completion_wait.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(2)

    @property
    def verbs(self):
        return [verb for verb, _ in self.commands]
