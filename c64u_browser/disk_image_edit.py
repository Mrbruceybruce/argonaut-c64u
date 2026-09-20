# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Staged, hardware-compatible edits for standard 1541 and 1571 images."""
from dataclasses import dataclass

from .disk_image import (
    D64Image, D71Image, D81Image, DiskDirectoryEntry, DiskImageError,
    sectors_on_d71_track, sectors_on_track)
from .diagnostics import operation_event


_TYPE_CODES = {'SEQ': 1, 'PRG': 2, 'USR': 3}


def encode_petscii_name(name):
    """Encode a conservative, interoperable 1541 filename padded to 16 bytes."""
    if not isinstance(name, str):
        raise TypeError('name must be text')
    name = name.strip().upper()
    if not name:
        raise DiskImageError('Enter a disk filename.')
    if len(name) > 16:
        raise DiskImageError('A 1541 disk filename can contain at most 16 characters.')
    try:
        ascii_name = name.encode('ascii')
    except UnicodeEncodeError as exc:
        raise DiskImageError('Use simple C64-compatible characters in the disk filename.') from exc
    if any(byte < 0x20 or byte > 0x7e or byte in (0x2f, 0x5c) for byte in ascii_name):
        raise DiskImageError('Use simple C64-compatible characters without / or \\ in the disk filename.')
    # Directory text loaded with LOAD"$",8 is printed directly by BASIC. Keep
    # uppercase letters in PETSCII's screen-readable $41-$5A range; $C1-$DA
    # renders as graphic/reversed characters on physical C64 hardware.
    return ascii_name.ljust(16, b'\xa0')


def encode_disk_id(disk_id):
    """Encode an optional two-character ID stored in a 1541 header."""
    if not isinstance(disk_id, str):
        raise TypeError('disk_id must be text')
    disk_id = disk_id.strip().upper()
    if not disk_id:
        return b'\xa0\xa0'
    if len(disk_id) != 2:
        raise DiskImageError(
            'A 1541 disk ID must be blank or contain exactly 2 characters.')
    try:
        value = disk_id.encode('ascii')
    except UnicodeEncodeError as exc:
        raise DiskImageError('Use simple C64-compatible characters in the disk ID.') from exc
    if any(byte < 0x20 or byte > 0x7e or byte in (0x2f, 0x5c) for byte in value):
        raise DiskImageError(
            'Use simple C64-compatible characters without / or \\ in the disk ID.')
    return value


def create_blank_d64_image(disk_name, disk_id):
    """Return a validated, standard 35-track disk formatted for CBM DOS 2A."""
    with operation_event('disk_image', 'create_blank', 'd64'):
        raw_name = encode_petscii_name(disk_name)
        raw_id = encode_disk_id(disk_id)
        data = bytearray(683 * 256)

        def offset(track, sector):
            return (sum(sectors_on_track(value) for value in range(1, track))
                    + sector) * 256

        bam_offset = offset(18, 0)
        bam = memoryview(data)[bam_offset:bam_offset + 256]
        bam[:4] = bytes((18, 1, 0x41, 0))
        for track in range(1, 36):
            count = sectors_on_track(track)
            location = 4 + (track - 1) * 4
            bitmap = bytearray(3)
            for sector in range(count):
                bitmap[sector // 8] |= 1 << (sector % 8)
            bam[location] = count
            bam[location + 1:location + 4] = bitmap

        # Track 18 sector 0 is the BAM/header and sector 1 is the first
        # directory sector. Both are allocated on a freshly formatted disk.
        track_18 = 4 + 17 * 4
        for sector in (0, 1):
            bam[track_18 + 1 + sector // 8] &= ~(1 << (sector % 8))
            bam[track_18] -= 1
        bam[0x90:0xa0] = raw_name
        bam[0xa0:0xa2] = b'\xa0\xa0'
        bam[0xa2:0xa4] = raw_id
        bam[0xa4] = 0xa0
        bam[0xa5:0xa7] = b'2A'
        bam[0xa7:0xab] = b'\xa0' * 4

        directory_offset = offset(18, 1)
        data[directory_offset:directory_offset + 2] = bytes((0, 255))
        image = D64Image(data)
        directory = image.directory()
        validation = image.validate()
        if (directory.entries or directory.blocks_free != 664
                or not validation.standard_compatible):
            raise DiskImageError('The blank D64 did not pass complete validation.')
        return image


@dataclass(frozen=True)
class D64Edit:
    operation: str
    description: str


class D64EditSession:
    """Keep D64 changes staged in memory until a new image is explicitly saved."""

    image_type = D64Image
    format_name = 'D64'
    extension = '.d64'
    directory_track = 18
    directory_first_sector = 1
    removable_types = ('PRG', 'SEQ', 'USR', 'REL')

    def __init__(self, image):
        if type(image) is not self.image_type:
            raise TypeError(f'image must be a {self.image_type.__name__}')
        if not image.geometry.standard:
            raise DiskImageError(
                f'Editing requires a standard {image.geometry.tracks}-track '
                f'{self.format_name} image.')
        validation = image.validate()
        if not validation.standard_compatible:
            raise DiskImageError(
                f'Repair the {self.format_name} structure before editing it.')
        self._original = image.source_bytes
        self._data = bytearray(self._original)
        self._changes = []
        self._saved_change_count = 0

    @property
    def image(self):
        return self.image_type(self._data)

    @property
    def changes(self):
        return tuple(self._changes)

    @property
    def dirty(self):
        return bool(self._changes)

    @property
    def has_unsaved_changes(self):
        return len(self._changes) != self._saved_change_count

    def mark_saved(self):
        self._saved_change_count = len(self._changes)

    def discard(self):
        self._data = bytearray(self._original)
        self._changes.clear()
        self._saved_change_count = 0

    def _track_sectors(self, track):
        return sectors_on_track(track)

    def _sector_number(self, track, sector):
        return sum(self._track_sectors(value) for value in range(1, track)) + sector

    def _offset(self, track, sector):
        return self._sector_number(track, sector) * 256

    def _write_sector(self, track, sector, value):
        if len(value) != 256:
            raise ValueError('sector data must be exactly 256 bytes')
        offset = self._offset(track, sector)
        self._data[offset:offset + 256] = value
        self._mark_sector_okay(track, sector)

    def _mark_sector_okay(self, track, sector):
        geometry = self.image.geometry
        if geometry.error_table:
            self._data[geometry.sectors * 256 + self._sector_number(track, sector)] = 1

    def _bam_location(self, track):
        return self._offset(18, 0) + 4 + (track - 1) * 4

    def _is_free(self, track, sector):
        location = self._bam_location(track)
        return bool(self._data[location + 1 + sector // 8] & (1 << (sector % 8)))

    def _set_free(self, track, sector, free):
        location = self._bam_location(track)
        mask = 1 << (sector % 8)
        current = bool(self._data[location + 1 + sector // 8] & mask)
        if current == free:
            return
        if free:
            self._data[location + 1 + sector // 8] |= mask
            self._data[location] += 1
        else:
            self._data[location + 1 + sector // 8] &= ~mask
            if self._data[location] == 0:
                raise DiskImageError(f'D64 BAM free count underflow on track {track}.')
            self._data[location] -= 1
        self._mark_sector_okay(18, 0)

    def _current_entry(self, entry):
        if not isinstance(entry, DiskDirectoryEntry):
            raise TypeError('entry must be a DiskDirectoryEntry')
        for current in self.image.directory().entries:
            if (current.directory_track, current.directory_sector, current.directory_slot) == (
                    entry.directory_track, entry.directory_sector, entry.directory_slot):
                return current
        raise DiskImageError('The selected disk entry changed; select it again.')

    def can_remove(self, entry):
        return (isinstance(entry, DiskDirectoryEntry)
                and entry.file_type in self.removable_types
                and entry.closed and not entry.locked)

    def rename(self, entry, name):
        with operation_event('disk_image', 'stage_rename', 'entry'):
            before = self._data[:]
            try:
                current = self._current_entry(entry)
                raw = encode_petscii_name(name)
                new_name = name.strip().upper()
                if current.name.casefold() == new_name.casefold():
                    raise DiskImageError('The disk file already has that name.')
                if any(item.name.casefold() == new_name.casefold() and item != current
                       for item in self.image.directory().entries):
                    raise DiskImageError('That disk filename is already in use.')
                offset = (self._offset(current.directory_track, current.directory_sector)
                          + 2 + current.directory_slot * 32 + 3)
                self._data[offset:offset + 16] = raw
                self._changes.append(D64Edit(
                    'rename', f'Rename "{current.name}" to "{new_name}"'))
            except Exception:
                self._data = before
                raise

    def remove(self, entry):
        with operation_event('disk_image', 'stage_remove', 'entry'):
            before = self._data[:]
            try:
                current = self._current_entry(entry)
                if current.locked:
                    raise DiskImageError('This disk file is locked and was not removed.')
                if not current.closed:
                    raise DiskImageError('This disk file is open or incomplete and was not removed.')
                if current.file_type not in self.removable_types:
                    raise DiskImageError('This disk file type cannot be removed safely.')
                _, sectors = self.image._file_chain(current)
                side_sectors = self.image._rel_side_chain(current)
                for track, sector in (*sectors, *side_sectors):
                    self._set_free(track, sector, True)
                offset = (self._offset(current.directory_track, current.directory_sector)
                          + 2 + current.directory_slot * 32)
                self._data[offset] = 0
                self._changes.append(D64Edit('remove', f'Remove "{current.name}"'))
            except Exception:
                self._data = before
                raise

    def _directory_slot(self):
        image = self.image
        block = image.sector(self.directory_track, self.directory_first_sector)
        previous = (self.directory_track, self.directory_first_sector)
        seen = set()
        while True:
            track, sector = previous
            if previous in seen:
                raise DiskImageError('D64 directory chain contains a loop.')
            seen.add(previous)
            block = image.sector(track, sector)
            for slot in range(8):
                if block[2 + slot * 32] == 0:
                    return track, sector, slot
            if block[0] == 0:
                break
            previous = (block[0], block[1])
        for sector in range(
                self.directory_first_sector, self._track_sectors(self.directory_track)):
            if self._is_free(self.directory_track, sector):
                self._set_free(self.directory_track, sector, False)
                new_block = bytearray(256)
                new_block[:2] = bytes((0, 255))
                self._write_sector(self.directory_track, sector, new_block)
                old = bytearray(image.sector(*previous))
                old[:2] = bytes((self.directory_track, sector))
                self._write_sector(*previous, old)
                return self.directory_track, sector, 0
        raise DiskImageError(f'The {self.image.drive_model} directory track is full.')

    def add_file(self, data, name, file_type='PRG'):
        with operation_event('disk_image', 'stage_add', 'file'):
            before = self._data[:]
            try:
                file_type = str(file_type).upper()
                if file_type not in _TYPE_CODES:
                    raise DiskImageError('Add a PRG, SEQ, or USR file.')
                raw_name = encode_petscii_name(name)
                new_name = name.strip().upper()
                if any(item.name.casefold() == new_name.casefold()
                       for item in self.image.directory().entries):
                    raise DiskImageError('That disk filename is already in use.')
                data = bytes(data)
                needed = max(1, (len(data) + 253) // 254)
                available = [(track, sector)
                             for track in range(1, self.image.geometry.tracks + 1)
                             if track != self.directory_track
                             for sector in range(self._track_sectors(track))
                             if self._is_free(track, sector)]
                if len(available) < needed:
                    raise DiskImageError(f'The disk needs {needed} free block(s) for this file.')
                directory_track, directory_sector, slot = self._directory_slot()
                chain = available[:needed]
                for index, (track, sector) in enumerate(chain):
                    self._set_free(track, sector, False)
                    payload = data[index * 254:(index + 1) * 254]
                    block = bytearray(256)
                    if index + 1 < len(chain):
                        block[:2] = bytes(chain[index + 1])
                    else:
                        block[:2] = bytes((0, len(payload) + 1))
                    block[2:2 + len(payload)] = payload
                    self._write_sector(track, sector, block)
                directory = bytearray(self.image.sector(directory_track, directory_sector))
                start = 2 + slot * 32
                # Each directory slot is 32 bytes apart, but its first two
                # bytes are the sector-chain link (slot zero) or unused.
                directory[start:start + 30] = bytes(30)
                directory[start:start + 3] = bytes(
                    (0x80 | _TYPE_CODES[file_type], *chain[0]))
                directory[start + 3:start + 19] = raw_name
                directory[start + 28:start + 30] = len(chain).to_bytes(2, 'little')
                self._write_sector(directory_track, directory_sector, directory)
                self._changes.append(D64Edit(
                    'add', f'Add "{new_name}" as {file_type} '
                           f'({len(chain)} block(s))'))
            except Exception:
                self._data = before
                raise

    def add_files(self, files):
        """Stage an import batch atomically, preserving earlier staged edits."""
        before_data = self._data[:]
        before_changes = self._changes[:]
        before_saved_count = self._saved_change_count
        try:
            for data, name, file_type in files:
                self.add_file(data, name, file_type)
        except Exception:
            self._data = before_data
            self._changes = before_changes
            self._saved_change_count = before_saved_count
            raise

    def validated_bytes(self):
        with operation_event(
                'disk_image', 'validate_edits', self.format_name.casefold()):
            image = self.image
            validation = image.validate()
            if not validation.standard_compatible:
                raise DiskImageError('The staged disk image did not pass complete validation.')
            return image.source_bytes


class D71EditSession(D64EditSession):
    """Keep authentic 1571 D71 edits staged until a new image is saved."""

    image_type = D71Image
    format_name = 'D71'
    extension = '.d71'

    def _track_sectors(self, track):
        return sectors_on_d71_track(track)

    def _is_free(self, track, sector):
        if track <= 35:
            return super()._is_free(track, sector)
        second_bam = self._offset(53, 0)
        location = second_bam + (track - 36) * 3
        return bool(self._data[location + sector // 8] & (1 << (sector % 8)))

    def _set_free(self, track, sector, free):
        if track <= 35:
            super()._set_free(track, sector, free)
            return
        bitmap = self._offset(53, 0) + (track - 36) * 3 + sector // 8
        count = self._offset(18, 0) + 0xdd + track - 36
        mask = 1 << (sector % 8)
        current = bool(self._data[bitmap] & mask)
        if current == free:
            return
        if free:
            self._data[bitmap] |= mask
            self._data[count] += 1
        else:
            self._data[bitmap] &= ~mask
            if self._data[count] == 0:
                raise DiskImageError(f'D71 BAM free count underflow on track {track}.')
            self._data[count] -= 1
        self._mark_sector_okay(18, 0)
        self._mark_sector_okay(53, 0)


class D81EditSession(D64EditSession):
    """Keep authentic 1581 D81 edits staged while protecting CBM partitions."""

    image_type = D81Image
    format_name = 'D81'
    extension = '.d81'
    directory_track = 40
    directory_first_sector = 3
    # D81 REL files use super side sectors, which require a separate editor.
    removable_types = ('PRG', 'SEQ', 'USR')

    def _track_sectors(self, track):
        if not 1 <= track <= 80:
            raise DiskImageError(f'Invalid D81 track {track}.')
        return 40

    def _bam_details(self, track, sector):
        bam_sector = 1 if track <= 40 else 2
        bam_offset = self._offset(40, bam_sector)
        entry = 0x10 + ((track - 1) % 40) * 6
        return bam_sector, bam_offset + entry, bam_offset + entry + 1 + sector // 8

    def _is_free(self, track, sector):
        _, _, bitmap = self._bam_details(track, sector)
        return bool(self._data[bitmap] & (1 << (sector % 8)))

    def _set_free(self, track, sector, free):
        bam_sector, count, bitmap = self._bam_details(track, sector)
        mask = 1 << (sector % 8)
        current = bool(self._data[bitmap] & mask)
        if current == free:
            return
        if free:
            self._data[bitmap] |= mask
            self._data[count] += 1
        else:
            self._data[bitmap] &= ~mask
            if self._data[count] == 0:
                raise DiskImageError(f'D81 BAM free count underflow on track {track}.')
            self._data[count] -= 1
        self._mark_sector_okay(40, bam_sector)
