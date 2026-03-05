import time
import os
import pyperclip
import win32clipboard
from io import BytesIO
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains

# --- FUNÇÃO PARA COPIAR IMAGEM PARA O CLIPBOARD ---
def enviar_imagem_ao_clipboard(caminho_imagem):
    image = Image.open(caminho_imagem)
    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()

def enviar_oferta_metodo_cola(nome_do_grupo, texto, caminho_foto):
    options = webdriver.ChromeOptions()
    options.add_argument(r"user-data-dir=C:\Users\Camim\AppData\Local\Google\Chrome\User Data\Default") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get("https://web.whatsapp.com")
    wait = WebDriverWait(driver, 50)
    
    try:
        # 1. ENTRAR NO GRUPO (mesmo código de antes)
        search_box = wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')))
        search_box.click()
        search_box.send_keys(nome_do_grupo)
        time.sleep(2)
        search_box.send_keys(Keys.ENTER)
        time.sleep(2)

        # 2. COPIAR E COLAR A IMAGEM NA CONVERSA
        print("| 📋 Copiando imagem...")
        enviar_imagem_ao_clipboard(caminho_foto)
        
        chat_box = wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')))
        chat_box.click()
        time.sleep(1)
        
        print("| 📥 Colando imagem (Ctrl+V)...")
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

        # 3. O SEGREDO: ESPERAR O CAMPO DE LEGENDA APARECER
        print("| ⏳ Aguardando editor de legenda...")
        # O WhatsApp usa um 'aria-label' específico para esse campo na tela de prévia
        xpath_legenda = '//div[@aria-label="Adicionar legenda"] | //div[@contenteditable="true"]//p'
        
        # Esperamos até que o campo de legenda esteja visível
        legenda_box = wait.until(EC.visibility_of_element_located((By.XPATH, xpath_legenda)))
        
        # 4. CLICAR E COLAR O TEXTO NA LEGENDA
        print("| ✍️ Colando o texto na legenda...")
        # Usamos JS para garantir o foco e evitar o erro de 'element click intercepted'
        driver.execute_script("arguments[0].focus();", legenda_box)
        driver.execute_script("arguments[0].click();", legenda_box)
        time.sleep(1)
        
        pyperclip.copy(texto)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        
        # Espera um pouco para o link ser processado (gerar prévia se houver)
        time.sleep(2)

        # 5. ENVIO FINAL (ENTER)
        print("| 🚀 Enviando oferta completa!")
        ActionChains(driver).send_keys(Keys.ENTER).perform()

        print("| ✅ AGORA FOI! Verifique o WhatsApp.")

    except Exception as e:
        print(f"| ❌ Falha no envio: {e}")
    
    finally:
        time.sleep(5)
        driver.quit()

# --- ABAIXO É O QUE ESTAVA FALTANDO: A CHAMADA DO SCRIPT! ---

if __name__ == "__main__":
    # 1. Defina o nome do grupo igualzinho está no seu WhatsApp
    meu_grupo = "Instagram @celle.tech" 
    
    # 2. Defina o texto da oferta (com a formatação do Whats)
    texto_oferta = (
        "*OFERTA EXCLUSIVA* 🤖🔥\n\n"
        "Produto Incrível para o seu setup!\n"
        "De: ~R$ 250,00~\n"
        "Por: *R$ 189,90*\n\n"
        "🛒 Link: https://amzn.to/3xyz123"
    )
    
    # 3. O nome do arquivo de imagem que deve estar na mesma pasta
    arquivo_foto = "produto.jpg" 

    # Chama a função
    enviar_oferta_metodo_cola(meu_grupo, texto_oferta, arquivo_foto)