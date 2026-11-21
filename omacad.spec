# -*- mode: python ; coding: utf-8 -*-

import glob
import importlib.util
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


def _opencascade_binaries():
    """OpenCascade (cadquery-ocp, B-rep bodies) on Windows: every DLL its extension loads, from cadquery_ocp.libs
    and vtk.libs only as far as needed (46 of VTK's files, ~130 MB; the rest of VTK, ~185 MB, and its Python modules
    stay out). OCP/__init__.py puts both folders next to the package on the DLL search path, so they keep their names
    and places. Elsewhere (Linux wheels) PyInstaller finds the shared libraries itself."""
    spec = importlib.util.find_spec("OCP")
    if spec is None or not spec.submodule_search_locations:
        return []
    package = list(spec.submodule_search_locations)[0]
    site = os.path.dirname(package)
    folders = ("cadquery_ocp.libs", "vtk.libs")
    if not os.path.isdir(os.path.join(site, folders[0])):
        return []
    import pefile
    index = {}
    for folder in folders:
        for path in glob.glob(os.path.join(site, folder, "*")):
            index[os.path.basename(path).lower()] = (path, folder)
    todo = glob.glob(os.path.join(package, "OCP*.pyd"))
    seen, out = set(todo), []
    while todo:
        pe = pefile.PE(todo.pop(), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                               pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        names = [e.dll.decode().lower() for e in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])]
        names += [e.dll.decode().lower() for e in getattr(pe, "DIRECTORY_ENTRY_DELAY_IMPORT", [])]
        pe.close()
        for name in names:
            if name in index and index[name][0] not in seen:
                path, folder = index[name]
                seen.add(path)
                todo.append(path)
                out.append((path, folder))
    for folder in folders:                    # OCP/__init__ adds both folders; a missing one stops the import
        if not any(dest == folder for _, dest in out):
            raise SystemExit(f"OpenCascade bundle: nothing collected from {folder}")
    return out

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
] + (collect_submodules('OCP') if importlib.util.find_spec('OCP') else [])    # B-rep bodies (OpenCascade)

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
    'vtk',                  # OpenCascade needs VTK's DLLs (collected above), not its Python modules
    'vtkmodules',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=_opencascade_binaries(),
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
