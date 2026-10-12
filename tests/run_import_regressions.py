"""Run explicit offline regression modules; forbid non-loopback socket endpoints."""
import ipaddress
import socket
import sys
import unittest

def guard(original):
    def call(sock, address, *args):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0]
            if not ipaddress.ip_address(host).is_loopback:
                raise AssertionError('Non-loopback networking forbidden during import regressions')
        return original(sock, address, *args)
    return call

socket.socket.connect = guard(socket.socket.connect)
socket.socket.connect_ex = guard(socket.socket.connect_ex)
socket.socket.bind = guard(socket.socket.bind)
unittest.main(module=None, argv=[sys.argv[0], *sys.argv[1:]])
