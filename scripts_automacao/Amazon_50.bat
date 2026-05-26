@echo off
title Ofertas Amazon - Ate R$ 50
echo ===============================
echo       AMAZON - ATE R$ 50
echo ===============================
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py AMAZON50 --pular CELULARES NOTEBOOKS TELEVISOES
) else (
    python rastreador_ofertas.py AMAZON50 --pular CELULARES NOTEBOOKS TELEVISOES
)
pause