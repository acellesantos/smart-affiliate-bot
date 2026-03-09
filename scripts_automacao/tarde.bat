@echo off
title Rodando Robo - TARDE
cd /d "%~dp0"
cd ..

:: Tenta usar o python do ambiente virtual da raiz
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py TARDE
) else (
    python rastreador_ofertas.py TARDE
)

pause