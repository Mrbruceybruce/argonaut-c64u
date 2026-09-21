# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from c64u_browser.sid_format import SidFormatError, parse_sid


def sid_bytes(*, magic='PSID', version=2, title='TUNE', author='AUTHOR',
              released='2026', declared_load=0, effective_load=0x1000,
              init=0x1000, play=0x1003, songs=1, start=1, speed=0,
              flags=0, relocation_start=0, relocation_pages=0,
              second=0, third=0, payload=b'\xea' * 32):
    offset = 0x76 if version == 1 else 0x7c
    header = bytearray(offset)
    header[:4] = magic.encode('ascii')
    header[4:6] = version.to_bytes(2, 'big')
    header[6:8] = offset.to_bytes(2, 'big')
    header[8:10] = declared_load.to_bytes(2, 'big')
    header[10:12] = init.to_bytes(2, 'big')
    header[12:14] = play.to_bytes(2, 'big')
    header[14:16] = songs.to_bytes(2, 'big')
    header[16:18] = start.to_bytes(2, 'big')
    header[18:22] = speed.to_bytes(4, 'big')
    for position, text in ((0x16, title), (0x36, author), (0x56, released)):
        value = text.encode('cp1252')[:32]
        header[position:position + len(value)] = value
    if version >= 2:
        header[0x76:0x78] = flags.to_bytes(2, 'big')
        header[0x78] = relocation_start
        header[0x79] = relocation_pages
        header[0x7a] = second
        header[0x7b] = third
    prefix = effective_load.to_bytes(2, 'little') if declared_load == 0 else b''
    return bytes(header) + prefix + payload


class SidFormatTests(unittest.TestCase):
    def test_psid_versions_one_through_four(self):
        for version in range(1, 5):
            with self.subTest(version=version):
                metadata = parse_sid(sid_bytes(version=version))
                self.assertEqual(('PSID', version, 0x1000, 32),
                                 (metadata.format, metadata.version,
                                  metadata.effective_load_address,
                                  metadata.payload_size))
                self.assertEqual(64, len(metadata.sha256))

    def test_rsid_versions_two_through_four(self):
        for version in range(2, 5):
            with self.subTest(version=version):
                metadata = parse_sid(sid_bytes(
                    magic='RSID', version=version, declared_load=0,
                    effective_load=0x0801, init=0x0801, play=0, speed=0))
                self.assertEqual('RSID', metadata.format)
                self.assertIn('real-c64-environment', metadata.compatibility_flags)
                self.assertEqual('warning', metadata.playback_classification)

    def test_embedded_and_explicit_load_addresses(self):
        embedded = parse_sid(sid_bytes(declared_load=0, effective_load=0x2000))
        explicit = parse_sid(sid_bytes(declared_load=0x3000))
        self.assertEqual((0, 0x2000), (embedded.declared_load_address,
                                      embedded.effective_load_address))
        self.assertEqual((0x3000, 0x3000), (explicit.declared_load_address,
                                           explicit.effective_load_address))

    def test_song_bounds_and_speed_interpretation(self):
        metadata = parse_sid(sid_bytes(songs=34, start=34, speed=(1 | (1 << 31))))
        self.assertEqual('cia-1', metadata.song_speeds[0])
        self.assertEqual('vbi', metadata.song_speeds[1])
        self.assertEqual('cia-1', metadata.song_speeds[32])
        for songs, start in ((0, 1), (257, 1), (2, 0), (2, 3)):
            with self.subTest(songs=songs, start=start):
                with self.assertRaises(SidFormatError):
                    parse_sid(sid_bytes(songs=songs, start=start))

    def test_windows_1252_metadata(self):
        metadata = parse_sid(sid_bytes(title='Café', author='Åke',
                                       released='© 2026'))
        self.assertEqual(('Café', 'Åke', '© 2026'),
                         (metadata.title, metadata.author, metadata.released))

    def test_clock_models_and_multisid_addresses(self):
        # PAL, primary 6581, second 8580, third either.
        flags = (1 << 2) | (1 << 4) | (2 << 6) | (3 << 8)
        metadata = parse_sid(sid_bytes(
            version=4, flags=flags, second=0x42, third=0xe0))
        self.assertEqual('PAL', metadata.clock)
        self.assertEqual(3, metadata.sid_count)
        self.assertEqual((0xd400, 0xd420, 0xde00),
                         tuple(chip.address for chip in metadata.chips))
        self.assertEqual(('MOS6581', 'MOS8580', 'MOS6581-or-MOS8580'),
                         tuple(chip.model for chip in metadata.chips))

    def test_single_and_two_sid_metadata(self):
        self.assertEqual(1, parse_sid(sid_bytes(version=4)).sid_count)
        two = parse_sid(sid_bytes(version=3, second=0x44))
        self.assertEqual((2, 0xd440, None),
                         (two.sid_count, two.second_sid_address,
                          two.third_sid_address))

    def test_mus_playsid_and_rsid_basic_classification(self):
        mus = parse_sid(sid_bytes(flags=1))
        playsid = parse_sid(sid_bytes(flags=2))
        basic = parse_sid(sid_bytes(
            magic='RSID', flags=2, effective_load=0x0801,
            init=0, play=0, speed=0))
        self.assertEqual(('blocked', False, True),
                         (mus.playback_classification,
                          mus.playback_eligible, mus.mus))
        self.assertTrue(playsid.playsid_specific)
        self.assertFalse(playsid.playback_eligible)
        self.assertTrue(basic.rsid_basic)
        self.assertTrue(basic.playback_eligible)

    def test_relocation_constraints(self):
        valid = parse_sid(sid_bytes(relocation_start=0x20,
                                    relocation_pages=2))
        self.assertEqual((0x20, 2), (valid.relocation_start_page,
                                    valid.relocation_pages))
        for kwargs in (
                {'relocation_start': 0, 'relocation_pages': 1},
                {'relocation_start': 0xff, 'relocation_pages': 1},
                {'relocation_start': 0x10, 'relocation_pages': 0},
                {'relocation_start': 0x10, 'relocation_pages': 1,
                 'effective_load': 0x1000}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SidFormatError):
                parse_sid(sid_bytes(**kwargs))

    def test_malformed_truncated_overflow_and_rsid_rules(self):
        cases = [
            b'', b'NOPE' + b'\0' * 200,
            sid_bytes()[:0x70],
            sid_bytes(effective_load=0xfff0, payload=b'x' * 32),
            sid_bytes(magic='RSID', effective_load=0x0801,
                      declared_load=0x0801, play=0, speed=0),
            sid_bytes(magic='RSID', effective_load=0x0700,
                      init=0x0801, play=0, speed=0),
            sid_bytes(magic='RSID', effective_load=0x0801,
                      init=0x0801, play=1, speed=0),
            sid_bytes(magic='RSID', effective_load=0x0801,
                      init=0x0900, play=0, speed=0, payload=b'x' * 32),
            sid_bytes(version=3, second=0x42, third=0x44),
            sid_bytes(version=4, second=0x42, third=0x42),
        ]
        for data in cases:
            with self.subTest(length=len(data)), self.assertRaises(SidFormatError):
                parse_sid(data)


if __name__ == '__main__':unittest.main()
