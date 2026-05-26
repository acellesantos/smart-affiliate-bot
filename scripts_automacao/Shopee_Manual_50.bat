@echo off
title Ofertas Shopee - Ate R$ 50
echo ===============================
echo        SHOPEE - ATE R$ 50
echo ===============================
cd /d "C:\Projetos\BlackFridayAssistant"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" rastreador_ofertas.py SHOPEE50
) else (
    python rastreador_ofertas.py SHOPEE50
)
pause