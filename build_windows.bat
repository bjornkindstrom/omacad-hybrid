@echo off
echo ==============================================
echo  Bygger Omacad kompakt enskild .exe (Onefile)
echo ==============================================

python -m pip install --upgrade pip
pip install PySide6 numpy manifold3d trimesh PyOpenGL Pillow shapely pyinstaller

pyinstaller --clean omacad.spec

echo.
echo ==============================================
echo  Klart! Fristående EXE finns i: dist\Omacad.exe
echo ==============================================
pause
