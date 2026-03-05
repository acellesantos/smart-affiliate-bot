from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time

# 1. CONFIGURA O PERFIL (O MESMO DO SEU ROBÔ)
print("--- ESPIÃO DA AMAZON INICIADO ---")
print("Certifique-se que o outro robô e o Chrome estão FECHADOS.")

options = webdriver.ChromeOptions()
# Caminho exato do seu perfil
options.add_argument(r"--user-data-dir=C:\Users\Camim\whatsapp_selenium_profile")
options.add_argument("--profile-directory=Default")
options.add_argument("--start-maximized")

# Inicia o navegador
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    # 2. ENTRA EM UM PRODUTO QUALQUER
    url_teste = "https://www.amazon.com.br/Mouse-Nanoreceptor-Inclusa-Logitech-Mouses/dp/B074L9L5KZ/?_encoding=UTF8&pd_rd_w=eGIU0&content-id=amzn1.sym.812ea633-abc7-4b1d-b3cf-adb0fac8c69c%3Aamzn1.symc.5a16118f-86f0-44cd-8e3e-6c5f82df43d0&pf_rd_p=812ea633-abc7-4b1d-b3cf-adb0fac8c69c&pf_rd_r=CAK2CQNV8WVJ9ER7W5QG&pd_rd_wg=Df3P6&pd_rd_r=634109c6-7e92-4702-96f5-19acf43e1c5f&ref_=pd_hp_d_atf_ci_mcx_mr_ca_hp_atf_d&th=1" # Echo Dot (Produto comum)
    print(f"Acessando produto teste: {url_teste}")
    driver.get(url_teste)

    print("⏳ Aguardando 10 segundos para carregamento total...")
    time.sleep(10)

    # 3. O RAIO-X DO SITESTRIPE
    print("\n--- 🔍 RESULTADOS DA INVESTIGAÇÃO ---")
    
    # Verifica se a barra principal existe
    barra = driver.find_elements(By.ID, "amzn-ss-text-link-span")
    if barra:
        print("✅ ACHEI! O container principal '#amzn-ss-text-link-span' EXISTE na página.")
        print(f"   Visível? {barra[0].is_displayed()}")
        print(f"   Tamanho: {barra[0].size}")
    else:
        print("❌ O container '#amzn-ss-text-link-span' NÃO foi encontrado.")

    # Procura TODOS os links dentro da barra de ferramentas
    print("\n--- 📋 LISTANDO ELEMENTOS DA BARRA ---")
    # Tenta pegar qualquer coisa dentro da div do SiteStripe
    elementos = driver.find_elements(By.CSS_SELECTOR, "#amzn-acp-text-link span, #amzn-ss-text-link-span a")
    
    if not elementos:
        print("Nenhum elemento específico encontrado. Tentando busca ampla...")
        # Busca ampla por qualquer link que tenha 'Texto' escrito
        elementos = driver.find_elements(By.XPATH, "//a[contains(text(), 'Texto')]")

    for i, elem in enumerate(elementos):
        try:
            print(f"\nITEM #{i+1}:")
            print(f"   Texto: '{elem.text}'")
            print(f"   Tag: <{elem.tag_name}>")
            print(f"   ID: '{elem.get_attribute('id')}'")
            print(f"   Class: '{elem.get_attribute('class')}'")
            print(f"   Href: '{elem.get_attribute('href')}'")
            print(f"   Está visível? {elem.is_displayed()}")
        except:
            print("   (Elemento mudou enquanto eu lia)")

    # 4. TIRA A PROVA REAL (PRINT)
    print("\n📸 Tirando foto do que o robô está vendo...")
    driver.save_screenshot("FOTO_ESPIAO.png")
    print("Foto salva como 'FOTO_ESPIAO.png'. Veja se a barra cinza aparece nela!")

except Exception as e:
    print(f"ERRO NO ESPIÃO: {e}")

finally:
    print("\n--- FIM DA ESPIONAGEM ---")
    print("Pressione ENTER para fechar o navegador...")
    input()
    driver.quit()