@echo off
title Rodando Robo - ALMOCO
cd /d "%~dp0"
cd ..

:: Tenta usar o python do ambiente virtual da raiz
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py ALMOCO
) else (
    python rastreador_ofertas.py ALMOCO
)

pause