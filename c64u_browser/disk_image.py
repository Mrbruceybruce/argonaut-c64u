# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Read-only Commodore 1541 D64 directory parsing.

The parser deliberately exposes the flat CBM DOS directory.  It never rewrites
the source image and does not invent host-style folders inside a floppy disk.
"""
from dataclasses import dataclass
from pathlib import Path

from .diagnostics import operation_event


class DiskImageError(ValueError):
    """The image is not a supported, structurally readable D64."""


@dataclass(frozen=True)
class D64Geometry:
    tracks: int
    sectors: int
    error_table: bool
    standard: bool


@dataclass(frozen=True)
class DiskDirectoryEntry:
    name: str
    raw_name: bytes
    file_type: str
    closed: bool
    locked: bool
    start_track: int
    start_sector: int
    blocks: int


@dataclass(frozen=True)
class D64Directory:
    disk_name: str
    raw_disk_name: bytes
    disk_id: str
    dos_type: str
    dos_version: str
    blocks_free: int
    entries: tuple[DiskDirectoryEntry, ...]
    geometry: D64Geometry


@dataclass(frozen=True)
class D64Validation:
    standard_compatible: bool
    entries_checked: int
    issues: tuple[str, ...]


_GEOMETRIES = {
    174848: D64Geometry(35, 683, False, True),
    175531: D64Geometry(35, 683, True, True),
    196608: D64Geometry(40, 768, False, False),
    197376: D64Geometry(40, 768, True, False),
    205312: D64Geometry(42, 802, False, False),
    206114: D64Geometry(42, 802, True, False),
}
_FILE_TYPES = {0: 'DEL', 1: 'SEQ', 2: 'PRG', 3: 'USR', 4: 'REL'}


def sectors_on_track(track):
    if not 1 <= track <= 42:
        raise DiskImageError(f'Invalid D64 track {track}.')
    if track <= 17:
        return 21
    if track <= 24:
        return 19
    if track <= 30:
        return 18
    return 17


def decode_petscii(value):
    """Conservatively render common disk-label PETSCII without losing raw data."""
    value = bytes(value).rstrip(b'\xa0')
    rendered = []
    for byte in value:
        if byte == 0xa0:
            rendered.append(' ')
        elif 0x20 <= byte <= 0x7e:
            rendered.append(chr(byte))
        elif 0xc1 <= byte <= 0xda:
            rendered.append(chr(byte - 0x80))
        else:
            rendered.append('\ufffd')
    return ''.join(rendered)


class D64Image:
    """An immutable view of a standard or recognized extended D64 image."""

    def __init__(self, data):
        self._source = bytes(data)
        try:
            self.geometry = _GEOMETRIES[len(self._source)]
        except KeyError as exc:
            raise DiskImageError(
                'Unsupported D64 size. Expected a 35-track image or a recognized '
                '40/42-track extended image, with or without an error table.') from exc
        self._disk_data = self._source[:self.geometry.sectors * 256]

    @classmethod
    def from_path(cls, path):
        return cls(Path(path).read_bytes())

    @property
    def source_bytes(self):
        return self._source

    def sector(self, track, sector):
        if not 1 <= track <= self.geometry.tracks:
            raise DiskImageError(f'Track {track} is outside this D64 image.')
        count = sectors_on_track(track)
        if not 0 <= sector < count:
            raise DiskImageError(
                f'Sector {sector} is outside track {track}; valid sectors are 0-{count - 1}.')
        preceding = sum(sectors_on_track(number) for number in range(1, track))
        offset = (preceding + sector) * 256
        return self._disk_data[offset:offset + 256]

    def directory(self):
        with operation_event('disk_image', 'read_directory', 'd64'):
            return self._directory()

    def _directory(self):
        header = self.sector(18, 0)
        raw_name = header[0x90:0xa0]
        first_track, first_sector = header[0], header[1]
        if first_track != 18 or not 1 <= first_sector < sectors_on_track(18):
            raise DiskImageError('D64 header does not point to a valid 1541 directory sector.')

        blocks_free = 0
        for track in range(1, 36):
            if track == 18:
                continue
            free = header[4 + (track - 1) * 4]
            if free > sectors_on_track(track):
                raise DiskImageError(f'D64 BAM has an invalid free-block count for track {track}.')
            blocks_free += free

        entries = []
        seen = set()
        track, sector = first_track, first_sector
        while track:
            if track != 18 or not 1 <= sector < sectors_on_track(18):
                raise DiskImageError('D64 directory chain leaves the standard directory track.')
            location = (track, sector)
            if location in seen:
                raise DiskImageError('D64 directory chain contains a loop.')
            seen.add(location)
            block = self.sector(track, sector)
            for index in range(8):
                start = 2 + index * 32
                raw_type = block[start]
                if raw_type == 0:
                    continue
                kind = raw_type & 0x07
                entries.append(DiskDirectoryEntry(
                    name=decode_petscii(block[start + 3:start + 19]),
                    raw_name=bytes(block[start + 3:start + 19]),
                    file_type=_FILE_TYPES.get(kind, f'${kind:X}'),
                    closed=bool(raw_type & 0x80),
                    locked=bool(raw_type & 0x40),
                    start_track=block[start + 1],
                    start_sector=block[start + 2],
                    blocks=int.from_bytes(block[start + 28:start + 30], 'little'),
                ))
            track, sector = block[0], block[1]

        return D64Directory(
            disk_name=decode_petscii(raw_name),
            raw_disk_name=bytes(raw_name),
            disk_id=decode_petscii(header[0xa2:0xa4]),
            dos_type=decode_petscii(header[0xa5:0xa7]),
            dos_version=decode_petscii(header[2:3]),
            blocks_free=blocks_free,
            entries=tuple(entries),
            geometry=self.geometry,
        )

    def read_file(self, entry):
        """Return the file's raw CBM data bytes by following its sector chain."""
        with operation_event('disk_image', 'read_file', 'entry'):
            return self._read_file(entry)

    def _read_file(self, entry):
        return self._file_chain(entry)[0]

    def _file_chain(self, entry):
        if not isinstance(entry, DiskDirectoryEntry):
            raise TypeError('entry must be a DiskDirectoryEntry')
        track, sector = entry.start_track, entry.start_sector
        if track == 0:
            if sector == 0 and entry.blocks == 0:
                return b'', ()
            raise DiskImageError(f'{entry.name} has an invalid starting track and sector.')

        result = bytearray()
        seen = set()
        while track:
            location = (track, sector)
            if location in seen:
                raise DiskImageError(f'{entry.name} contains a loop in its file chain.')
            seen.add(location)
            block = self.sector(track, sector)
            next_track, next_sector = block[0], block[1]
            if next_track == 0:
                # On a terminal CBM DOS sector, byte 1 is one greater than the
                # number of payload bytes used (valid values are 1 through 255).
                if not 1 <= next_sector <= 255:
                    raise DiskImageError(f'{entry.name} has an invalid final-sector length.')
                result.extend(block[2:next_sector + 1])
                break
            result.extend(block[2:])
            track, sector = next_track, next_sector
            if len(seen) > self.geometry.sectors:
                raise DiskImageError(f'{entry.name} file chain is longer than the disk.')
        return bytes(result), tuple(seen)

    def validate(self):
        """Report standard directory/file-chain issues without rejecting the image."""
        with operation_event('disk_image', 'validate', 'd64'):
            directory = self._directory()
            issues = []
            if not self.geometry.standard:
                issues.append('geometry.extended_tracks')
            occupied = set()
            checked = 0
            for index, entry in enumerate(directory.entries, 1):
                if entry.file_type == 'DEL':
                    continue
                checked += 1
                try:
                    _, sectors = self._file_chain(entry)
                except DiskImageError:
                    issues.append(f'entry.{index}.chain')
                    continue
                if len(sectors) != entry.blocks:
                    issues.append(f'entry.{index}.block_count')
                if occupied.intersection(sectors):
                    issues.append(f'entry.{index}.cross_link')
                occupied.update(sectors)
            return D64Validation(
                standard_compatible=not issues,
                entries_checked=checked,
                issues=tuple(issues),
            )
