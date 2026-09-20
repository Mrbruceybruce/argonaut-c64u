from pathlib import Path
import tempfile
import unittest

from c64u_browser.api import BrowserError
from c64u_browser.disk_image import D71Image
from c64u_browser.disk_image_edit import D71EditSession
from c64u_browser.disk_image_io import save_edited_copy


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1571-authentic.d71'


class D71EditTests(unittest.TestCase):
    def setUp(self):
        self.original = FIXTURE.read_bytes()
        self.session = D71EditSession(D71Image(self.original))

    def test_rename_is_staged_in_the_flat_1571_directory(self):
        hello = self.session.image.directory().entries[0]
        self.session.rename(hello, 'new hello')
        self.assertEqual(self.session.image.directory().entries[0].name, 'NEW HELLO')
        self.assertEqual(D71Image(self.original).directory().entries[0].name, 'HELLO')
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_remove_releases_cross_side_file_blocks(self):
        directory = self.session.image.directory()
        crossside = directory.entries[1]
        self.assertTrue(any(track > 35 for track, _ in
                            self.session.image._file_chain(crossside)[1]))
        self.session.remove(crossside)
        changed = self.session.image.directory()
        self.assertEqual([entry.name for entry in changed.entries], ['HELLO'])
        self.assertEqual(changed.blocks_free, directory.blocks_free + 670)
        self.assertTrue(self.session.image.validate().standard_compatible)
        self.assertEqual(FIXTURE.read_bytes(), self.original)

    def test_adds_and_reads_a_new_file_across_both_sides(self):
        crossside = self.session.image.directory().entries[1]
        self.session.remove(crossside)
        payload = bytes((index * 31 + 9) % 256 for index in range(170000))
        self.session.add_file(payload, 'NEW CROSSSIDE', 'PRG')
        added = self.session.image.directory().entries[-1]
        self.assertEqual((added.name, added.blocks), ('NEW CROSSSIDE', 670))
        self.assertEqual(self.session.image.read_file(added), payload)
        self.assertTrue(any(track > 35 for track, _ in
                            self.session.image._file_chain(added)[1]))
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_saves_validated_d71_copy_without_replacement(self):
        self.session.rename(self.session.image.directory().entries[0], 'RENAMED')
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'edited.d71'
            result = save_edited_copy(self.session, destination)
            self.assertEqual(result['bytes'], len(self.original))
            saved = D71Image.from_path(destination)
            self.assertEqual(saved.directory().entries[0].name, 'RENAMED')
            self.assertTrue(saved.validate().standard_compatible)
            with self.assertRaisesRegex(BrowserError, 'already exists'):
                save_edited_copy(self.session, destination)
            with self.assertRaisesRegex(BrowserError, r'\.d71'):
                save_edited_copy(self.session, Path(folder) / 'edited.d64')

    def test_preserves_error_table_and_marks_both_bams_good(self):
        data = self.original + bytes((5,)) * 1366
        session = D71EditSession(D71Image(data))
        session.remove(session.image.directory().entries[1])
        edited = session.validated_bytes()
        self.assertEqual(len(edited), 351062)
        first_bam = session._sector_number(18, 0)
        second_bam = session._sector_number(53, 0)
        self.assertEqual(edited[349696 + first_bam], 1)
        self.assertEqual(edited[349696 + second_bam], 1)


if __name__ == '__main__':
    unittest.main()
