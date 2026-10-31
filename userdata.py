"""Where PromptCAD keeps the user's own files (settings with API keys, logs).

They live outside the add-in folder, so updating or reinstalling the add-in never touches them,
and they never end up in a copy of the add-in someone shares:
  Windows: %APPDATA%\\PromptCAD
  macOS:   ~/Library/Application Support/PromptCAD
  other:   $XDG_CONFIG_HOME/promptcad (~/.config/promptcad)
Set PROMPTCAD_HOME to use another folder (the tests do).
"""
import os
import pathlib
import sys


def folder() -> pathlib.Path:
    custom = os.environ.get('PROMPTCAD_HOME')
    if custom:
        return pathlib.Path(custom)
    home = pathlib.Path.home()
    if sys.platform == 'win32':
        return pathlib.Path(os.environ.get('APPDATA') or home / 'AppData' / 'Roaming') / 'PromptCAD'
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'PromptCAD'
    return pathlib.Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config') / 'promptcad'


def path(name: str) -> pathlib.Path:
    """A file in the folder (the folder is created if needed)."""
    f = folder()
    try:
        f.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return f / name
