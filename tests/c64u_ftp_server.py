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
                 data_wait=None, completion_wait=None, coalesced=False, directories=None,
                 mutation_tree=False, after_mutation=None, mutation_hook=None,
                 transfer_hook=None, readback_data=None, transfer_completion=None):
        self.listing, self.list_data, self.feat = listing, list_data, feat
        self.replies = replies or {}
        self.files = dict(files or {b'/file': b'abc'})
        self.completion, self.welcome, self.split = completion, welcome, split
        self.data_wait, self.completion_wait = data_wait, completion_wait
        self.coalesced = coalesced
        self.directories = None if directories is None else dict(directories)
        self.mutation_tree = mutation_tree
        self.after_mutation = after_mutation or {}
        self.mutation_hook = mutation_hook
        self.transfer_hook = transfer_hook
        self.readback_data = readback_data
        self.transfer_completion = transfer_completion
        self.bytes_transferred = 0
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
                rename_source = None
                with fixture._lock:
                    fixture.connections += 1
                    fixture.live += 1
                self.connection.settimeout(3)
                self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                def send(data):
                    if fixture.split:
                        for offset in range(0, len(data), 3):
                            self.connection.sendall(data[offset:offset+3])
                    else:
                        self.connection.sendall(data)
                def mutation_reply(verb, argument, default):
                    if fixture.mutation_hook:fixture.mutation_hook(verb, argument)
                    reply = fixture.after_mutation.get(verb, default)
                    if callable(reply):reply = reply(argument)
                    if reply is None:return False
                    send(reply)
                    return True

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
                            if callable(reply):reply = reply(argument)
                            if reply is None:
                                return
                            send(reply)
                            continue
                        if verb == b'USER':send(b'331 Password required\r\n')
                        elif verb == b'PASS':send(b'230 Welcome\r\n')
                        elif verb == b'FEAT':send(fixture.feat)
                        elif verb == b'TYPE':send(b'200 Type set\r\n')
                        elif verb == b'CWD':
                            if fixture.directories is not None and argument not in fixture.directories:
                                send(b'550 Missing directory\r\n');continue
                            cwd=argument;send(b'250 Directory changed\r\n')
                        elif verb == b'PWD':send(b'257 \"'+cwd.replace(b'\"',b'\"\"')+b'\"\r\n')
                        elif fixture.mutation_tree and verb in (b'RNFR', b'RNTO', b'MKD', b'DELE', b'RMD'):
                            if verb == b'RNFR':
                                if argument not in fixture.files and argument not in fixture.directories:
                                    send(b'550 Missing source\r\n');continue
                                rename_source = argument
                                reply = b'350 Continue\r\n'
                            elif verb == b'RNTO':
                                if rename_source is None:
                                    send(b'503 RNFR required\r\n');continue
                                if argument in fixture.files or argument in fixture.directories:
                                    send(b'550 Exists\r\n');continue
                                for tree in (fixture.files, fixture.directories):
                                    for path in tuple(tree):
                                        if path == rename_source or path.startswith(rename_source+b'/'):
                                            tree[argument+path[len(rename_source):]] = tree.pop(path)
                                rename_source = None
                                reply = b'250 Renamed\r\n'
                            elif verb == b'MKD':
                                if argument in fixture.directories or argument in fixture.files:
                                    send(b'550 Exists\r\n');continue
                                fixture.directories[argument] = b''
                                reply = b'257 "created"\r\n'
                            elif verb == b'DELE':
                                if argument not in fixture.files:
                                    send(b'550 Missing file\r\n');continue
                                del fixture.files[argument]
                                reply = b'250 Deleted\r\n'
                            else:
                                if argument not in fixture.directories or any(
                                        path.startswith(argument+b'/') for tree in
                                        (fixture.files,fixture.directories) for path in tree):
                                    send(b'550 Missing or nonempty\r\n');continue
                                del fixture.directories[argument]
                                reply = b'250 Removed\r\n'
                            if not mutation_reply(verb, argument, reply):return
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
                            completion = (fixture.transfer_completion(verb, argument)
                                          if fixture.transfer_completion else fixture.completion)
                            send(b'150 Opening\r\n' + (completion if fixture.coalesced else b''))
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
                                    if fixture.mutation_tree:
                                        prefix = cwd.rstrip(b'/')+b'/'
                                        records = []
                                        for path in fixture.directories:
                                            name = path[len(prefix):] if path.startswith(prefix) else b''
                                            if name and b'/' not in name:records.append(b'type=dir; '+name+b'\r\n')
                                        for path, payload in fixture.files.items():
                                            name = path[len(prefix):] if path.startswith(prefix) else b''
                                            if name and b'/' not in name:records.append(b'type=file;size='+str(len(payload)).encode()+b'; '+name+b'\r\n')
                                        fixture.directories[cwd] = b''.join(sorted(records))
                                    listing = fixture.directories[cwd] if verb == b'MLSD' and fixture.directories is not None else fixture.listing
                                    content = (listing if verb == b'MLSD' else
                                               fixture.list_data if verb == b'LIST' else fixture.files[argument])
                                    if verb == b'RETR' and fixture.readback_data:
                                        content = fixture.readback_data(argument, content)
                                    data.sendall(content)
                                    with fixture._lock:fixture.bytes_transferred += len(content)
                            if fixture.transfer_hook:fixture.transfer_hook(verb, argument)
                            if fixture.completion_wait:fixture.completion_wait.wait(2)
                            if completion is None:return
                            if not fixture.coalesced:send(completion)
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
