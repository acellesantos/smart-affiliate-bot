@echo off
title Rodando Robo - NOITE
cd /d "%~dp0"
cd ..

:: Tenta usar o python do ambiente virtual da raiz
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py NOITE
) else (
    python rastreador_ofertas.py NOITE
)

pause