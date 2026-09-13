import json
import unittest
from unittest.mock import patch
from c64u_browser.api import BrowserError
from c64u_browser.local_networks import local_networks,parse_linux,parse_macos,parse_windows

class LocalNetworksTests(unittest.TestCase):
    def test_macos_active_interfaces_hex_and_dotted_masks(self):
        data='''lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
    inet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500
    inet 192.168.68.20 netmask 0xfffffc00 broadcast 192.168.71.255
    status: active
en1: flags=8863<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500
    inet 10.0.0.2 netmask 255.255.255.0 broadcast 10.0.0.255
    status: active
en2: flags=8863<UP,BROADCAST,RUNNING,MULTICAST> mtu 1500
    inet 192.168.3.2 netmask 0xffffff00
    status: inactive
'''
        self.assertEqual(parse_macos(data),['10.0.0.0/24','192.168.68.0/22'])
        with patch('c64u_browser.local_networks.sys.platform','darwin'),patch('c64u_browser.local_networks.subprocess.check_output',return_value=data) as command:
            self.assertEqual(local_networks(),parse_macos(data))
            self.assertEqual(command.call_args.args[0],['/sbin/ifconfig','-a'])

    def test_windows_arrays_singletons_and_empty(self):
        row={'IPAddress':'192.168.68.22','PrefixLength':22}
        self.assertEqual(parse_windows(json.dumps(row)),['192.168.68.0/22'])
        self.assertEqual(parse_windows(json.dumps([row,row,{'IPAddress':'127.0.0.1','PrefixLength':8},{'IPAddress':'169.254.2.3','PrefixLength':16} ])),['192.168.68.0/22'])
        self.assertEqual(parse_windows('[]'),[])
        with patch('c64u_browser.local_networks.sys.platform','win32'),patch('c64u_browser.local_networks.subprocess.check_output',return_value=json.dumps(row)) as command:
            self.assertEqual(local_networks(),['192.168.68.0/22'])
            self.assertIn('-NoProfile',command.call_args.args[0])
            self.assertIn('ConnectionState',command.call_args.args[0][-1])

    def test_linux_and_enumeration_failure(self):
        self.assertEqual(parse_linux(json.dumps([{'ifname':'eth0','addr_info':[{'local':'192.168.1.9','prefixlen':24,'scope':'global'}]}])),['192.168.1.0/24'])
        with patch('c64u_browser.local_networks.subprocess.check_output',side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(BrowserError,'Could not read'):local_networks()

    def test_no_network_is_not_reported_as_zero_replies(self):
        from c64u_browser.discovery import ident_scan
        with patch('c64u_browser.discovery.local_networks',return_value=[]),patch('c64u_browser.discovery.socket.socket'):
            with self.assertRaisesRegex(BrowserError,'No connected'):ident_scan()
