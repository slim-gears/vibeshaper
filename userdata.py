"""Where VibeShaper keeps the user's own files (settings with API keys, logs).

They live outside the add-in folder, so updating or reinstalling the add-in never touches them,
and they never end up in a copy of the add-in someone shares:
  Windows: %APPDATA%\\VibeShaper
  macOS:   ~/Library/Application Support/VibeShaper
  other:   $XDG_CONFIG_HOME/vibeshaper (~/.config/vibeshaper)
Set VIBESHAPER_HOME to use another folder (the tests do).
"""
import os
import pathlib
import sys


def folder() -> pathlib.Path:
    custom = os.environ.get('VIBESHAPER_HOME')
    if custom:
        return pathlib.Path(custom)
    home = pathlib.Path.home()
    if sys.platform == 'win32':
        return pathlib.Path(os.environ.get('APPDATA') or home / 'AppData' / 'Roaming') / 'VibeShaper'
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'VibeShaper'
    return pathlib.Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config') / 'vibeshaper'


def path(name: str) -> pathlib.Path:
    """A file in the folder (the folder is created if needed)."""
    f = folder()
    try:
        f.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return f / name
