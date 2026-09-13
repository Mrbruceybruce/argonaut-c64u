import os
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest.mock import patch, Mock
import urllib.error
from c64u_browser.api import UltimateClient, ConnectionFailure, BrowserError
from c64u_browser.profiles import Profile, Preferences
from c64u_browser.discovery import Candidate, verify, dns_name, dns_records, subnet_scan

INFO={'product':'C64 Ultimate','firmware_version':'1.1.0s2','errors':[]}
VERSION={'version':'0.1','errors':[]}

class Connections(unittest.TestCase):
    def response(self, body):
        response=Mock();response.read.return_value=json.dumps(body).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        return response

    @patch('urllib.request.build_opener')
    def test_verified_and_custom_port(self, opener):
        opener.return_value.open.side_effect=[self.response(VERSION),self.response(INFO)]
        client=UltimateClient('test.local','example',http_port=8080)
        self.assertEqual(client.test_connection()['info']['product'],'C64 Ultimate')
        for call in opener.return_value.open.call_args_list:
            self.assertTrue(call.args[0].full_url.startswith('http://test.local:8080/v1/'))

    def test_error_classes(self):
        cases=[(urllib.error.HTTPError('x',403,'Forbidden',{},None),'authentication'),
               (urllib.error.HTTPError('x',404,'Missing',{},None),'api'),
               (urllib.error.URLError(socket.gaierror()),'host'),
               (urllib.error.URLError(ConnectionRefusedError()),'network')]
        for error,kind in cases:
            with self.subTest(kind=kind),patch('urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect=error
                with self.assertRaises(ConnectionFailure) as cm:UltimateClient('test').read_about('info')
                self.assertEqual(cm.exception.kind,kind)

    def test_generic_server_not_device(self):
        with patch.object(UltimateClient,'info',return_value={'version':VERSION,'info':{'product':'Web Server','firmware_version':'1','errors':[]}}):
            with self.assertRaises(ConnectionFailure):UltimateClient('test').test_connection()

    @patch('urllib.request.build_opener')
    def test_invalid_json_and_shape(self, opener):
        for body in [[],{}, {'errors':'oops'}, {'errors':['failed']}]:
            opener.return_value.open.return_value=self.response(body)
            with self.assertRaises(ConnectionFailure) as cm:UltimateClient('test').read_about('info')
            self.assertEqual(cm.exception.kind,'api')

    def test_password_candidate_not_verified(self):
        with patch.object(UltimateClient,'test_connection',side_effect=ConnectionFailure('authentication','Denied')):
            c=verify(Candidate('192.168.68.60'))
            self.assertIsNone(c)
            c=verify(Candidate('192.168.68.60',info={'ident':{'product':'C64 Ultimate'}}))
            self.assertIn('identity unverified',c.status)

    def test_profile_roundtrip_and_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            prefs=Preferences(Path(d)/'argonaut/config.json')
            p=Profile.new('Breadbin','c64.local',http_port=8080,auto_connect=True,
                          serial_number='SN001',case_edition='BASIC Beige',notes='Replacement board')
            other=Profile.new('Second','192.168.68.61')
            prefs.profiles=[p,other];prefs.selected_id=p.id;prefs.save()
            loaded=Preferences(prefs.path).load()
            self.assertEqual(loaded.selected(),p);self.assertEqual(len(loaded.profiles),2)
            self.assertNotIn('password',prefs.path.read_text())
            if os.name != "nt":self.assertEqual(prefs.path.stat().st_mode & 0o777,0o600)

    def test_old_profile_without_optional_details(self):
        p=Profile(id='old',name='Old profile',host='c64.local').validate()
        self.assertEqual((p.serial_number,p.case_edition,p.notes),('','',''))

    def test_bad_config_kept(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'config.json';path.write_text('{broken')
            with self.assertRaises(BrowserError):Preferences(path).load()
            self.assertEqual(path.read_text(),'{broken')

    def test_bad_ports(self):
        for port in [0,65536,'80',True]:
            with self.assertRaises(BrowserError):UltimateClient('test',http_port=port)

    def test_dns_pointer_loop(self):
        with self.assertRaises(ValueError):dns_name(b'\xc0\x00',0)
        with self.assertRaises(ValueError):dns_records(b'bad')

    def test_dns_address(self):
        data=struct.pack('!6H',0,0x8400,0,1,0,0)+b'\x03c64\x05local\0'+struct.pack('!HHIH',1,1,120,4)+socket.inet_aton('192.168.68.60')
        self.assertEqual(dns_records(data),[('c64.local','A','192.168.68.60')])

    def test_scan_scope(self):
        with patch('c64u_browser.discovery.local_networks',return_value=['192.168.68.0/22']):
            for cidr in ['0.0.0.0/0','192.168.0.0/16','10.0.0.0/24','8.8.8.0/24']:
                with self.assertRaises(ValueError):subnet_scan(cidr)

class SubnetSelectionTests(unittest.TestCase):
    def test_device_lan_wins_over_virtual_network(self):
        from c64u_browser.discovery import preferred_subnet
        networks=['192.168.122.0/24','192.168.68.0/22']
        self.assertEqual(preferred_subnet(networks,['192.168.68.60']),'192.168.68.0/22')
        self.assertEqual(preferred_subnet(networks,['c64.local','192.168.68.60']),'192.168.68.0/22')
        self.assertEqual(preferred_subnet(networks), '')
        self.assertEqual(preferred_subnet(networks[:1]), '192.168.122.0/24')


class IdentTests(unittest.TestCase):
    def test_short_nonce_and_reply(self):
        from c64u_browser.discovery import ident_scan
        sock=Mock(); sock.__enter__=Mock(return_value=sock);sock.__exit__=Mock(return_value=False)
        def receive(_):
            nonce=sock.sendto.call_args_list[0].args[0].decode()[4:]
            self.assertLessEqual(len(nonce),24)
            return json.dumps({'product':'C64 Ultimate (V1.49) 1.1.0s2','firmware_version':'1.1.0s2','hostname':'C64','your_string':nonce}).encode(),('192.168.68.60',64)
        sock.recvfrom.side_effect=receive
        with patch('c64u_browser.discovery.socket.socket',return_value=sock), patch('c64u_browser.discovery.local_networks',return_value=['192.168.68.0/22']), patch('c64u_browser.discovery.time.monotonic',side_effect=[0,0,0,0,1,1,1,2,2,2,3]):
            results=ident_scan()
        self.assertIn(('192.168.68.60',80),results)
        self.assertEqual(sock.sendto.call_count,6)
        self.assertEqual({c.args[1] for c in sock.sendto.call_args_list},{('192.168.71.255',64),('255.255.255.255',64)})

if __name__=='__main__':unittest.main()
