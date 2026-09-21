# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Bruce Marcus
"""Strict, presentation-neutral PSID/RSID metadata parsing."""
from dataclasses import dataclass
import hashlib


MAX_SID_BYTES = 128 * 1024


class SidFormatError(ValueError):
    """The supplied bytes are not a structurally valid supported SID file."""


@dataclass(frozen=True)
class SidChip:
    address: int
    model: str


@dataclass(frozen=True)
class SidMetadata:
    format: str
    version: int
    title: str
    author: str
    released: str
    declared_load_address: int
    effective_load_address: int
    init_address: int
    play_address: int
    songs: int
    start_song: int
    speed: int
    song_speeds: tuple[str, ...]
    clock: str
    chips: tuple[SidChip, ...]
    mus: bool
    playsid_specific: bool
    rsid_basic: bool
    relocation_start_page: int
    relocation_pages: int
    compatibility_flags: tuple[str, ...]
    warnings: tuple[str, ...]
    playback_classification: str
    playback_eligible: bool
    payload_size: int
    file_size: int
    sha256: str

    @property
    def sid_count(self):
        return len(self.chips)

    @property
    def second_sid_address(self):
        return self.chips[1].address if len(self.chips) > 1 else None

    @property
    def third_sid_address(self):
        return self.chips[2].address if len(self.chips) > 2 else None


def _word(data, offset):
    return int.from_bytes(data[offset:offset + 2], 'big')


def _text(data, offset):
    return data[offset:offset + 32].split(b'\0', 1)[0].decode(
        'cp1252', errors='replace').strip()


def _model(value):
    return ('unknown', 'MOS6581', 'MOS8580', 'MOS6581-or-MOS8580')[value]


def _extra_sid(raw, version, minimum_version):
    if version < minimum_version:
        if raw:
            raise SidFormatError('SID header uses an extra SID field before its format version supports it.')
        return None, False
    valid = (0x42 <= raw <= 0x7f or 0xe0 <= raw <= 0xfe) and raw % 2 == 0
    return ((0xd000 | (raw << 4)) if valid else None), bool(raw and not valid)


def _ranges_overlap(first_start, first_end, second_start, second_end):
    return first_start < second_end and second_start < first_end


def parse_sid(value):
    """Return validated SID metadata; never executes or transports SID data."""
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise SidFormatError('SID data must be bytes.')
    data = bytes(value)
    if not 0x76 < len(data) <= MAX_SID_BYTES:
        raise SidFormatError('SID file size is outside the supported validation bound.')
    magic = data[:4]
    if magic not in (b'PSID', b'RSID'):
        raise SidFormatError('SID file does not begin with a PSID or RSID header.')
    format_name = magic.decode('ascii')
    version = _word(data, 4)
    if version not in (1, 2, 3, 4) or (format_name == 'RSID' and version == 1):
        raise SidFormatError('SID format version is unsupported.')
    expected_offset = 0x76 if version == 1 else 0x7c
    data_offset = _word(data, 6)
    if data_offset != expected_offset or len(data) <= data_offset:
        raise SidFormatError('SID data offset or payload is invalid.')

    declared_load = _word(data, 8)
    init_address = _word(data, 10)
    play_address = _word(data, 12)
    songs = _word(data, 14)
    start_song = _word(data, 16)
    speed = int.from_bytes(data[18:22], 'big')
    if not 1 <= songs <= 256 or not 1 <= start_song <= songs:
        raise SidFormatError('SID song count or default song is invalid.')

    payload_offset = data_offset
    if declared_load == 0:
        if len(data) < data_offset + 3:
            raise SidFormatError('SID payload does not contain an embedded load address and data.')
        effective_load = int.from_bytes(data[data_offset:data_offset + 2], 'little')
        payload_offset += 2
    else:
        effective_load = declared_load
    payload_size = len(data) - payload_offset
    if payload_size <= 0 or effective_load + payload_size > 0x10000:
        raise SidFormatError('SID payload exceeds the C64 address space.')

    flags = _word(data, 0x76) if version >= 2 else 0
    if flags & ~0x03ff:
        raise SidFormatError('SID header contains unsupported reserved flags.')
    mus = bool(flags & 1)
    flag_one = bool(flags & 2)
    playsid_specific = format_name == 'PSID' and flag_one
    rsid_basic = format_name == 'RSID' and flag_one
    clock = ('unknown', 'PAL', 'NTSC', 'PAL-and-NTSC')[(flags >> 2) & 3]
    primary_model = _model((flags >> 4) & 3)
    second_model = _model((flags >> 6) & 3)
    third_model = _model((flags >> 8) & 3)
    if second_model == 'unknown':
        second_model = primary_model
    if third_model == 'unknown':
        third_model = primary_model

    relocation_start = data[0x78] if version >= 2 else 0
    relocation_pages = data[0x79] if version >= 2 else 0
    if relocation_start in (0, 0xff):
        if relocation_pages:
            raise SidFormatError('SID relocation length is invalid for its start page.')
    else:
        if not relocation_pages or relocation_start + relocation_pages > 0x100:
            raise SidFormatError('SID relocation range is invalid.')
        relocation_begin = relocation_start << 8
        relocation_end = (relocation_start + relocation_pages) << 8
        load_end = effective_load + payload_size
        if _ranges_overlap(relocation_begin, relocation_end,
                           effective_load, load_end):
            raise SidFormatError('SID relocation range overlaps its payload.')
        if format_name == 'RSID' and any(_ranges_overlap(
                relocation_begin, relocation_end, start, end)
                for start, end in ((0, 0x400), (0xa000, 0xc000),
                                   (0xd000, 0x10000))):
            raise SidFormatError('RSID relocation range overlaps reserved memory.')

    second_raw = data[0x7a] if version >= 2 else 0
    third_raw = data[0x7b] if version >= 2 else 0
    second_address, invalid_second = _extra_sid(second_raw, version, 3)
    third_address, invalid_third = _extra_sid(third_raw, version, 4)
    if second_address is not None and third_address == second_address:
        raise SidFormatError('Second and third SID addresses must differ.')

    if format_name == 'RSID':
        if declared_load != 0 or play_address != 0 or speed != 0:
            raise SidFormatError('RSID reserved load, play and speed fields must be zero.')
        if effective_load < 0x07e8:
            raise SidFormatError('RSID effective load address is below $07E8.')
        if rsid_basic:
            if init_address != 0:
                raise SidFormatError('RSID BASIC files require a zero init address.')
        elif init_address and not (0x07e8 <= init_address <= 0x9fff
                                  or 0xc000 <= init_address <= 0xcfff):
            raise SidFormatError('RSID init address is outside executable RAM.')
        if (not rsid_basic and init_address
                and not effective_load <= init_address < effective_load + payload_size):
            raise SidFormatError('RSID init address is outside its load image.')

    song_speeds = []
    for index in range(songs):
        if format_name == 'RSID':
            song_speeds.append('installed-interrupt')
            continue
        if index < 32:
            bit = index
        elif playsid_specific or version <= 1:
            bit = index % 32
        else:
            bit = 31
        song_speeds.append('cia-1' if speed & (1 << bit) else 'vbi')

    warnings = []
    compatibility_flags = []
    if mus:
        compatibility_flags.append('mus-data')
        warnings.append('Compute! MUS data needs an external player and is blocked from physical playback.')
    if playsid_specific:
        compatibility_flags.append('playsid-specific')
        warnings.append('PlaySID-specific data is not compatible with physical C64 playback.')
    if rsid_basic:
        compatibility_flags.append('rsid-basic')
    if format_name == 'RSID':
        compatibility_flags.append('real-c64-environment')
        warnings.append('RSID requires a true C64 environment; C64U firmware compatibility is unverified.')
    if clock == 'unknown':
        warnings.append('The SID file does not declare a PAL or NTSC clock requirement.')
    if primary_model == 'unknown':
        warnings.append('The SID file does not declare a primary SID model.')
    if invalid_second:
        warnings.append('The encoded second SID address is invalid and is treated as absent.')
    if invalid_third:
        warnings.append('The encoded third SID address is invalid and is treated as absent.')

    chips = [SidChip(0xd400, primary_model)]
    if second_address is not None:
        chips.append(SidChip(second_address, second_model))
    if third_address is not None:
        chips.append(SidChip(third_address, third_model))
    if len(chips) > 1:
        warnings.append(f'This tune requests {len(chips)} SID chips; device compatibility is unverified.')

    blocked = mus or playsid_specific
    classification = 'blocked' if blocked else ('warning' if warnings else 'eligible')
    return SidMetadata(
        format_name, version, _text(data, 0x16), _text(data, 0x36),
        _text(data, 0x56), declared_load, effective_load, init_address,
        play_address, songs, start_song, speed, tuple(song_speeds), clock,
        tuple(chips), mus, playsid_specific, rsid_basic, relocation_start,
        relocation_pages, tuple(compatibility_flags), tuple(warnings),
        classification, not blocked, payload_size, len(data),
        hashlib.sha256(data).hexdigest())
