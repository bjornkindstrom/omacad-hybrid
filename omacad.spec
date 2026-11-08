# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ('assets', 'assets'),
    ('CHANGELOG.md', '.'),
    ('omacad/scripting/GUIDE.md', 'omacad/scripting'),          # what the AI gets (New Script with AI)
    ('omacad/scripting/examples', 'omacad/scripting/examples'),
]

hiddenimports = [
    # standard modules user scripts may import (GUIDE.md lists them); the exe only has what is bundled
    'math', 'cmath', 'random', 'statistics', 'fractions', 'decimal', 'itertools', 'functools', 'collections',
    'dataclasses', 'json', 're', 'string', 'bisect', 'heapq',
    '_viewport_native',
    'manifold3d',
    'trimesh',
    'OpenGL',
    'OpenGL.GL',
    'OpenGL.GL.shaders',
    'OpenGL.arrays.ctypesarrays',
    'shapely',
    'python_solvespace',
    'urllib.request',
    'http.client',
    'email.message',
    'ssl',
    'omacad.rfc',
    'omacad._rfc_secret',
    'tomllib',
]

excludes = [
    'tkinter',
    'matplotlib',
    'scipy',
    'pandas',
    'unittest',
    'test',
    'distutils',
    'pydoc',
    'sqlite3',
    'xmlrpc',
    'curses',
    'IPython',
    'jedi',
    'docutils',
    'setuptools',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Omacad',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
