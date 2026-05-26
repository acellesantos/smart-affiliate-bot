@echo off
title Ofertas Mercado Livre - Ate R$ 50
echo ===============================
echo    MERCADO LIVRE - ATE R$ 50
echo ===============================
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py ML50
) else (
    python rastreador_ofertas.py ML50
)
pause