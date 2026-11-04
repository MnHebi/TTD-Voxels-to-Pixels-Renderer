@echo off
rem SPDX-License-Identifier: GPL-2.0-only
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch.ps1"
if errorlevel 1 pause
