# SPDX-License-Identifier: GPL-3.0-or-later
"""Allowlisted stream reports: never serialize clients, settings or exceptions."""
import ipaddress

COUNTERS = {
    'frames': 'Complete frames received',
    'video_packets': 'Video packets received',
    'audio_packets': 'Audio packets received',
    'invalid_video': 'Invalid video packets',
    'incomplete_video': 'Incomplete video frames',
    'invalid_audio': 'Invalid audio packets',
    'missing_audio': 'Estimated audio sequence gaps',
    'audio_resets': 'Possible audio sequence resets',
    'audio_evictions': 'Receiver audio queue drops',
    'video_superseded': 'Receiver frames superseded',
    'display_superseded': 'Display frames superseded',
    'displayed': 'Frames presented to the main preview',
    'recorded': 'Frames submitted to recording',
    'monitor_drops': 'Audio monitor input drops',
}

def advice(stats):
    if stats.get('running') is False:
        return 'Preview is stopped. Counters are from the last session; start preview explicitly for live measurements.'
    if not stats:
        return 'Start preview explicitly to measure incoming media. Opening diagnostics does not start streams.'
    if not stats.get('video_packets', 0):
        return ('No video packets received. Use the C64U wired Ethernet address. The destination '
                'must be this computer, not the C64U. Incoming UDP 11000–11001 may be blocked '
                'by a firewall, a VM network, or another application using these ports.')
    if not stats.get('frames', 0):
        return 'Video packets arrived, but no complete picture could be decoded. Check packet loss and firmware compatibility.'
    if (stats.get('video_age') or 0) > 2:
        return 'Video has stopped arriving. Check the Ethernet cable and whether another client changed the stream destination.'
    if stats.get('with_audio') and not stats.get('audio_packets', 0):
        return 'Video is arriving, but audio is not. Check incoming UDP 11001. Stop and restart preview with audio enabled.'
    return 'Media is arriving. Received FPS is not necessarily displayed or recorded FPS; sequence gaps are estimates, not confirmed network loss.'

def report(stats, include_addresses=False):
    lines = ['Argonaut stream diagnostics', 'Passwords, keys, device identifiers and file paths are excluded.']
    lines.append('Connection in Argonaut: '+('Connected' if stats.get('connected') is True else 'Disconnected'))
    lines.append('Preview: '+('Running' if stats.get('running') is True else 'Stopped'))
    for key in ('peer', 'address'):
        value = 'Hidden'
        if include_addresses:
            try: value = str(ipaddress.ip_address(stats.get(key, '')))
            except ValueError: value = 'Unavailable'
        lines.append(('C64U address' if key == 'peer' else 'Computer destination') + ': ' + value)
    lines.append('UDP listeners: video 11000; audio 11001 when enabled')
    for key, label in COUNTERS.items():
        value = stats.get(key)
        lines.append(f'{label}: {value if type(value) is int and value >= 0 else "Unavailable"}')
    for key, label in [('video_age','Seconds since complete video'),('audio_age','Seconds since audio')]:
        value=stats.get(key)
        lines.append(f'{label}: {round(value, 2) if type(value) in (int,float) and 0 <= value < 1e9 else "Unavailable"}')
    state=stats.get('recording_state')
    lines.append('Recording: '+(state if state in ('idle','starting','recording','finishing','saved','failed') else 'Unavailable'))
    lines.append('Video packet loss: unavailable (incomplete frames are counted separately)')
    lines.append(advice(stats))
    return '\n'.join(lines)
