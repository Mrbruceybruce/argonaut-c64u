from pathlib import Path
import tempfile
import unittest

from c64u_browser.api import BrowserError
from c64u_browser.disk_image import D64Image, DiskImageError, sectors_on_track
from c64u_browser.disk_image_edit import (
    D64EditSession, create_blank_d64_image, encode_disk_id,
    encode_petscii_name)
from c64u_browser.disk_image_io import save_edited_copy


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'
REL_FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-rel.d64'


class D64EditTests(unittest.TestCase):
    def setUp(self):
        self.original = FIXTURE.read_bytes()
        self.session = D64EditSession(D64Image(self.original))

    def test_rename_is_staged_and_preserves_original(self):
        hello = self.session.image.directory().entries[0]
        self.session.rename(hello, 'new hello')
        self.assertEqual(self.session.image.directory().entries[0].name, 'NEW HELLO')
        self.assertEqual(self.session.image.directory().entries[0].raw_name[:9], b'NEW HELLO')
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

    def test_remove_rel_releases_data_and_side_sectors(self):
        original = REL_FIXTURE.read_bytes()
        session = D64EditSession(D64Image(original))
        before = session.image.directory()
        self.assertEqual(before.blocks_free, 658)
        session.remove(before.entries[0])
        changed = session.image.directory()
        self.assertEqual((changed.entries, changed.blocks_free), ((), 664))
        self.assertTrue(session.image.validate().standard_compatible)
        self.assertEqual(REL_FIXTURE.read_bytes(), original)

    def test_remove_rel_rejects_damaged_side_sector_without_changes(self):
        damaged = bytearray(REL_FIXTURE.read_bytes())
        side = (sum(sectors_on_track(track) for track in range(1, 17)) + 10) * 256
        damaged[side + 3] = 41
        with self.assertRaisesRegex(DiskImageError, 'Repair the D64 structure'):
            D64EditSession(D64Image(damaged))

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
        self.assertEqual(encode_petscii_name('C64 TEST')[:8], b'C64 TEST')
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

    def test_creates_authentic_blank_d64_and_accepts_staged_files(self):
        image = create_blank_d64_image('MY DISK', 'A1')
        directory = image.directory()
        self.assertEqual(len(image.source_bytes), 174848)
        self.assertEqual((directory.disk_name, directory.disk_id, directory.dos_type),
                         ('MY DISK', 'A1', '2A'))
        self.assertEqual((directory.blocks_free, directory.entries), (664, ()))
        self.assertEqual(directory.raw_disk_name[:7], b'MY DISK')
        self.assertTrue(image.validate().standard_compatible)

        session = D64EditSession(image)
        self.assertFalse(session._is_free(18, 0))
        self.assertFalse(session._is_free(18, 1))
        self.assertTrue(session._is_free(18, 2))
        session.add_file(b'\x01\x08READY', 'HELLO', 'PRG')
        added = session.image.directory().entries[0]
        self.assertEqual(session.image.read_file(added), b'\x01\x08READY')
        self.assertEqual(session.image.directory().blocks_free, 663)
        self.assertTrue(session.image.validate().standard_compatible)

    def test_blank_d64_rejects_invalid_label_and_id(self):
        for name, disk_id in (('', '64'), ('x' * 17, '64'), ('bad/name', '64'),
                              ('GOOD', ''), ('GOOD', '1'), ('GOOD', '123'),
                              ('GOOD', '\u2603!')):
            with self.subTest(name=name, disk_id=disk_id), self.assertRaises(DiskImageError):
                create_blank_d64_image(name, disk_id)
        self.assertEqual(encode_disk_id('a1'), b'A1')


if __name__ == '__main__':
    unittest.main()
