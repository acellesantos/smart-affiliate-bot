import time
import os
import traceback
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def abrir_para_login():
    print("\n" + "="*50)
    print("🚀 ABRINDO CHROME PORTÁTIL PARA LOGIN")
    print("="*50)
    
    # 1. PEGA O CAMINHO DA PASTA ATUAL (ONEDRIVE)
    # Isso faz o script funcionar em qualquer PC sem você precisar mudar o nome do usuário!
    diretorio_projeto = os.path.dirname(os.path.abspath(__file__))
    
    # 2. DEFINE OS CAMINHOS USANDO A SUA ESTRUTURA DE PASTAS
    caminho_chrome = os.path.join(diretorio_projeto, "chrome-win64", "chrome.exe")
    caminho_perfil = os.path.join(diretorio_projeto, "ChromeProfile")

    print(f"| 📂 Pasta do Projeto: {diretorio_projeto}")
    print(f"| 🌐 Usando Chrome em: {caminho_chrome}")
    print(f"| 👤 Usando Perfil em: {caminho_perfil}")

    # Tenta fechar processos que travam o perfil
    print("| 🛠️ Limpando processos antigos...")
    os.system("taskkill /f /im chrome.exe >nul 2>&1")
    os.system("taskkill /f /im chromedriver.exe >nul 2>&1")
    time.sleep(2)

    options = webdriver.ChromeOptions()
    
    # AQUI ESTÁ O PULO DO GATO:
    options.binary_location = caminho_chrome  # Força o Selenium a usar o SEU Chrome portátil
    options.add_argument(f"--user-data-dir={caminho_perfil}") # Usa a pasta ChromeProfile do OneDrive
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    options.add_argument("--remote-debugging-port=9222") # Deixa a porta pronta para o robô depois

    try:
        print("| ⏳ Iniciando navegador... (Aguarde a barra de automação)")
        
        # O Service agora vai baixar o driver compatível com a sua versão do Chrome portátil
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        driver.get("https://web.whatsapp.com")
        
        print("\n" + "!"*40)
        print("💡 NAVEGADOR PRONTO!")
        print("1. Faça login no WhatsApp e Shopee.")
        print("2. Quando terminar, FECHE O NAVEGADOR NO X.")
        print("!"*40 + "\n")
        
        while True:
            try:
                _ = driver.window_handles
                time.sleep(2)
            except:
                print("\n✅ Janela fechada! Logins salvos.")
                break
                
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO:")
        print("-" * 30)
        traceback.print_exc()
        print("-" * 30)
        input("\nAperte ENTER para sair...")

if __name__ == "__main__":
    abrir_para_login()