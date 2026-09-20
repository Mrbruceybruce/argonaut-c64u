import hashlib
from pathlib import Path
import unittest

from c64u_browser.disk_image import D81Image, DiskImageError


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1581-authentic.d81'


class D81ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = FIXTURE.read_bytes()

    def test_reads_authentic_flat_1581_root_directory(self):
        image = D81Image(self.data)
        directory = image.directory()
        self.assertEqual((directory.disk_name, directory.disk_id,
                          directory.dos_type, directory.dos_version),
                         ('ARGONAUT', '81', '3D', 'D'))
        self.assertEqual(directory.raw_disk_name[:8], b'ARGONAUT')
        self.assertEqual(directory.blocks_free, 1534)
        self.assertEqual(
            [(entry.name, entry.file_type, entry.blocks)
             for entry in directory.entries],
            [('HELLO', 'PRG', 1), ('CROSS81', 'PRG', 1615),
             ('SMALLPART', 'CBM', 10)])
        self.assertEqual(directory.entries[2].partition_kind, 'protected')
        self.assertEqual((directory.geometry.tracks, directory.geometry.sectors),
                         (80, 3200))

    def test_extracts_file_chain_across_both_bam_halves(self):
        image = D81Image(self.data)
        hello, crossside = image.directory().entries[:2]
        self.assertEqual(image.read_file(hello),
                         b'\x01\x08\x0b\x08\x00\x00\x9e2061\x00\x00\x00')
        expected = bytes((index * 31 + 9) % 256 for index in range(410000))
        self.assertEqual(image.read_file(crossside), expected)
        sectors = image._file_chain(crossside)[1]
        self.assertTrue(any(track < 40 for track, _ in sectors))
        self.assertTrue(any(track > 40 for track, _ in sectors))

    def test_vice_fixture_passes_both_bams_and_preserves_source(self):
        before = hashlib.sha256(self.data).digest()
        image = D81Image(self.data)
        validation = image.validate()
        self.assertTrue(validation.standard_compatible)
        self.assertEqual(validation.entries_checked, 2)
        self.assertEqual(validation.issues, ())
        self.assertEqual(hashlib.sha256(image.source_bytes).digest(), before)

    def test_cbm_partition_is_contiguous_allocated_and_not_extractable(self):
        image = D81Image(self.data)
        partition = image.directory().entries[2]
        sectors = image._partition_sectors(partition)
        self.assertEqual(sectors, tuple((80, sector) for sector in range(10)))
        self.assertTrue(all(not image._bam_is_free(*location)
                            for location in sectors))
        with self.assertRaisesRegex(DiskImageError, 'partition, not a chained file'):
            image.read_file(partition)

    def test_recognizes_error_table(self):
        image = D81Image(self.data + bytes((1,)) * 3200)
        self.assertTrue(image.geometry.error_table)
        self.assertTrue(image.validate().standard_compatible)

    def test_reports_second_bam_and_header_pointer_damage(self):
        damaged = bytearray(self.data)
        header = (40 - 1) * 40 * 256
        second_bam = header + 2 * 256
        damaged[header:header + 2] = bytes((1, 0))
        damaged[second_bam + 0x10] += 1
        issues = D81Image(damaged).validate().issues
        self.assertIn('format.directory_pointer', issues)
        self.assertIn('bam.track.41.free_count', issues)

    def test_reads_fixed_root_directory_when_header_pointer_is_wrong(self):
        damaged = bytearray(self.data)
        header = (40 - 1) * 40 * 256
        damaged[header:header + 2] = bytes((1, 0))
        image = D81Image(damaged)
        self.assertEqual(image.directory().entries[0].name, 'HELLO')
        self.assertIn('format.directory_pointer', image.validate().issues)

    def test_rejects_unknown_size_and_invalid_sector(self):
        with self.assertRaisesRegex(DiskImageError, 'Unsupported D81 size'):
            D81Image(self.data[:-1])
        image = D81Image(self.data)
        with self.assertRaisesRegex(DiskImageError, 'outside track 80'):
            image.sector(80, 40)


if __name__ == '__main__':
    unittest.main()
