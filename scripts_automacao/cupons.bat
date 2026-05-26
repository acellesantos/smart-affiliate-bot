@echo off
title Rodando Robo - CUPONS
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py --cupons
) else (
    python rastreador_ofertas.py --cupons
)
pause