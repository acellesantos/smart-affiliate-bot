@echo off
title Rodando Robo - NOITE
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py NOITE
) else (
    python rastreador_ofertas.py NOITE
)
pause