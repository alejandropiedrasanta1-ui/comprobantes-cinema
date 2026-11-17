@echo off
rem Crea en GENERADOR\INSTALADOR:
rem   - Comprobantes Cinema Portable.exe   (un solo archivo, se abre sin instalar)
rem   - Instalar Comprobantes Cinema (Windows) X.exe
rem Requisitos: Python con PySide6, PySide6-Fluent-Widgets, Pillow y PyInstaller.
rem El instalador es propio (como el de CineSlide): windows\instalador_windows.cs, se compila con el
rem csc.exe de .NET Framework que ya trae Windows; no hace falta Inno Setup.
cd /d "%~dp0"
set "SALIDA=..\..\INSTALADOR"

echo [1/3] Creando la version portable (un solo .exe)...
python -m PyInstaller --noconfirm --clean --distpath "%SALIDA%" --workpath build-portable portable.spec || goto error

echo [2/3] Empaquetando el programa para el instalador...
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build comprobantes.spec || goto error

echo [3/3] Creando el instalador (ventana propia, como CineSlide)...
set "PS=powershell"
where pwsh >nul 2>nul && set "PS=pwsh"
%PS% -NoProfile -ExecutionPolicy Bypass -File "windows\construir_instalador.ps1" -Dist "dist\Comprobantes Cinema" -Salida "%SALIDA%" || goto error

rem Borra los archivos temporales de la compilacion
rd /s /q build build-portable dist dist-portable 2>nul
if exist "%SALIDA%\Comprobantes Cinema" rd /s /q "%SALIDA%\Comprobantes Cinema"
echo.
echo Listo: en GENERADOR\INSTALADOR estan la version portable y el instalador.
pause
exit /b 0

:error
echo.
echo *** Hubo un error. Revisa los mensajes de arriba. ***
pause
exit /b 1
