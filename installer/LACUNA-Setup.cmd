@echo off
rem LACUNA installer: double-click. Installs into %LOCALAPPDATA%\LACUNA, no admin rights needed.
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/leon-qr-li/lacuna/releases/latest/download/install.ps1 | iex"
pause
