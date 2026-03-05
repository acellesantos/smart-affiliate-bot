import sys
import os
import time
import re
import requests
import json
import pyperclip
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import win32clipboard
from PIL import Image

# --- CONFIGURAÇÕES ---
ARQUIVO_LINKS = "links.txt"
ARQUIVO_CACHE_ENVIOS = "cache_envios_24h.json"

GRUPOS_ALVO = [
   # "Achadinhos da Celle • AI", 
     "Instagram @celle.tech",
]

# --- CACHE 24H ---

def carregar_cache():
    if not os.path.exists(ARQUIVO_CACHE_ENVIOS): return {}
    try:
        with open(ARQUIVO_CACHE_ENVIOS, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

def salvar_cache(cache):
    try:
        with open(ARQUIVO_CACHE_ENVIOS, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=4, ensure_ascii=False)
    except: pass

def verificar_se_ja_enviou_24h(titulo):
    if not titulo: return False
    chave = titulo.strip().lower()
    cache = carregar_cache()
    if chave in cache:
        if (time.time() - cache[chave]) < 86400:
            return True
        else:
            del cache[chave]
            salvar_cache(cache)
    return False

def registrar_envio_24h(titulo):
    if not titulo: return
    chave = titulo.strip().lower()
    cache = carregar_cache()
    cache[chave] = time.time()
    salvar_cache(cache)

# --- UTILITÁRIOS ---

def iniciar_driver():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ Conectado ao Chrome (Modo Anti-Bot)!")
        return driver
    except:
        print("⚠️ Chrome fechado. Abrindo nova janela...")
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

def baixar_imagem(url):
    try:
        if not url: return None
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code == 200:
            caminho = os.path.abspath("temp_img.jpg")
            with open(caminho, 'wb') as f:
                f.write(res.content)
            return caminho
    except: pass
    return None

def copiar_imagem_clipboard(caminho):
    image = Image.open(caminho)
    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()

def formatar_preco_br(texto):
    if not texto: return "0,00"
    try:
        if isinstance(texto, (float, int)):
             return f"{texto:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        nums = re.findall(r'\d+[,.]\d+', texto)
        if nums: return nums[0]
        return texto
    except: return "0,00"

# --- ENVIO WHATSAPP (VERSÃO 4 - CURSOR INTELIGENTE) ---

def enviar_whatsapp(driver, grupo, msg, img_path):
    print(f"| 🟢 WhatsApp: Enviando para '{grupo}'...")
    wait = WebDriverWait(driver, 30)
    
    # 1. Foca na aba
    try:
        for h in driver.window_handles:
            driver.switch_to.window(h)
            if "WhatsApp" in driver.title: break
    except: pass

    # 2. Limpa interface (fecha modais anteriores)
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.5)

    try:
        # 3. Busca o Grupo
        box_busca = wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')))
        box_busca.click()
        driver.execute_script("arguments[0].innerText = '';", box_busca) # Limpa via JS
        box_busca.send_keys(Keys.CONTROL + "a"); box_busca.send_keys(Keys.BACKSPACE)
        
        box_busca.send_keys(grupo)
        time.sleep(1.5)
        box_busca.send_keys(Keys.ENTER)
        time.sleep(1)

        # 4. Cola Imagem
        if img_path:
            copiar_imagem_clipboard(img_path)
            
            # Garante foco no chat
            try:
                driver.find_element(By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]').click()
            except: pass
            
            time.sleep(0.5)
            ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            
            print("| ⏳ Aguardando editor de imagem...")
            time.sleep(2.5) # Tempo crucial para a imagem carregar e o cursor focar
            
            # --- ESTRATÉGIA V4: Foco no Elemento Ativo ---
            # Ao colar a imagem, o WhatsApp foca automaticamente na legenda.
            # Não vamos tentar achar o elemento pelo nome, vamos usar o cursor onde ele estiver.
            
            # Prepara texto
            msg_whats = msg.replace("<b>", "*").replace("</b>", "*").replace("<s>", "~").replace("</s>", "~")
            msg_whats = re.sub(r'<a href=.*?>.*?</a>', '', msg_whats).strip()
            pyperclip.copy(msg_whats)
            
            try:
                # Tenta achar a caixa explicitamente primeiro (rápido)
                box_legenda = driver.find_element(By.XPATH, '//div[@aria-label="Adicionar legenda"] | //div[@contenteditable="true"][@data-tab="10"] | //span[text()="Adicionar legenda"]/../following-sibling::div//div[@contenteditable="true"]')
                box_legenda.click()
            except:
                # SE FALHAR, APERTA TAB PARA TENTAR FOCAR
                print("| ⚠️ Caixa não achada pelo nome. Tentando focar via TAB...")
                ActionChains(driver).send_keys(Keys.TAB).perform()
                time.sleep(0.5)
            
            # COLA O TEXTO (No elemento que estiver ativo)
            print("| 📝 Colando legenda no cursor ativo...")
            ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            time.sleep(1)
            
            # ENVIAR (ENTER)
            print("| 🚀 Enviando (Enter)...")
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            
            # Se Enter não foi, tenta clicar no botão verde
            try:
                time.sleep(1)
                botoes_enviar = driver.find_elements(By.XPATH, '//span[@data-icon="send"]')
                if botoes_enviar:
                    driver.execute_script("arguments[0].click();", botoes_enviar[-1])
            except: pass
            
            print("| ✅ Processo concluído!")
            time.sleep(4) # Tempo para upload

    except Exception as e:
        print(f"| ❌ Erro WhatsApp: {e}")
        try: ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except: pass

# --- EXTRATORES ---

def extrair_dados_ml(driver):
    try: titulo = driver.find_element(By.CSS_SELECTOR, "h1.ui-pdp-title").text.strip()
    except: titulo = "Produto Mercado Livre"
    preco_atual = "0,00"; preco_antigo = None
    try:
        container = driver.find_element(By.CSS_SELECTOR, ".ui-pdp-price__second-line")
        elem_frac = container.find_element(By.CSS_SELECTOR, ".andes-money-amount__fraction")
        preco_atual = elem_frac.text.replace('.', '') 
    except: 
        try:
             el = driver.find_element(By.CSS_SELECTOR, ".andes-money-amount__fraction")
             preco_atual = el.text.replace('.', '')
        except: pass
    try:
        elem_antigo = driver.find_element(By.CSS_SELECTOR, ".ui-pdp-price__original-value .andes-money-amount__fraction")
        preco_antigo = elem_antigo.text.replace('.', '')
    except: pass
    img_url = None
    try:
        img = driver.find_element(By.CSS_SELECTOR, "figure.ui-pdp-gallery__figure img")
        img_url = img.get_attribute("src")
    except:
        try:
            imgs = driver.find_elements(By.TAG_NAME, "img")
            for i in imgs:
                if "http" in i.get_attribute("src") and int(i.get_attribute("width") or 0) > 300:
                    img_url = i.get_attribute("src"); break
        except: pass
    return titulo, formatar_preco_br(float(preco_atual)) if preco_atual != "0,00" else "0,00", formatar_preco_br(float(preco_antigo)) if preco_antigo else None, img_url

def extrair_dados_universal(driver, url):
    driver.get(url)
    time.sleep(4)
    if "mercadolivre.com" in url or "produto.mercadolivre" in url: return extrair_dados_ml(driver)
    titulo = "Oferta"; preco = "Confira"; img_url = None; preco_antigo = None
    try:
        for sel in ["h1", "#productTitle", ".ui-pdp-title", ".vR6K3w", ".shopee-product-info__header__title"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if len(el.text) > 5: titulo = el.text.strip(); break
            except: pass
        for sel in [".a-price .a-offscreen", ".pqTWkA", ".IZPeQz", '[data-testid="price-value"]']:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                txt = el.get_attribute("innerText") or el.text
                if re.search(r'\d', txt): preco = txt.strip(); break
            except: pass
        imgs = driver.find_elements(By.TAG_NAME, "img")
        for i in imgs:
            src = i.get_attribute("src")
            w = int(i.get_attribute("width") or 0)
            if src and "http" in src and w > 300: img_url = src; break
    except Exception as e: print(f"| ⚠️ Erro extração: {e}")
    return titulo, preco, preco_antigo, img_url

# --- MAIN ---

def main():
    print("\n=== 🕵️ ROBÔ MANUAL V4 (CURSOR ATIVO) ===")
    filtro_loja = None
    if len(sys.argv) > 1:
        filtro_loja = sys.argv[1].upper()
        print(f"| 🎯 FILTRO: '{filtro_loja}'")

    if not os.path.exists(ARQUIVO_LINKS): print(f"| ❌ {ARQUIVO_LINKS} não encontrado."); return
    driver = iniciar_driver()
    aba_inicial = driver.current_window_handle
    
    with open(ARQUIVO_LINKS, "r", encoding="utf-8") as f: linhas = f.readlines()
    
    for linha in linhas:
        if not linha.strip() or linha.startswith("#"): continue
        partes = linha.split("|")
        url_produto = partes[0].strip()
        url_afiliado = partes[1].strip() if len(partes) > 1 else url_produto
        
        if filtro_loja:
            if filtro_loja == "SHOPEE" and "shope" not in url_produto: continue
            if filtro_loja == "AMAZON" and "amazon" not in url_produto: continue
            if filtro_loja == "MAGALU" and "magazine" not in url_produto: continue
            if filtro_loja == "ML" and "mercado" not in url_produto: continue

        print(f"\n| 🔄 Processando: {url_produto[:40]}...")
        try: driver.switch_to.window(aba_inicial)
        except: pass
        
        titulo, preco, preco_antigo, img_url = extrair_dados_universal(driver, url_produto)
        if verificar_se_ja_enviou_24h(titulo): print(f"| ⏳ Já enviado hoje. Pulando."); continue
        if not img_url: print("| ❌ Imagem não encontrada."); continue
            
        print(f"| 🏷️  {titulo[:30]}... | 💰 {preco}")
        emoji = "🔥"
        if "shope" in url_produto: emoji = "🟠"
        elif "amazon" in url_produto: emoji = "📦"
        elif "magazine" in url_produto: emoji = "💙"
        elif "mercado" in url_produto: emoji = "🤝"
        
        bloco_preco = f"✅ <b>Apenas: R$ {preco}</b>"
        if preco_antigo: bloco_preco = f"❌ <s>De: R$ {preco_antigo}</s>\n✅ <b>Por: R$ {preco}</b> 📉"

        msg = (f"{emoji} <b>ACHADINHO!</b>\n\n📦 {titulo}\n\n{bloco_preco}\n\n🛒 <b>COMPRE AQUI:</b> 👇\n{url_afiliado}")
        path_img = baixar_imagem(img_url)
        sucesso = False
        for grupo in GRUPOS_ALVO:
            enviar_whatsapp(driver, grupo, msg, path_img)
            sucesso = True
        
        if sucesso: registrar_envio_24h(titulo)
        if path_img: os.remove(path_img)
        time.sleep(2) 

    print(f"\n| ✅ FIM DA LISTA.")

if __name__ == "__main__":
    main()