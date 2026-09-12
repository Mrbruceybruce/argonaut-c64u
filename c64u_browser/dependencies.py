# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Menu dependencies confirmed on the user's Spiffy C64U."""
LED_MODES={
 'LedStrip Pattern':{'Rainbow','Rainbow Sparkle','SID Music'},
 'Strip Intensity':{'Default','Fixed Color','Rainbow','Rainbow Sparkle','SID Music','Sparkle'},
 'Fixed Color':{'Fixed Color','Sparkle'},
 'Color tint':{'Fixed Color','Rainbow','Rainbow Sparkle','SID Music','Sparkle'},
}
NETWORK_CATEGORIES={'Ethernet Settings','WiFi settings'}
STATIC_FIELDS={'Static IP','Static Netmask','Static Gateway','Static DNS'}

def controls_dependencies(category,name):
 return (category=='LED Strip Settings' and name=='LedStrip Mode') or (category in NETWORK_CATEGORIES and name=='Use DHCP')

def inactive_reason(category,name):
 if category in NETWORK_CATEGORIES and name in STATIC_FIELDS:
  return 'Read-only while DHCP is enabled. Disable DHCP to edit these saved static settings.'
 return 'Inactive in the selected LED mode.'

def enabled(category,name,settings,pending):
 if category in NETWORK_CATEGORIES and name in STATIC_FIELDS:
  dhcp=pending.get((category,'Use DHCP'))
  if dhcp is None:dhcp=next((s.current for s in settings.get(category,[]) if s.name=='Use DHCP'),None)
  return dhcp=='Disabled'
 if category!='LED Strip Settings' or name not in LED_MODES:return True
 mode=pending.get((category,'LedStrip Mode'))
 if mode is None:mode=next((s.current for s in settings.get(category,[]) if s.name=='LedStrip Mode'),None)
 return mode in LED_MODES[name]
