@echo off
title Rodando Robo - ALMOCO
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py ALMOCO
) else (
    python rastreador_ofertas.py ALMOCO
)
pause