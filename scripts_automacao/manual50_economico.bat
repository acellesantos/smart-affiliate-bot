@echo off
title Ofertas Manual - Ate R$ 50
echo Rodando MANUAL50 sem Moveis, Celulares e Notebooks...
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py MANUAL50 --pular MOVEIS CELULARES NOTEBOOKS TELEVISOES
) else (
    python rastreador_ofertas.py MANUAL50 --pular MOVEIS CELULARES NOTEBOOKS TELEVISOES
)
pause