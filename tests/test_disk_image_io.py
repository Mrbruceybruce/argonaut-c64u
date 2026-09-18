import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from c64u_browser.api import BrowserError
from c64u_browser.disk_image import D64Image
from c64u_browser.disk_image_io import (
    extract_new, read_host_file_for_d64, read_local_d64, read_local_d71,
    read_local_d81, read_local_disk_image, read_remote_d64, read_remote_d71,
    read_remote_d81,
    read_remote_disk_image, suggested_name)


FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1541-authentic.d64'
D71_FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1571-authentic.d71'
D81_FIXTURE = Path(__file__).with_name('fixtures') / 'vice-1581-authentic.d81'


class DiskImageIOTests(unittest.TestCase):
    def test_local_reader_accepts_regular_d64_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            image = folder / 'disk.d64'
            image.write_bytes(FIXTURE.read_bytes())
            self.assertEqual(read_local_d64(image).directory().disk_name, 'ARGONAUT')
            link = folder / 'link.d64'
            os.symlink(image, link)
            with self.assertRaisesRegex(BrowserError, 'regular local D64'):
                read_local_d64(link)

    def test_remote_reader_uses_bounded_remote_file_reader(self):
        client = Mock()
        with patch('c64u_browser.disk_image_io.read_remote',
                   return_value=FIXTURE.read_bytes()) as reader:
            image = read_remote_d64(client, '/USB2/GAMES/DISK.D64')
        reader.assert_called_once_with(client, '/USB2/GAMES/DISK.D64')
        self.assertEqual(image.directory().disk_name, 'ARGONAUT')

    def test_remote_reader_requires_storage_image_path(self):
        for path in ('/USB2', '/Flash/disk.d64', '/USB2/disk.prg'):
            with self.subTest(path=path), self.assertRaises(BrowserError):
                read_remote_d64(Mock(), path)

    def test_local_and_remote_d71_readers_dispatch_by_real_suffix(self):
        self.assertEqual(read_local_d71(D71_FIXTURE).directory().disk_id, '71')
        self.assertEqual(read_local_disk_image(D71_FIXTURE).format_name, 'D71')
        client = Mock()
        with patch('c64u_browser.disk_image_io.read_remote',
                   return_value=D71_FIXTURE.read_bytes()) as reader:
            image = read_remote_d71(client, '/USB2/GAMES/DISK.D71')
            dispatched = read_remote_disk_image(client, '/USB2/GAMES/DISK.D71')
        self.assertEqual((image.format_name, dispatched.format_name), ('D71', 'D71'))
        self.assertEqual(reader.call_count, 2)

    def test_local_and_remote_d81_readers_dispatch_by_real_suffix(self):
        self.assertEqual(read_local_d81(D81_FIXTURE).directory().disk_id, '81')
        self.assertEqual(read_local_disk_image(D81_FIXTURE).format_name, 'D81')
        client = Mock()
        with patch('c64u_browser.disk_image_io.read_remote',
                   return_value=D81_FIXTURE.read_bytes()) as reader:
            image = read_remote_d81(client, '/USB2/GAMES/DISK.D81')
            dispatched = read_remote_disk_image(client, '/USB2/GAMES/DISK.D81')
        self.assertEqual((image.format_name, dispatched.format_name), ('D81', 'D81'))
        self.assertEqual(reader.call_count, 2)

    def test_disk_image_dispatch_rejects_unimplemented_formats(self):
        with self.assertRaisesRegex(BrowserError, 'D64, D71 or D81'):
            read_local_disk_image('disk.d80')
        with self.assertRaisesRegex(BrowserError, 'D64, D71 or D81'):
            read_remote_disk_image(Mock(), '/USB2/disk.d80')

    def test_extracts_exact_bytes_without_replacing_destination(self):
        image = D64Image.from_path(FIXTURE)
        entry = image.directory().entries[1]
        expected = bytes((index * 37 + 11) % 256 for index in range(600))
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / suggested_name(entry)
            result = extract_new(image, entry, destination)
            self.assertEqual(result['bytes'], 600)
            self.assertEqual(destination.read_bytes(), expected)
            destination.write_bytes(b'keep me')
            with self.assertRaisesRegex(BrowserError, 'already exists'):
                extract_new(image, entry, destination)
            self.assertEqual(destination.read_bytes(), b'keep me')

    def test_suggested_name_is_safe_for_host_chooser(self):
        entry = D64Image.from_path(FIXTURE).directory().entries[0]
        self.assertEqual(suggested_name(entry), 'HELLO.prg')

    def test_import_reader_accepts_bounded_regular_file_only(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'hello.prg'
            source.write_bytes(b'hello')
            self.assertEqual(read_host_file_for_d64(source), b'hello')
            link = folder / 'link.prg'
            os.symlink(source, link)
            with self.assertRaisesRegex(BrowserError, 'regular local file'):
                read_host_file_for_d64(link)
            large = folder / 'large.prg'
            large.write_bytes(bytes(174849))
            with self.assertRaisesRegex(BrowserError, 'too large'):
                read_host_file_for_d64(large)


if __name__ == '__main__':
    unittest.main()
