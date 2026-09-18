# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Staged, hardware-compatible edits for standard 1541 D64 images."""
from dataclasses import dataclass

from .disk_image import D64Image, DiskDirectoryEntry, DiskImageError, sectors_on_track
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
    # VICE c1541 and CBM DOS directory sectors conventionally store uppercase
    # letters in PETSCII's shifted $C1-$DA range.
    raw = bytes(byte + 0x80 if 0x41 <= byte <= 0x5a else byte
                for byte in ascii_name)
    return raw.ljust(16, b'\xa0')


@dataclass(frozen=True)
class D64Edit:
    operation: str
    description: str


class D64EditSession:
    """Keep D64 changes staged in memory until a new image is explicitly saved."""

    def __init__(self, image):
        if not isinstance(image, D64Image):
            raise TypeError('image must be a D64Image')
        if not image.geometry.standard:
            raise DiskImageError('Editing requires a standard 35-track D64 image.')
        validation = image.validate()
        if not validation.standard_compatible:
            raise DiskImageError('Repair the D64 structure before editing it.')
        self._original = image.source_bytes
        self._data = bytearray(self._original)
        self._changes = []
        self._saved_change_count = 0

    @property
    def image(self):
        return D64Image(self._data)

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

    @staticmethod
    def _sector_number(track, sector):
        return sum(sectors_on_track(value) for value in range(1, track)) + sector

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
                if current.file_type == 'REL':
                    raise DiskImageError(
                        'REL files need side-sector support before they can be removed safely.')
                if current.locked:
                    raise DiskImageError('This disk file is locked and was not removed.')
                if not current.closed:
                    raise DiskImageError('This disk file is open or incomplete and was not removed.')
                if current.file_type not in _TYPE_CODES:
                    raise DiskImageError('This disk file type cannot be removed safely.')
                _, sectors = self.image._file_chain(current)
                for track, sector in sectors:
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
        block = image.sector(18, 1)
        previous = (18, 1)
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
        for sector in range(1, sectors_on_track(18)):
            if self._is_free(18, sector):
                self._set_free(18, sector, False)
                new_block = bytearray(256)
                new_block[:2] = bytes((0, 255))
                self._write_sector(18, sector, new_block)
                old = bytearray(image.sector(*previous))
                old[:2] = bytes((18, sector))
                self._write_sector(*previous, old)
                return 18, sector, 0
        raise DiskImageError('The 1541 directory track is full.')

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
                available = [(track, sector) for track in range(1, 36) if track != 18
                             for sector in range(sectors_on_track(track))
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

    def validated_bytes(self):
        with operation_event('disk_image', 'validate_edits', 'd64'):
            image = self.image
            validation = image.validate()
            if not validation.standard_compatible:
                raise DiskImageError('The staged disk image did not pass complete validation.')
            return image.source_bytes
