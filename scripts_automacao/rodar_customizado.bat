@echo off
title Robo de Ofertas - Modo Custom
echo ==========================================
echo       ROBO DE OFERTAS - MODO CUSTOM
echo ==========================================
echo.
cd /d "C:\Projetos\BlackFridayAssistant"

set /p COMANDO="Digite o comando (ex: MANUAL50): "
echo.
echo Categorias comuns: MOVEIS CELULARES NOTEBOOKS TELEVISOES ELETRODOMESTICOS
set /p PULAR="O que voce quer pular? (Separe por espaco ou deixe vazio): "

:: Define qual Python usar
set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"

if "%PULAR%"=="" (
    "%PY_CMD%" rastreador_ofertas.py %COMANDO%
) else (
    "%PY_CMD%" rastreador_ofertas.py %COMANDO% --pular %PULAR%
)

pause