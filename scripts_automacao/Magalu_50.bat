@echo off
title Ofertas Magalu - Ate R$ 50
echo ===============================
echo       MAGALU - ATE R$ 50
echo ===============================
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py MAGALU50 --pular MOVEIS CELULARES NOTEBOOKS TELEVISOES ELETRODOMESTICOS PCGAMER
) else (
    python rastreador_ofertas.py MAGALU50 --pular MOVEIS CELULARES NOTEBOOKS TELEVISOES ELETRODOMESTICOS PCGAMER
)
pause