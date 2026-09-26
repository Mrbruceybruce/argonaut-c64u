# SPDX-License-Identifier: GPL-3.0-or-later
"""Packaged runtime setup; must run before importing any GStreamer consumer."""
import os
from pathlib import Path
import sys


def configure_gstreamer_registry(*, development=False):
    """Keep macOS runtime cache writes outside the signed application.

    Called by the entry script after PyInstaller runtime hooks. Packaged macOS
    deliberately overrides both registry variables (including explicit values)
    to enforce channel isolation and prevent bundle-local writes. Plugin search
    paths are unchanged. Other platforms and unfrozen runs retain their entire
    environment. Failure to create the cache directory aborts startup rather
    than falling back to the signed bundle.
    """
    if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
        return
    channel = 'argonaut-development' if development else 'argonaut'
    directory = (Path.home() / 'Library' / 'Caches' / channel / 'gstreamer').resolve()
    bundle = Path(sys._MEIPASS).resolve()
    protected = [bundle, *(p for p in bundle.parents if p.suffix == '.app')]
    registry = directory / 'registry.bin'
    if any(registry.is_relative_to(p) for p in protected) or registry.is_symlink():
        raise RuntimeError('GStreamer cache must be outside the application bundle')
    directory.mkdir(parents=True, exist_ok=True)
    os.environ['GST_REGISTRY'] = str(registry)
    os.environ['GST_REGISTRY_1_0'] = str(registry)
