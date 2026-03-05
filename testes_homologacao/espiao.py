import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def espiao_local():
    # 1. Pega a pasta ONDE ESTAMOS AGORA (A mesma do seu robô)
    pasta_atual = os.getcwd()
    nome_arquivo = os.path.join(pasta_atual, "CODIGO_SECRETO.txt")

    # Configurações do navegador
    options = webdriver.ChromeOptions()
    options.add_argument(r"--user-data-dir=C:\Users\Camim\whatsapp_selenium_profile")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")

    print(f"🕵️ INICIANDO ESPIÃO LOCAL...")
    print(f"📂 O arquivo será salvo AQUI: {nome_arquivo}")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://www.magazinevoce.com.br/magazinecelle/")
        
        print("\n" + "="*50)
        print("1. Vá no navegador e CLIQUE num produto (com estrelas!).")
        print("2. Espere carregar.")
        print("3. VOLTE AQUI e aperte ENTER.")
        print("="*50)
        
        input("👉 Aperte ENTER aqui quando estiver pronto...")

        # Captura e Salva
        with open(nome_arquivo, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
            
        print(f"\n✅ SUCESSO!")
        print(f"O arquivo 'CODIGO_SECRETO.txt' apareceu na mesma pasta do seu robô.")
        print(f"Caminho: {pasta_atual}")

    except Exception as e:
        print(f"❌ Erro: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    espiao_local()