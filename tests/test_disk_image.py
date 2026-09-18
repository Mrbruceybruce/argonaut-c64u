import hashlib
from pathlib import Path
import unittest

from c64u_browser.disk_image import D64Image, DiskImageError, sectors_on_track


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'


class D64ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = FIXTURE.read_bytes()

    def test_reads_flat_directory_created_by_vice_c1541(self):
        image = D64Image(self.data)
        directory = image.directory()
        self.assertEqual((directory.disk_name, directory.disk_id, directory.dos_type),
                         ('ARGONAUT', '64', '2A'))
        self.assertEqual(directory.raw_disk_name[:8], b'ARGONAUT')
        self.assertEqual(directory.blocks_free, 660)
        self.assertEqual(len(directory.entries), 2)
        entry = directory.entries[0]
        self.assertEqual((entry.name, entry.file_type, entry.closed, entry.locked, entry.blocks),
                         ('HELLO', 'PRG', True, False, 1))
        self.assertEqual(entry.raw_name[:5], b'HELLO')
        self.assertTrue(directory.geometry.standard)
        self.assertEqual(directory.geometry.tracks, 35)

    def test_reads_single_and_multi_sector_files_exactly(self):
        image = D64Image(self.data)
        hello, bigfile = image.directory().entries
        self.assertEqual(image.read_file(hello),
                         b'\x01\x08\x0b\x08\x00\x00\x9e2061\x00\x00\x00')
        expected = bytes((index * 37 + 11) % 256 for index in range(600))
        self.assertEqual(bigfile.blocks, 3)
        self.assertEqual(image.read_file(bigfile), expected)

    def test_vice_fixture_passes_standard_structure_validation(self):
        validation = D64Image(self.data).validate()
        self.assertTrue(validation.standard_compatible)
        self.assertEqual(validation.entries_checked, 2)
        self.assertEqual(validation.issues, ())

    def test_parsing_does_not_change_any_source_byte(self):
        before = hashlib.sha256(self.data).digest()
        image = D64Image(self.data)
        image.directory()
        self.assertEqual(hashlib.sha256(image.source_bytes).digest(), before)
        self.assertEqual(image.source_bytes, self.data)

    def test_recognizes_error_table_without_treating_it_as_disk_sectors(self):
        image = D64Image(self.data + bytes([1]) * 683)
        self.assertTrue(image.geometry.error_table)
        self.assertEqual(image.directory().disk_name, 'ARGONAUT')

    def test_recognizes_extended_images_as_nonstandard(self):
        extended = self.data + bytes(196608 - len(self.data))
        image = D64Image(extended)
        self.assertEqual(image.geometry.tracks, 40)
        self.assertFalse(image.geometry.standard)
        self.assertEqual(image.directory().disk_name, 'ARGONAUT')
        self.assertEqual(image.validate().issues, ('geometry.extended_tracks',))

    def test_validation_reports_block_count_without_blocking_read(self):
        damaged = bytearray(self.data)
        directory = (sum(sectors_on_track(track) for track in range(1, 18)) + 1) * 256
        damaged[directory + 2 + 28:directory + 2 + 30] = bytes((2, 0))
        image = D64Image(damaged)
        self.assertEqual(image.read_file(image.directory().entries[0]),
                         b'\x01\x08\x0b\x08\x00\x00\x9e2061\x00\x00\x00')
        self.assertIn('entry.1.block_count', image.validate().issues)

    def test_rejects_unknown_size(self):
        with self.assertRaisesRegex(DiskImageError, 'Unsupported D64 size'):
            D64Image(self.data[:-1])

    def test_rejects_invalid_directory_pointer(self):
        damaged = bytearray(self.data)
        header = sum(sectors_on_track(track) for track in range(1, 18)) * 256
        damaged[header] = 17
        with self.assertRaisesRegex(DiskImageError, 'does not point'):
            D64Image(damaged).directory()

    def test_rejects_directory_loop(self):
        damaged = bytearray(self.data)
        directory = (sum(sectors_on_track(track) for track in range(1, 18)) + 1) * 256
        damaged[directory:directory + 2] = bytes((18, 1))
        with self.assertRaisesRegex(DiskImageError, 'loop'):
            D64Image(damaged).directory()

    def test_rejects_file_chain_loop(self):
        image = D64Image(self.data)
        entry = image.directory().entries[1]
        damaged = bytearray(self.data)
        offset = (sum(sectors_on_track(track) for track in range(1, entry.start_track))
                  + entry.start_sector) * 256
        damaged[offset:offset + 2] = bytes((entry.start_track, entry.start_sector))
        with self.assertRaisesRegex(DiskImageError, 'loop in its file chain'):
            D64Image(damaged).read_file(entry)

    def test_rejects_invalid_final_sector_length(self):
        image = D64Image(self.data)
        entry = image.directory().entries[0]
        damaged = bytearray(self.data)
        offset = (sum(sectors_on_track(track) for track in range(1, entry.start_track))
                  + entry.start_sector) * 256
        damaged[offset:offset + 2] = b'\x00\x00'
        with self.assertRaisesRegex(DiskImageError, 'final-sector length'):
            D64Image(damaged).read_file(entry)

    def test_track_geometry_matches_1541_zones(self):
        self.assertEqual([sectors_on_track(track) for track in (1, 17, 18, 24, 25, 30, 31, 35)],
                         [21, 21, 19, 19, 18, 18, 17, 17])


if __name__ == '__main__':
    unittest.main()
