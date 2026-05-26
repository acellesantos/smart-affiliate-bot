@echo off
title Rodando Robo - TARDE
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py TARDE
) else (
    python rastreador_ofertas.py TARDE
)
pause