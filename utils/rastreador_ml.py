import time
import pyperclip
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

def iniciar_driver():
    options = webdriver.ChromeOptions()
    options.add_argument(r"--user-data-dir=C:\Users\Camim\whatsapp_selenium_profile")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def capturar_link_ml(driver):
    print("--- RASTREADOR MERCADO LIVRE ---")
    driver.get("https://www.mercadolivre.com.br/afiliados/hub") 
    
    print("| Aguardando carregamento...")
    time.sleep(5) 

    # 1. PEGAR OS CARDS (Baseado no seu HTML)
    # A classe que você mandou: andes-card poly-card...
    cards = driver.find_elements(By.CSS_SELECTOR, ".poly-card")
    
    if not cards:
        print("| ❌ Nenhum card encontrado. O login funcionou?")
        return

    print(f"| Encontrados {len(cards)} produtos. Testando o primeiro...")
    card = cards[0]
    
    try:
        # Rola até o card
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
        time.sleep(1)

        # Pega Título
        titulo = card.find_element(By.CSS_SELECTOR, "a.poly-component__title").text
        print(f"| Produto: {titulo}")
        
        # Pega Preço (Seletor ajustado pelo seu HTML)
        try:
            preco_fraction = card.find_element(By.CSS_SELECTOR, ".andes-money-amount__fraction").text
            print(f"| Preço: R$ {preco_fraction}")
        except: pass

        # 2. CLICAR EM COMPARTILHAR
        # O botão está dentro de uma div com data-testid="form-action"
        print("| Clicando em Compartilhar...")
        botao_share = card.find_element(By.XPATH, ".//button//span[contains(text(), 'Compartilhar')]")
        driver.execute_script("arguments[0].click();", botao_share)
        
        # 3. CLICAR EM COPIAR LINK (No Pop-up)
        print("| Aguardando pop-up...")
        try:
            # Procura pelo texto "Copiar link" ou "Copiar"
            botao_copiar = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Copiar link')] | //div[contains(text(), 'Copiar link')]"))
            )
            botao_copiar.click()
            print("| Botão 'Copiar link' clicado!")
            
            # 4. CAPTURAR O CLIPBOARD
            time.sleep(1.5) # Tempo para o Windows processar
            link_final = pyperclip.paste()
            
            if "mercadolivre" in link_final or "ml.com" in link_final:
                print(f"| 🚀 SUCESSO! Link: {link_final}")
            else:
                print(f"| ⚠️ O que veio não parece link: {link_final}")
                
            # Fecha pop-up com ESC
            webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            
        except Exception as e:
            print(f"| ❌ Falha no Pop-up: {e}")
            driver.save_screenshot("ERRO_ML_POPUP.png")

    except Exception as e:
        print(f"| ❌ Erro no Card: {e}")
        driver.save_screenshot("ERRO_ML_CARD.png")

if __name__ == "__main__":
    driver = iniciar_driver()
    capturar_link_ml(driver)
    input("Pressione ENTER para sair...")
    driver.quit()