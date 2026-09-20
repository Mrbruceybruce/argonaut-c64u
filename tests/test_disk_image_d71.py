import hashlib
from pathlib import Path
import unittest

from c64u_browser.disk_image import (
    D71Image, DiskImageError, sectors_on_d71_track)


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1571-authentic.d71'


class D71ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = FIXTURE.read_bytes()

    def test_reads_authentic_flat_1571_directory(self):
        image = D71Image(self.data)
        directory = image.directory()
        self.assertEqual((directory.disk_name, directory.disk_id, directory.dos_type),
                         ('ARGONAUT', '71', '2A'))
        self.assertEqual(directory.raw_disk_name[:8], b'ARGONAUT')
        self.assertEqual(directory.blocks_free, 657)
        self.assertEqual(
            [(entry.name, entry.file_type, entry.blocks) for entry in directory.entries],
            [('HELLO', 'PRG', 1), ('CROSSSIDE', 'PRG', 670)])
        self.assertEqual((directory.geometry.tracks, directory.geometry.sectors),
                         (70, 1366))

    def test_extracts_file_chain_across_both_physical_sides(self):
        image = D71Image(self.data)
        hello, crossside = image.directory().entries
        self.assertEqual(image.read_file(hello),
                         b'\x01\x08\x0b\x08\x00\x00\x9e2061\x00\x00\x00')
        expected = bytes((index * 29 + 7) % 256 for index in range(170000))
        self.assertEqual(image.read_file(crossside), expected)
        sectors = image._file_chain(crossside)[1]
        self.assertTrue(any(track > 35 for track, _ in sectors))

    def test_vice_fixture_passes_both_bams_and_preserves_source(self):
        before = hashlib.sha256(self.data).digest()
        image = D71Image(self.data)
        validation = image.validate()
        self.assertTrue(validation.standard_compatible)
        self.assertEqual(validation.entries_checked, 2)
        self.assertEqual(validation.issues, ())
        self.assertEqual(hashlib.sha256(image.source_bytes).digest(), before)

    def test_recognizes_error_table(self):
        image = D71Image(self.data + bytes((1,)) * 1366)
        self.assertTrue(image.geometry.error_table)
        self.assertTrue(image.validate().standard_compatible)

    def test_reports_second_side_bam_and_double_sided_flag_damage(self):
        damaged = bytearray(self.data)
        header = sum(sectors_on_d71_track(track) for track in range(1, 18)) * 256
        damaged[header + 3] = 0
        damaged[header + 0xdd] -= 1
        issues = D71Image(damaged).validate().issues
        self.assertIn('format.double_sided_flag', issues)
        self.assertIn('bam.track.36.free_count', issues)

    def test_reads_fixed_1571_directory_when_header_pointer_is_wrong(self):
        damaged = bytearray(self.data)
        header = sum(sectors_on_d71_track(track) for track in range(1, 18)) * 256
        damaged[header:header + 2] = bytes((1, 0))
        image = D71Image(damaged)
        self.assertEqual(image.directory().entries[0].name, 'HELLO')
        self.assertIn('format.directory_pointer', image.validate().issues)

    def test_rejects_unknown_size_and_invalid_second_side_sector(self):
        with self.assertRaisesRegex(DiskImageError, 'Unsupported D71 size'):
            D71Image(self.data[:-1])
        image = D71Image(self.data)
        with self.assertRaisesRegex(DiskImageError, 'outside track 70'):
            image.sector(70, 17)

    def test_1571_track_geometry_mirrors_both_sides(self):
        self.assertEqual(
            [sectors_on_d71_track(track) for track in
             (1, 17, 18, 24, 25, 30, 31, 35, 36, 52, 53, 59, 60, 65, 66, 70)],
            [21, 21, 19, 19, 18, 18, 17, 17,
             21, 21, 19, 19, 18, 18, 17, 17])


if __name__ == '__main__':
    unittest.main()
