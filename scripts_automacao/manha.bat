@echo off
title Rodando Robo - MANHA
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py MANHA
) else (
    python rastreador_ofertas.py MANHA
)
pause