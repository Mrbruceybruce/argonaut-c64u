from unittest import TestCase
from unittest.mock import Mock
from c64u_browser.configuration import Configuration,WIRED_STATUS_FIELDS
from c64u_browser.settings_sections import subsection_for
from c64u_browser.backups import snapshot,differences
class WiredStatusTests(TestCase):
    def test_missing_status_is_not_added(self):
        client=Mock();client.read_configuration.return_value={'Ethernet Settings':{'Static IP':{'current':'192.168.2.64'}}}
        rows=Configuration(client).settings('Ethernet Settings')
        self.assertEqual([row.name for row in rows],['Static IP'])
    def test_network_status_hidden_in_sections_search_and_favorites(self):
        from c64u_browser.configuration import Setting
        from c64u_browser.settings_sections import section_entries,visible_entries
        for category in ('Ethernet Settings','WiFi settings'):
            settings={category:[Setting(name,'example','',editable=False) for name in WIRED_STATUS_FIELDS]}
            self.assertEqual(section_entries(settings),{})
            self.assertEqual(visible_entries(settings,None,'example'),[])
            self.assertEqual(visible_entries(settings,None,favorites={(category,name) for name in WIRED_STATUS_FIELDS}),[])
    def test_device_supplied_values_are_read_only_and_not_duplicated(self):
        values={'Status':'Link Up','Active IP address':'192.168.68.66','Interface MAC':'02:15:41:7f:01:c9'}
        client=Mock();client.read_configuration.return_value={'Ethernet Settings':{k:{'current':v} for k,v in values.items()}}
        rows=Configuration(client).settings('Ethernet Settings')
        self.assertEqual(len(rows),3)
        self.assertEqual({r.name:r.current for r in rows},values)
        self.assertTrue(all(not r.editable for r in rows))
        model={'Ethernet Settings':rows}
        self.assertEqual(snapshot(model,'test')['settings'],{})
        self.assertEqual(differences({'settings':{'Ethernet Settings':values}},model),([],3))
    def test_other_categories_do_not_gain_wired_fields(self):
        client=Mock();client.read_configuration.return_value={'WiFi settings':{'Use DHCP':{'current':'Enabled'}}}
        self.assertEqual(len(Configuration(client).settings('WiFi settings')),1)
