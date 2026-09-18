from pathlib import Path
import tempfile
import unittest

from c64u_browser.api import BrowserError
from c64u_browser.disk_image import D64Image, DiskImageError
from c64u_browser.disk_image_edit import D64EditSession, encode_petscii_name
from c64u_browser.disk_image_io import save_edited_copy


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'


class D64EditTests(unittest.TestCase):
    def setUp(self):
        self.original = FIXTURE.read_bytes()
        self.session = D64EditSession(D64Image(self.original))

    def test_rename_is_staged_and_preserves_original(self):
        hello = self.session.image.directory().entries[0]
        self.session.rename(hello, 'new hello')
        self.assertEqual(self.session.image.directory().entries[0].name, 'NEW HELLO')
        self.assertEqual(D64Image(self.original).directory().entries[0].name, 'HELLO')
        self.assertEqual(self.session.changes[0].operation, 'rename')
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_remove_releases_file_blocks_and_discard_restores_stage(self):
        directory = self.session.image.directory()
        self.session.remove(directory.entries[0])
        changed = self.session.image.directory()
        self.assertEqual([entry.name for entry in changed.entries], ['BIGFILE'])
        self.assertEqual(changed.blocks_free, directory.blocks_free + 1)
        self.assertTrue(self.session.image.validate().standard_compatible)
        self.session.discard()
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.session.image.source_bytes, self.original)

    def test_adds_multisector_file_with_authentic_chain_and_bam(self):
        payload = bytes((index * 13) % 256 for index in range(700))
        before = self.session.image.directory().blocks_free
        self.session.add_file(payload, 'UPLOAD', 'SEQ')
        directory = self.session.image.directory()
        added = directory.entries[-1]
        self.assertEqual((added.name, added.file_type, added.blocks), ('UPLOAD', 'SEQ', 3))
        self.assertEqual(directory.blocks_free, before - 3)
        self.assertEqual(self.session.image.read_file(added), payload)
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_extends_the_real_directory_chain_after_eight_entries(self):
        for index in range(7):
            self.session.add_file(bytes((index,)), f'FILE {index}', 'PRG')
        directory = self.session.image.directory()
        self.assertEqual(len(directory.entries), 9)
        self.assertEqual(directory.entries[-1].directory_sector, 2)
        self.assertTrue(self.session.image.validate().standard_compatible)

    def test_rejects_unsafe_names_duplicates_and_unsupported_types(self):
        for name in ('', 'x' * 17, 'bad/name', 'snowman \u2603'):
            with self.subTest(name=name), self.assertRaises(DiskImageError):
                encode_petscii_name(name)
        with self.assertRaisesRegex(DiskImageError, 'already in use'):
            self.session.add_file(b'x', 'hello')
        with self.assertRaisesRegex(DiskImageError, 'already has'):
            self.session.rename(self.session.image.directory().entries[0], 'hello')
        with self.assertRaisesRegex(DiskImageError, 'PRG, SEQ, or USR'):
            self.session.add_file(b'x', 'new', 'REL')

    def test_saves_validated_new_copy_without_replacing_any_file(self):
        self.session.add_file(b'payload', 'NEW FILE', 'USR')
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'edited.d64'
            result = save_edited_copy(self.session, destination)
            self.assertEqual((result['bytes'], result['changes']), (len(self.original), 1))
            self.assertFalse(self.session.has_unsaved_changes)
            saved = D64Image.from_path(destination)
            self.assertTrue(saved.validate().standard_compatible)
            self.assertEqual(saved.read_file(saved.directory().entries[-1]), b'payload')
            destination.write_bytes(b'keep')
            with self.assertRaisesRegex(BrowserError, 'already exists'):
                save_edited_copy(self.session, destination)
            self.assertEqual(destination.read_bytes(), b'keep')
            self.assertEqual(FIXTURE.read_bytes(), self.original)

    def test_preserves_error_table_and_marks_changed_sectors_good(self):
        data = self.original + bytes((5,)) * 683
        session = D64EditSession(D64Image(data))
        session.add_file(b'payload', 'NEW FILE', 'PRG')
        edited = session.validated_bytes()
        self.assertEqual(len(edited), 175531)
        image = session.image
        added = image.directory().entries[-1]
        bam_number = session._sector_number(18, 0)
        file_number = session._sector_number(added.start_track, added.start_sector)
        self.assertEqual(edited[174848 + bam_number], 1)
        self.assertEqual(edited[174848 + file_number], 1)
        self.assertEqual(edited[174848 + 500], 5)


if __name__ == '__main__':
    unittest.main()
