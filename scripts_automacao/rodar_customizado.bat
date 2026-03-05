@echo off
echo ==========================================
echo      ROBO DE OFERTAS - MODO CUSTOM
echo ==========================================
echo.
set /p COMANDO="Digite o comando (ex: MANUAL50): "
echo.
echo Categorias comuns: MOVEIS CELULARES NOTEBOOKS TELEVISOES ELETRODOMESTICOS
set /p PULAR="O que voce quer pular? (Separe por espaco ou deixe vazio): "

if "%PULAR%"=="" (
    python script.py %COMANDO%
) else (
    python script.py %COMANDO% --pular %PULAR%
)

pause