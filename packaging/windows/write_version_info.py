#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the PyInstaller PE version resource from the release contract."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from c64u_browser.release import (COPYRIGHT, PRODUCT_NAME, PUBLISHER, VERSION,
                                  WINDOWS_NUMERIC_VERSION)


def version_resource():
    numbers = ', '.join(WINDOWS_NUMERIC_VERSION.split('.'))
    return f"""# Generated from c64u_browser.release; do not edit.
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers}), mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', {PUBLISHER!r}),
    StringStruct('FileDescription', {PRODUCT_NAME!r}),
    StringStruct('FileVersion', {WINDOWS_NUMERIC_VERSION!r}),
    StringStruct('InternalName', 'Argonaut'),
    StringStruct('LegalCopyright', {COPYRIGHT!r}),
    StringStruct('OriginalFilename', 'Argonaut.exe'),
    StringStruct('ProductName', {PRODUCT_NAME!r}),
    StringStruct('ProductVersion', {VERSION!r})
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'packaging/windows/version_info.txt')
    args = parser.parse_args()
    args.output.write_text(version_resource(), encoding='utf-8')
