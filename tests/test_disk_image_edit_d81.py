from pathlib import Path
import tempfile
import unittest

from c64u_browser.api import BrowserError
from c64u_browser.disk_image import D81Image, DiskImageError
from c64u_browser.disk_image_edit import D81EditSession
from c64u_browser.disk_image_io import save_edited_copy


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1581-authentic.d81'


class D81EditTests(unittest.TestCase):
    def setUp(self):
        self.original = FIXTURE.read_bytes()
        self.session = D81EditSession(D81Image(self.original))

    def test_rename_preserves_cbm_partition_allocation(self):
        hello = self.session.image.directory().entries[0]
        partition_before = self.session.image._partition_sectors(
            self.session.image.directory().entries[2])
        self.session.rename(hello, 'new hello')
        directory = self.session.image.directory()
        self.assertEqual(directory.entries[0].name, 'NEW HELLO')
        self.assertEqual(
            self.session.image._partition_sectors(directory.entries[2]),
            partition_before)
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_remove_cross_bam_file_preserves_partition(self):
        directory = self.session.image.directory()
        crossside = directory.entries[1]
        self.session.remove(crossside)
        changed = self.session.image.directory()
        self.assertEqual([entry.name for entry in changed.entries],
                         ['HELLO', 'SMALLPART'])
        self.assertEqual(changed.blocks_free, directory.blocks_free + 1615)
        partition = changed.entries[1]
        self.assertTrue(all(not self.session.image._bam_is_free(*location)
                            for location in self.session.image._partition_sectors(partition)))
        self.assertTrue(self.session.image.validate().standard_compatible)
        self.assertEqual(FIXTURE.read_bytes(), self.original)

    def test_refuses_to_remove_cbm_partition(self):
        partition = self.session.image.directory().entries[2]
        self.assertFalse(self.session.can_remove(partition))
        with self.assertRaisesRegex(DiskImageError, 'cannot be removed safely'):
            self.session.remove(partition)

    def test_adds_file_across_both_bam_halves(self):
        crossside = self.session.image.directory().entries[1]
        self.session.remove(crossside)
        payload = bytes((index * 37 + 5) % 256 for index in range(410000))
        self.session.add_file(payload, 'NEW CROSS81', 'PRG')
        added = next(entry for entry in self.session.image.directory().entries
                     if entry.name == 'NEW CROSS81')
        locations = self.session.image._file_chain(added)[1]
        self.assertEqual((added.name, added.blocks), ('NEW CROSS81', 1615))
        self.assertEqual(self.session.image.read_file(added), payload)
        self.assertTrue(any(track < 40 for track, _ in locations))
        self.assertTrue(any(track > 40 for track, _ in locations))
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_extends_root_directory_only_on_track_40(self):
        for index in range(6):
            self.session.add_file(bytes((index,)), f'FILE {index}', 'USR')
        directory = self.session.image.directory()
        self.assertEqual(len(directory.entries), 9)
        self.assertEqual((directory.entries[-1].directory_track,
                          directory.entries[-1].directory_sector), (40, 4))
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_saves_validated_d81_copy_without_replacement(self):
        self.session.rename(self.session.image.directory().entries[0], 'RENAMED')
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'edited.d81'
            result = save_edited_copy(self.session, destination)
            self.assertEqual(result['bytes'], len(self.original))
            saved = D81Image.from_path(destination)
            self.assertEqual(saved.directory().entries[0].name, 'RENAMED')
            self.assertTrue(saved.validate().standard_compatible)
            with self.assertRaisesRegex(BrowserError, 'already exists'):
                save_edited_copy(self.session, destination)
            with self.assertRaisesRegex(BrowserError, r'\.d81'):
                save_edited_copy(self.session, Path(folder) / 'edited.d71')

    def test_preserves_error_table_and_marks_bam_sectors_good(self):
        data = self.original + bytes((5,)) * 3200
        session = D81EditSession(D81Image(data))
        session.remove(session.image.directory().entries[1])
        edited = session.validated_bytes()
        self.assertEqual(len(edited), 822400)
        first_bam = session._sector_number(40, 1)
        second_bam = session._sector_number(40, 2)
        self.assertEqual(edited[819200 + first_bam], 1)
        self.assertEqual(edited[819200 + second_bam], 1)


if __name__ == '__main__':
    unittest.main()
