@echo off
set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_PATH%" set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

echo Finalizando processos do Chrome existentes...
taskkill /F /IM chrome.exe /T >nul 2>&1

echo Iniciando Chrome no modo de depuracao...
start "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="C:\Users\usuario\whatsapp_selenium_profile"

echo.
echo ========================================================
echo Chrome aberto com sucesso na porta 9222!
echo Por favor:
echo 1. Nao feche esta janela do Chrome que abriu agora.
echo 2. Faca login na Shopee e no WhatsApp nela.
echo 3. Agora voce pode rodar o seu script de Python.
echo ========================================================
pause
