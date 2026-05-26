import sys
import os
import re
import time
import random
import io
import requests
import json
import urllib.parse
import pyperclip
import pandas as pd
import win32clipboard
from datetime import datetime
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURAÇÕES INICIAIS ---
load_dotenv()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except: pass

SIMULAR_DIGITACAO = True
DELAY_MIN_ENTRE_MENSAGENS = 5
DELAY_MAX_ENTRE_MENSAGENS = 15
ARQUIVO_HISTORICO = os.getenv("ARQUIVO_HISTORICO", "historico_ofertas.csv")
# Arquivo de cache de envios (agora por default 5 dias)
ARQUIVO_CACHE_ENVIOS = os.getenv("ARQUIVO_CACHE_ENVIOS", "cache_envios_5dias.json")
# Retenção do cache em segundos (default = 5 dias = 120 horas = 432000s)
CACHE_RETENCAO_SECONDS = int(os.getenv("CACHE_RETENCAO_SECONDS", "432000"))
WA_CLICK_TIMEOUT = int(os.getenv("WA_CLICK_TIMEOUT", "12"))
# CAMPANHA SAZONAL (mudar para ativar prioridade de palavras-chave em campanhas)
CAMPANHA_SAZONAL = os.getenv("CAMPANHA_SAZONAL", "NENHUM")

# Dicionário simples de palavras-chave prioritárias por campanha
CAMPANHAS_PRIORIDADE = {
    "COPA": ["camisa", "tv", "projetor", "bandeira", "camiseta"],
    "NAMORADOS": ["perfume", "anel", "joia", "colar", "rosa"],
    "NENHUM": []
}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GRUPOS_ALVO = [
    "Achadinhos da Celle • AI",       # 👈 O bot vai tratar como o seu GRUPO comum de testes
    "[CANAL] Achadinhos da Celle • AI" # 👈 O bot vai saber que este é o CANAL oficial!
]

AWIN_AFFILIATE_ID = os.getenv("AWIN_AFFILIATE_ID", "SEU_ID_AWIN_AQUI")
AWIN_MID_KABUM = "17629"       # Confirme esse número no seu painel Awin
AWIN_MID_ALIEXPRESS = "18879"  # Confirme esse número no seu painel Awin

# VALIDAÇÃO DE SEGURANÇA: Avisa no terminal se o .env falhar
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "None":
    print("| ⚠️ ALERTA: 'TELEGRAM_BOT_TOKEN' não foi encontrado no seu arquivo .env!")
    print("| Verifique se o arquivo .env está na mesma pasta do script principal.")

if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "None":
    print("| ⚠️ ALERTA: 'TELEGRAM_CHAT_ID' não foi encontrado no seu arquivo .env!")


def enviar_mensagem_telegram_seguro(texto):
    """Envia mensagem ao Telegram lendo as credenciais do .env com tratamento de erros."""
    # Se não houver token, sai da função sem tentar fazer o request (evita o erro 404)
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "None":
        print("[TELEGRAM] Envio cancelado: Token ausente no ambiente.")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": texto,
            "parse_mode": "HTML"  # Permite formatação estilizada se necessário
        }

        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("[TELEGRAM] Mensagem enviada com sucesso!")
            return True
        else:
            print(f"[TELEGRAM] Erro na API do Telegram: {r.text}")
            return False
            
    except Exception as e:
        # Se a internet cair ou o Telegram falhar, o WhatsApp NÃO trava
        print(f"[TELEGRAM] Falha de conexão isolada (Fluxo mantido): {e}")
        return False

def enviar_canal_exclusivo(driver, nome_canal, mensagem, caminho_foto=None):
    try:
        print(f"\n📢 [FLUXO CANAL] Iniciando envio para: {nome_canal}")
        
        # 1. Clica no botão da aba 'Canais' (Atualizações)
        xpath_botao_canais = (
            '//*[local-name()="title" and contains(text(), "wds-ic-channels")]/ancestor::button | '
            '//*[local-name()="title" and contains(text(), "wds-ic-channels")]/ancestor::span | '
            '//button[@aria-label="Canais"] | //button[@title="Canais"] | '
            '//span[@data-icon="status-v3"]'
        )
        
        botao_canais = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, xpath_botao_canais))
        )
        botao_canais.click()
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", botao_canais)
        
        print("| ✅ Mudou de fato para a aba Canais.")
        time.sleep(3.5)
        
        # 2. Localiza a caixa de pesquisa na aba Canais
        xpath_pesquisa_canal = '//input[@role="textbox"][@aria-label="Pesquisar ou começar uma nova conversa"] | //input[@data-tab="3"]'
        caixa_pesquisa = WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.XPATH, xpath_pesquisa_canal))
        )
        caixa_pesquisa.click()
        time.sleep(0.5)
        caixa_pesquisa.send_keys(Keys.CONTROL + "a")
        caixa_pesquisa.send_keys(Keys.BACKSPACE)
        caixa_pesquisa.send_keys(nome_canal)
        print(f"| ✍️ Digitado na pesquisa de canais: '{nome_canal}'")
        time.sleep(2.5) # Um tiquinho a mais de tempo para o WhatsApp filtrar o canal na tela
        
        # 🎯 NOVA LÓGICA: ENTER + CLIQUE DE GARANTIA PARA ABRIR O CANAL
        # 🎯 NOVA LÓGICA ULTRA-ROBUSTA (Baseada no F12 real)
        try:
            caixa_pesquisa.send_keys(Keys.ENTER)
            print("| ⌨️ Pressionado ENTER para abrir o canal.")
            time.sleep(2)
            
            # Seletor baseado no HTML extraído: busca o frame do título que contém o texto limpo
            xpath_canal_f12 = '//div[@data-testid="cell-frame-title"]//span[contains(text(), "Achadinhos da Celle")]'
            
            # Procura o elemento e sobe até o botão clicável da lista
            alvo_canal = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xpath_canal_f12))
            )
            
            # Força o clique diretamente no contêiner usando JavaScript para não ter erro
            driver.execute_script("arguments[0].click();", alvo_canal)
            print("| 🖱️ Clique cirúrgico (F12) executado no canal!")
            
        except Exception as e_abrir:
            print(f"| ⚠️ O seletor F12 falhou, tentando clique genérico no primeiro item da lista: {e_abrir}")
            try:
                # Se falhar, clica no primeiro item de lista genérico que estiver na tela
                driver.execute_script("document.querySelector('div[role=\"listitem\"]').click();")
                print("| 🛡️ Contingência: Canal aberto via seletor de lista genérico.")
            except Exception as e_critico:
                print(f"| ❌ Falha crítica ao tentar abrir o canal: {e_critico}")
        
        time.sleep(4) # Tempo generoso para carregar o chat no meio da tela
        
        # 🎯 AJUSTE DE SELETOR: Garante o clique no campo de texto do Canal antes de colar
        xpath_texto_canal = (
            '//footer//div[@contenteditable="true"] | '
            '//div[@id="main"]//div[@contenteditable="true"] | '
            '//div[contains(@class, "lexical-rich-text-input")]//div[@contenteditable="true"]'
        )
        
        # 3. Envio de Mídia com Imagem e Legenda Juntas
        if caminho_foto and os.path.exists(caminho_foto):
            print("| 📸 Preparando imagem e copiando para a Área de Transferência...")
            copiar_imagem_para_clipboard(caminho_foto)
            
            campo_texto = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, xpath_texto_canal))
            )
            campo_texto.click()
            time.sleep(1.5)
            
            # Executa o Colar físico (Ctrl + V)
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys("v").key_up(Keys.CONTROL).perform()
            print("| ⏳ Aguardando tela de prévia de mídia do WhatsApp...")
            time.sleep(5) 
            
            msg_final_whats = formatar_para_whatsapp(mensagem)
            
            try:
                # Foca no campo de legenda da janela preta de mídias
                xpath_legenda = '//div[@role="textbox"][@data-tab="10"] | //div[contains(@class, "lexical-rich-text-input")]//div[@contenteditable="true"]'
                campo_legenda = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, xpath_legenda))
                )
                
                driver.execute_script("arguments[0].focus();", campo_legenda)
                time.sleep(0.5)
                simular_digitacao(driver, campo_legenda, msg_final_whats)
                time.sleep(1.5)
                
                # Clica no botão verde de Enviar da prévia de mídias
                xpath_botao_enviar_midia = '//span[@data-icon="send"] /ancestor::div[@role="button"] | //div[@aria-label="Enviar"] | //span[@data-icon="send"]'
                botao_enviar = WebDriverWait(driver, 8).until(
                    EC.presence_of_element_located((By.XPATH, xpath_botao_enviar_midia))
                )
                driver.execute_script("arguments[0].click();", botao_enviar)
                print("| 🚀 Sucesso absoluto! Imagem com legenda postadas juntas no Canal!")
                
            except Exception as e_midia:
                print(f"| ⚠️ Falha na prévia de mídia: {e_midia}. Forçando Enter global...")
                actions_texto = ActionChains(driver)
                actions_texto.send_keys(Keys.ENTER).perform()
            
            time.sleep(3)
            
        else:
            # Caso não vá imagem, envia o texto puro direto
            campo_texto = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, xpath_texto_canal))
            )
            campo_texto.click()
            msg_final_whats = formatar_para_whatsapp(mensagem)
            simular_digitacao(driver, campo_texto, msg_final_whats)
            time.sleep(1)
            campo_texto.send_keys(Keys.ENTER)
            print("| 🚀 Apenas texto enviado ao Canal!")
            time.sleep(2)
            
        # =========================================================================
        # 🎯 RETORNO SEGURO E FORÇADO PARA CONVERSAS (MULTI-XPATHS + JS) 🎯
        # =========================================================================
        print("| 🔄 Finalizando ciclo do canal com sucesso. Retornando para a aba de Conversas...")

        def voltar_para_conversas():
            """Função auxiliar para garantir retorno"""
            try:
                xpath_aba_conversas = (
                    '//*[local-name()="title" and contains(text(), "wds-ic-chat")]/ancestor::button | '
                    '//*[local-name()="title" and contains(text(), "wds-ic-chat")]/ancestor::span | '
                    '//button[@aria-label="Conversas"] | //button[@title="Conversas"] | '
                    '//span[@data-icon="chat-v3"]'
                )

                botao_conversas = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable((By.XPATH, xpath_aba_conversas))
                )
                driver.execute_script("arguments[0].click();", botao_conversas)
                time.sleep(1)
                return True
            except Exception as e:
                print(f"| ⚠️ Tentativa 1 de voltar falhou: {e}")
                try:
                    driver.execute_script("document.querySelector('button[aria-label=\"Conversas\"]')?.click() || document.querySelector('span[data-icon=\"chat-v3\"]')?.closest('button')?.click();")
                    time.sleep(1)
                    return True
                except Exception as e2:
                    print(f"| ⚠️ Tentativa 2 de voltar falhou: {e2}")
                    return False

        if voltar_para_conversas():
            print("| ✅ Voltou com sucesso para a aba de Conversas.")
            time.sleep(2)
        else:
            print("| ⚠️ Não conseguiu voltar, mas o envio foi realizado.")

        # --- NOVA AÇÃO: Aguarda e clica no ícone SVG 'wds-ic-chat' usando XPath exato fornecido ---
        try:
            xpath_svg_chat = "//*[local-name()='svg' and .//*[local-name()='title' and text()='wds-ic-chat']]/.."
            svg_parent = WebDriverWait(driver, WA_CLICK_TIMEOUT).until(
                EC.element_to_be_clickable((By.XPATH, xpath_svg_chat))
            )
            driver.execute_script("arguments[0].click();", svg_parent)
            print("| ✅ Clique no ícone SVG 'wds-ic-chat' realizado com sucesso.")
        except TimeoutException:
            print("| ⚠️ Timeout aguardando o ícone SVG 'wds-ic-chat' — não foi possível clicar.")
        except Exception as e_svg_click:
            print(f"| ⚠️ Erro ao tentar clicar no SVG 'wds-ic-chat': {e_svg_click}")

        return True
        
    except Exception as e:
        print(f"| ❌ Erro no fluxo dedicado do Canal: {e}")
        # 🛡️ PLANO DE CONTINGÊNCIA - SEMPRE TENTAR VOLTAR
        print("| 🛡️ Acionando contingência: Forçando retorno para aba de Conversas...")
        tentativas = 0
        while tentativas < 3:
            tentativas += 1
            try:
                xpath_voltar_chats = (
                    '//*[local-name()="title" and contains(text(), "wds-ic-chat")]/ancestor::button | '
                    '//*[local-name()="title" and contains(text(), "wds-ic-chat")]/ancestor::span | '
                    '//button[@aria-label="Conversas"] | //button[@title="Conversas"] | '
                    '//span[@data-icon="chat-v3"]'
                )
                botao_voltar = driver.find_element(By.XPATH, xpath_voltar_chats)
                driver.execute_script("arguments[0].click();", botao_voltar)
                time.sleep(1.5)
                print(f"| ✅ Retornou para Conversas na tentativa {tentativas}")
                break
            except Exception as e_retry:
                print(f"| ⚠️ Tentativa {tentativas} de retorno falhou: {e_retry}")
                time.sleep(0.5)

        return False
    
# --- UTILITÁRIOS ---

def human_delay(min_s=1, max_s=3):
    """Simula pausas humanas aleatórias."""
    time.sleep(random.uniform(min_s, max_s))

def formatar_para_whatsapp(texto_html):
    """Converte tags HTML/Telegram para Markdown do WhatsApp"""
    if not texto_html: return ""
    mapa_tags = {
        "<b>": "*", "</b>": "*", "<strong>": "*", "</strong>": "*",
        "<i>": "_", "</i>": "_", "<em>": "_", "</em>": "_",
        "<s>": "~", "</s>": "~", "<strike>": "~", "</strike>": "~"
    }
    
    texto_whats = texto_html
    for tag, replacement in mapa_tags.items():
        texto_whats = texto_whats.replace(tag, replacement)
        
    texto_whats = re.sub(r'<a href=[\'"](.*?)[\'"]>(.*?)</a>', r'\1', texto_whats)

    if "http" in texto_whats:
        if not re.search(r'http[s]?://[^\s]+$', texto_whats.strip()):
            partes = texto_whats.split("http")
            if len(partes) > 1:
                link = "http" + partes[-1]
                corpo = "http".join(partes[:-1]).strip()
                texto_whats = f"{corpo}\n\n{link}"
    return texto_whats.strip()

def simular_digitacao(driver, elemento, texto):
    """Simula digitação humana para evitar detecção de bot."""
    if not SIMULAR_DIGITACAO:
        elemento.send_keys(texto)
        return
    human_delay(0.5, 1.5)
    if len(texto) < 20:
        for char in texto:
            elemento.send_keys(char)
            time.sleep(random.uniform(0.05, 0.2))
    else:
        pyperclip.copy(texto)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        human_delay(1, 2)

def baixar_imagem_temporaria(url_imagem, nome_arquivo="temp_oferta.jpg"):
    try:
        resposta = requests.get(url_imagem, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if resposta.status_code == 200:
            with open(nome_arquivo, 'wb') as f:
                f.write(resposta.content)
            return os.path.abspath(nome_arquivo)
    except Exception as e:
        print(f"| ❌ Erro ao baixar imagem: {e}")
    return None

def copiar_imagem_para_clipboard(caminho_imagem):
    image = Image.open(caminho_imagem)
    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()

def extrair_valor_numerico(preco_texto):
    if not preco_texto:
        return None
    try:
        txt = preco_texto.replace('.', '')
        matches = re.findall(r'\d+,\d+', txt)
        if matches: return min([float(m.replace(',', '.')) for m in matches])
        match_simples = re.findall(r'\d+\d*', preco_texto.replace(',', '.'))
        return float(match_simples[0]) if match_simples else None
    except: return None

def formatar_preco_br(preco):
    try:
        return f"R$ {float(preco):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return str(preco)

# --- ANÁLISE DE DADOS E CACHE ---

def carregar_cache():
    if not os.path.exists(ARQUIVO_CACHE_ENVIOS): return {}
    try:
        with open(ARQUIVO_CACHE_ENVIOS, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

def salvar_cache(cache):
    with open(ARQUIVO_CACHE_ENVIOS, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=4, ensure_ascii=False)

def atualizar_historico(arquivo_csv, titulo, preco_coletado):
    if not preco_coletado or preco_coletado <= 0: return
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    nova_linha = pd.DataFrame([{'Data': data_hoje, 'Preco': preco_coletado, 'Produto': titulo}])
    if not os.path.exists(arquivo_csv):
        nova_linha.to_csv(arquivo_csv, index=False)
    else:
        df = pd.read_csv(arquivo_csv)
        if not ((df['Produto'] == titulo) & (df['Data'] == data_hoje)).any():
            pd.concat([df, nova_linha]).to_csv(arquivo_csv, index=False)

# --- CORE DO RASTREADOR (RPA) ---

def iniciar_driver():
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    print("| 🌐 Tentando conectar ao Chrome logado (Porta 9222)...")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        print("| ✅ Conectado com sucesso ao perfil existente!")
        return driver
    except Exception as e:
        print(f"\n| ❌ ERRO AO CONECTAR NA PORTA 9222:")
        print(f"| {e}\n")
        print("| ⚠️ Abrindo navegador NOVO (SEM LOGIN) como plano B...")
        
        options_fallback = Options()
        options_fallback.add_argument("--start-maximized")
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options_fallback)     

def focar_aba_whatsapp(driver):
    print("| 🔍 Procurando aba do WhatsApp...")
    
    # 1. Tenta mapear se ela já está aberta
    for handle in driver.window_handles:
        try:
            driver.switch_to.window(handle)
            time.sleep(0.5)
            if "whatsapp" in driver.title.lower() or "web.whatsapp" in driver.current_url:
                driver.execute_script("window.focus();")
                print("| ✅ WhatsApp encontrado e focado!")
                return handle # 👈 Retorna o ID da aba em vez de True
        except:
            continue
            
    # 2. Se rodar o loop inteiro e não achar, ela mesma abre a aba!
    print("| ⚠️ WhatsApp não detectado. Abrindo nova aba...")
    driver.execute_script("window.open('');") # Abre aba em branco
    driver.switch_to.window(driver.window_handles[-1]) # Vai para a nova aba
    driver.get("https://web.whatsapp.com")
    
    print("| ⏳ Aguardando 15 segundos para o carregamento do WhatsApp Web...")
    time.sleep(15)
    
    return driver.current_window_handle # 👈 Retorna o ID da nova aba aberta

def validar_link_afiliado(url, loja):
    """Verifica se o link contém os IDs de rastreio necessários."""
    if not url: return False
    
    regras = {
        "AMAZON": ["tag=celle-20"],
        "MAGALU": ["magazinevoce.com.br/magazinecelle"],
        "SHOPEE": ["shope.ee", "shopee.com.br/universal-link"],
        "MERCADOLIVRE": ["mercadolivre.com.br/social"]
    }
    
    for tag in regras.get(loja, []):
        if tag in url:
            return True
    return True


def produto_eh_bloqueado(titulo):
    """Verifica se o título contém algum termo da lista de bloqueio.
    
    Usa .lower() blindado para garantir que maiúsculas/minúsculas não quebrem o filtro.
    """
    if not titulo:
        return False
    
    # Garante que o título está em minúsculo para comparar certo
    titulo_produto_minusculo = titulo.lower()
    
    # Verifica se QUALQUER termo bloqueado está dentro do título
    if any(termo.lower() in titulo_produto_minusculo for termo in TERMOS_BLOQUEADOS):
        print(f"❌ Produto bloqueado pelo filtro: {titulo}")
        return True
    
    return False

def gerar_chamada_inteligente(titulo, preco_atual, categoria="", autor=""):
    """Lê o título, o preço e a categoria para criar uma frase de impacto com a persona do Robô da Celle.
    
    Se nenhuma categoria específica for detectada, usa frases genéricas de achadinhos.
    """
    
    # Lista de frases genéricas e dinâmicas para fallback e qualquer tipo de produto
    FRASES_GENERICAS_ACHADINHOS = [
        "🕵️‍♀️ Olha o que eu acabei de garimpar para vocês! ✨",
        "🚨 Alerta de preço baixo na tela! 📉",
        "🤖 Eis que surge mais um super achadinho! 💎",
        "✨ Meus algoritmos acharam esse tesouro escondido! 🔍",
        "🎯 Mais um achadinho imperdível pra vocês! 🔥",
        "💰 Preço que choca POSITIVAMENTE os meus circuitos! 💥",
        "🛍️ Novo ciclo, novos achadinhos! Confirma aí 👇",
        "🤖 Bi-bi-bop! ALERTA DE OFERTA!",
        "🚨 ACHADINHO LIBERADO PELA CELLE!"
    ]
    
    if not titulo:
        return random.choice(FRASES_GENERICAS_ACHADINHOS)
    
    titulo_lower = titulo.lower()
    categoria_upper = categoria.upper() if categoria else ""

    # 1. REGRA DA MATEMÁTICA (Kits e Unidades)
    if any(k in titulo_lower for k in ["unidade", "peça", "pcs", "kit"]):
        match_qtd = re.search(r'(\d+)\s*(unidades?|peças|pcs|kit)', titulo_lower)
        if match_qtd and preco_atual:
            qtd = int(match_qtd.group(1))
            if 1 < qtd <= 100:
                preco_unidade = preco_atual / qtd
                valor_teto = int(preco_unidade) + 1
                if preco_unidade < 15:
                    return random.choice([
                        f"Meus processadores calcularam: menos de {valor_teto} reais cada unidade! 🤖📉",
                        f"A matemática do robô não mente: sai a menos de R$ {valor_teto} cada! 🔥"
                    ])
                else:
                    preco_formatado = f"{preco_unidade:.2f}".replace('.', ',')
                    return random.choice([
                        f"Apenas R$ {preco_formatado} por item no kit! Minha IA pira nesse desconto! 🔥",
                        f"O kit compensa muito: R$ {preco_formatado} cada unidade! 📦"
                    ])

    # 2. SALA VIP: LIVROS E LEITURA 
    if categoria_upper == "LIVROS" or re.search(r'\b(livro|box|edição|capa dura|hq|mangá)\b', titulo_lower):
        texto_autor = f" de {autor}" if autor else ""
        if re.search(r'\b(kindle|ebook)\b', titulo_lower):
            return random.choice([
                f"Leitura digital{texto_autor} direto pro seu Kindle! (Eu, como um ser digital, aprovo) 📚🤖", 
                f"Ebook{texto_autor} em promoção! A Celle mandou avisar pra baixar hoje mesmo! 📖✨"
            ])
        else:
            return random.choice([
                f"Mais um{texto_autor} pra estante! Olha esse desconto que eu minerei pra quem ama ler! 📚☕",
                f"Leitura nova{texto_autor} garantida! Meus algoritmos acharam o menor preço! 🤓🤖"
            ])

    # 3. SALA VIP: BELEZA DIVIDIDA E BLINDADA
    # O uso do \b garante que ele procure a palavra exata, evitando que "natural" ative "natura"
    if re.search(r'\b(perfume|body splash|colônia|fragrância|natura|o boticário)\b', titulo_lower):
        return random.choice([
            "Aquele cheirinho de milhões com preço de centavos! ✨💨",
            "Minha IA detectou: sair de casa cheirosa agora custa bem menos! 🥰"
        ])

    elif re.search(r'\b(aparador|barbear|máquina de cortar|oneblade)\b', titulo_lower):
        return random.choice([
            "Visual na régua e praticidade garantida com esse achadinho do robô! ✨💈",
        ])

    elif re.search(r'\b(maquiagem|base|corretivo|batom|rímel|blush)\b', titulo_lower):
        # A Blindagem master ATUALIZADA: Ignora se for base de eletrodoméstico/móvel
        falsos_positivos = [
            "suporte", "geladeira", "fogão", "máquina", "lavar", "cama", "tv", 
            "monitor", "notebook", "mesa", "cooler", "louça", "banho", "tinta", 
            "parede", "chaleira", "elétrica", "eletrica", "giratória", "giratoria", 
            "jarra", "liquidificador", "ventilador", "cabo", "motor"
        ]
        if not any(proibido in titulo_lower for proibido in falsos_positivos):
            return random.choice([
                "Make de milhões com precinho de centavos! A Celle pediu pra compartilhar pra ontem! ✨💄",
                "Repondo o estoque de maquiagem com esse achadinho perfeito! 💄🤖"
            ])

    elif re.search(r'\b(esmalte|unha|manicure|acetona)\b', titulo_lower):
        return random.choice(["O kit de sobrevivência de quem ama unhas perfeitas! 💅💸"])

    elif re.search(r'\b(cabelo|capilar|shampoo|condicionador|máscara|widi care|lola|truss)\b', titulo_lower):
        return random.choice(["Tratamento de salão em casa pagando muito pouco! 🧴🔥"])
        
    elif categoria_upper == "BELEZA" or re.search(r'\b(pele|rosto|skincare|protetor|sérum|cerave)\b', titulo_lower):
        # Blindagem contra o spray de azeite! Se tiver palavras de cozinha, pula fora.
        falsos_positivos_pele = ["azeite", "óleo de soja", "cozinha", "temperar", "salada", "churrasco"]
        if not any(proibido in titulo_lower for proibido in falsos_positivos_pele):
            return random.choice([
                "✨ Skincare em dia! Porque até a IA precisa de manutenção na skin, né? 🧴🤖",
                "Sua pele vai ficar perfeita e sem gastar a grana toda! 🌸💸"
            ])

    # 4. HUMOR DA VIDA ADULTA E CASA
    if re.search(r'\b(air fryer|airfryer|fritadeira|spray|borrifador|azeite|óleo)\b', titulo_lower):
        return random.choice([
            "A salvação de quem, assim como eu, não sabe fritar nem um ovo! 🍟🤖",
            "Pra dar aquele toque de chef na cozinha sem fazer bagunça! 🍳✨",
            "O eletro mais amado do Brasil detectado nos meus radares! Pode colocar na bancada! ⚡"
        ])

    if any(term in titulo_lower for term in ["ferro de passar", "vaporizador"]):
        return random.choice(["A inteligência artificial ainda não passa roupa, mas eu garanto o desconto no ferro! 👔💨"])

    if any(term in titulo_lower for term in ["travesseiro", "jogo de cama", "lençol", "edredom"]):
        return random.choice(["O upgrade que o seu sono precisava pra você render mais amanhã! 💤✨"])

    if re.search(r'\b(geladeira|refrigerador)\b', titulo_lower):
        return random.choice(["Vida adulta é eu, um robô, surtar de alegria garimpando desconto pra sua cozinha! 😍🧊"])

    if any(term in titulo_lower for term in ["micro-ondas", "forno elétrico"]):
        return random.choice(["O mestre-cuca das madrugadas tá na promoção! 👨‍🍳🍕"])

    if any(term in titulo_lower for term in ["lavadora", "máquina de lavar", "lava e seca"]):
        return random.choice(["O fim do sofrimento no tanque chegou, e com desconto calculado! 🙌💦"])

    if any(term in titulo_lower for term in ["prateleira", "nicho", "organizador", "sapateira"]):
        return random.choice(["A paz de espírito de ver tudo organizado! Meus bytes até suspiram... 🙌📦"])

    # 5. CONSOLES E GAMES PREMIUM (Com Toque Pessoal)
    if any(term in titulo_lower for term in ["playstation", "ps5", "ps4", "xbox", "nintendo switch", "console", "dualsense"]):
        return random.choice([
            "Setup de respeito montado! Agora a única desculpa pra perder é a falta de habilidade mesmo. 🎮😅✨", 
            "Conforto imbatível pra não colocar a culpa do lag em mim! 🛋️🎮",
            "Setup de respeito pra não ter desculpa quando perder na gameplay! 🎮✨"
        ])

    # 6. REGRA GAMER E HOME OFFICE (Foco na profissão)
    if re.search(r'\b(gamer|rtx|gtx|pc|placa de vídeo)\b', titulo_lower):
        if re.search(r'\b(cadeira|mesa|microfone|led|suporte|mousepad)\b', titulo_lower):
            return random.choice(["Pra focar no trabalho (ou na gameplay) com conforto total! 🎮💻"])
        elif re.search(r'\b(rtx|gtx|ssd|ram|processador)\b', titulo_lower):
            return random.choice(["Pra rodar tudo no ultra e deixar meus circuitos com inveja! 🚀🤖"])
        
    if any(term in titulo_lower for term in ["smartwatch", "smartband", "mi band", "apple watch"]):
        return random.choice(["O companheiro perfeito pra sua rotina! Tecnologia pura no pulso! ⌚⚡"])

    elif any(term in titulo_lower for term in ["fone", "earbuds", "headphone", "headset", "caixa de som"]):
        return random.choice(["Aumenta o som e ignora o mundo que esse achadinho tá imperdível! 🎧🔊"])

    elif any(term in titulo_lower for term in ["suporte para notebook", "mouse sem fio", "teclado bluetooth", "webcam"]):
        return random.choice([
            "Pra render mais no trabalho e terminar as tarefas voando! 💻📈",
            "O upgrade que sua rotina precisava pra você focar no que importa! 🚀🖱️",
            "O setup de trabalho de milhões com preço de centavos! 🪑💼",
            "Pra dar conta de tudo e ainda sobrar tempo pro cafezinho! ☕✨"
        ])

    # 7. ELETRÔNICOS ESPECÍFICOS
    if "galaxy tab" in titulo_lower or "galaxy" in titulo_lower:
        return random.choice(["Ecossistema Galaxy com super desconto! Meus sensores apitaram! 🌌📱"])

    if "asus" in titulo_lower:
        return random.choice(["Máquina da ASUS na promo? Coloca agora no carrinho! 🛒💻"])

    if "linux" in titulo_lower and any(term in titulo_lower for term in ["notebook", "pc", "computador"]):
        return random.choice(["Atenção galera da TI: Máquina com Linux pagando barato! 🚀🐧"])

    # 8. REGRA DE AUTORIDADE COM BLINDAGEM ANTI-GENÉRICOS (O Fim do bug Elgin/LG!)
    marcas = ["motorola", "tramontina", "mondial", "sony", "samsung", "apple", "lg", "philco", "jbl", "brastemp", "consul", "intel", "logitech", "electrolux", "xiaomi", "asus", "acer", "lenovo", "dell", "nintendo", "arno", "britânia", "britania"]
    termos_genericos = ["para", "compatível", "compativel", "serve", "tipo", "cabo", "carregador", "capinha", "joystick", "genérico", "tv", "pc", "câmera", "camera", "lente", "sensor"]
    eh_produto_suspeito = any(termo in titulo_lower for termo in termos_genericos)

    marcas_presentes = []
    for marca in marcas:
        # AQUI É A MÁGICA: O \b garante que a marca seja uma palavra inteira. 
        # "lg" solto vai dar match, mas "eLGin" vai ser ignorado!
        match = re.search(rf'\b{marca}\b', titulo_lower)
        if match:
            posicao = match.start()
            marcas_presentes.append((posicao, marca))

    if marcas_presentes:
        marcas_presentes.sort()
        marca_principal = marcas_presentes[0][1]

        prefixos_validos = (marca_principal, "smartphone", "celular", "smart tv", "notebook", "tablet", "fone")
        if not (eh_produto_suspeito and not titulo_lower.startswith(prefixos_validos)):
            if marca_principal == "tramontina":
                return random.choice(["Qualidade Tramontina com desconto que o bolso aprova! 🍳✨"])
            elif marca_principal == "mondial":
                return random.choice(["A Mondial não brinca em serviço! Eletro no precinho! ⚡🔥"])
            else:
                return random.choice([
                    f"Qualidade {marca_principal.capitalize()} com desconto! Garimpei essa pra vocês! 🤖✨",
                    f"Fã da {marca_principal.capitalize()}? Minha IA achou o menor preço! 🔥"
                ])
            
    # 9.1 SALA VIP: MUNDO PET
    if re.search(r'\b(ração|racao|areia higiênica|sachê|sache|whiskas|golden|premier|petisco|tapete higiênico)\b', titulo_lower):
        
        # Se for especificamente sachê ou comida úmida
        if re.search(r'\b(sachê|sache|patê|pate|úmida)\b', titulo_lower):
            return random.choice([
                "Estoque de sachê garantido! Minha missão de alimentar os peludos tá cumprida! 🐱📉",
                "Aquela refeição premium que os pets amam! O sachê tá num preço ótimo! 🐾🍽️"
            ])
            
        # Para ração seca, areia e itens gerais
        else:
            return random.choice([
                "A Celle mandou eu achar desconto pra ajudar a sustentar os 4 gatos dela (e os seus pets também)! 🐾🐈",
                "Promoção liberada pros verdadeiros donos da casa (os pets, claro)! 🐕✨",
                "Estoque do mês garantido! Precinho excelente que meus radares encontraram pros peludos! 🐕🐈"
            ])
        
    # 10. SALA VIP: PÁSCOA (Transformado em Regra Independente para não falhar!)
    if re.search(r'\b(chocolate|ovo de páscoa|bombom|ferrero|lacta|nestlé|garoto|cacau show)\b', titulo_lower):
        return random.choice([
            "🐰 Alerta de Páscoa! O coelhinho (e meus algoritmos) acharam esse desconto! 🍫📉",
            "Ovo de Páscoa tá caro? Não no meu turno! Olha esse achadinho que a Celle pediu pra mandar: 🐰💸",
            "Estoque de chocolate garantido antes que os preços subam! 🍫✨"
        ])

    # 11. SALA VIP: SUPERMERCADO E LIMPEZA (Foco na necessidade e entrega rápida)
    if categoria_upper == "SUPERMERCADO" or re.search(r'\b(azeite|café|cafe|cápsula|sabão|sabao|omo|ariel|amaciante|papel higiênico|fralda|leite|nutella|limpeza|veja)\b', titulo_lower):
        
        # Sub-nicho: Azeite
        if "azeite" in titulo_lower:
            return random.choice([
                "O roubo do azeite acabou! Minha IA farejou esse preço justo pra você fazer o estoque! 🫒📉",
                "Alerta de ouro líquido na promoção! Pode colocar no carrinho sem medo de chorar! ✨🛒"
            ])
            
        # Sub-nicho: Café
        elif re.search(r'\b(café|cafe|cápsula|nespresso|três corações|dolce gusto)\b', titulo_lower):
            return random.choice([
                "Combustível de humano detectado com sucesso! Seus níveis de bateria agradecem (e o bolso também)! ☕🤖",
                "Pra garantir a energia do dia a dia (e aguentar a rotina) com desconto! ⚡☕"
            ])
            
        # Sub-nicho: Fraldas
        elif "fralda" in titulo_lower:
            return random.choice([
                "Atenção mamães e papais: hora de fazer o estoque! Fralda no precinho pra salvar o orçamento do mês! 👶💸",
                "Meus processadores calcularam: essa promo de fralda tá valendo muito a pena! 🍼📉"
            ])
            
        # Sub-nicho: Limpeza / Sabão
        elif re.search(r'\b(sabão|sabao|omo|ariel|amaciante|veja|detergente)\b', titulo_lower):
            return random.choice([
                "Manutenção da base ativada! Estoque de limpeza garantido sem pesar no bolso! 🧼✨",
                "O fim do sofrimento no supermercado! Produto de primeira pesado chegando direto na sua porta! 🧺📉"
            ])
            
        # Genérico Supermercado
        else:
            return random.choice([
                "Fazer mercado sem sair de casa e pagando menos? Meus algoritmos aprovam essa ideia! 🛒⚡",
                "Aquela comprinha de mês que chega voando na sua casa! Aproveita o desconto! 📦💨",
                "Achadinho de despensa liberado pela Celle! Reponha o estoque pagando preço de atacado! 🥫💸"
            ])
        
    # 12. SALA VIP: MARCAS QUERIDINHAS E BEBIDAS (Gatilhos de Identificação e Autoridade)
    
    # Sub-nicho: Cuidados Pessoais e Cabelo
    if re.search(r'\b(dove|nivea|rexona|elseve|lola cosmetics|lola|o boticário|boticario|natura)\b', titulo_lower):
        
        if "rexona" in titulo_lower:
            return random.choice([
                "Achadinho que não te abandona (nem o seu bolso)! Rexona no precinho pra fazer estoque! 🏃‍♀️💨",
                "Porque a rotina é pesada, mas o desodorante não pode falhar! Desconto ativado! 🛡️✨"
            ])
            
        elif re.search(r'\b(lola cosmetics|lola|elseve)\b', titulo_lower):
            return random.choice([
                "O projeto Rapunzel agradece! Tratamento de salão em casa pagando muito pouco! 💆‍♀️✨",
                "Cronograma capilar em dia com esse desconto imperdível que minha IA achou! 🧴💖"
            ])
            
        elif re.search(r'\b(o boticário|boticario|natura)\b', titulo_lower):
            return random.choice([
                "Aquele cheirinho de milhões com preço de centavos! ✨💨",
                "Promoção perfeita pra renovar o estoque e ficar cheirosa gastando pouco! 🥰🛍️"
            ])
            
        else: # Dove e Nivea
            return random.choice([
                "Cuidado pessoal de primeira linha com desconto de supermercado! Minha IA amou! 🛁💙",
                "A pele agradece e a carteira também! Promoção de marca queridinha no ar! 🧴✨"
            ])

    # Sub-nicho: Destilados e Bebidas Premium
    if re.search(r'\b(jack daniel\'s|jack daniels|jim beam|whisky|whiskey|bourbon|vodka|gin|tanqueray)\b', titulo_lower):
        
        if "jim beam" in titulo_lower:
            return random.choice([
                "O Bourbon nº 1 do mundo com um preço que até meus circuitos brindaram! 🥃🔥",
                "Jim Beam na promoção pra deixar o fim de semana no grau! Aproveita o desconto! 🥃✨"
            ])
            
        elif re.search(r'\b(jack daniel\'s|jack daniels)\b', titulo_lower):
            return random.choice([
                "Um clássico é um clássico! Jack Daniel's com desconto pra abastecer o bar! 🥃🎸",
                "Aquele Jack no precinho pra brindar as conquistas da semana! 🥃🔥"
            ])
            
        else: # Outras bebidas
            return random.choice([
                "O happy hour de sexta já tá garantido com esse desconto que eu minerei! 🍹📉",
                "Abasteça o bar pagando preço de atacado! Saúde! 🥂✨"
            ])


    # 13. FALLBACK DE PREÇO
    if preco_atual and preco_atual <= 40:
        return random.choice([
            "Aquele precinho camarada que a gente ama! 😍",
            "Menos de R$ 40? O robô aqui aprova colocar no carrinho! 🛒"
        ])

    # 14. GATILHOS GENÉRICOS DE ALTO IMPACTO (FALLBACK FINAL)
    return random.choice([
        "🕵️‍♀️ Olha o que eu acabei de garimpar para vocês! ✨",
        "🚨 Alerta de preço baixo na tela! 📉",
        "🤖 Eis que surge mais um super achadinho! 💎",
        "✨ Meus algoritmos acharam esse tesouro escondido! 🔍",
        "🎯 Mais um achadinho imperdível pra vocês! 🔥",
        "💰 Preço que choca POSITIVAMENTE os meus circuitos! 💥",
        "🛍️ Novo ciclo, novos achadinhos! Confirma aí 👇"
    ])

    
def gerar_link_afiliado(url_original, loja):
    try:
        # --- LÓGICA AWIN (KABUM E ALIEXPRESS) ---
        if loja in ["KABUM", "ALIEXPRESS"]:
            merchant_id = AWIN_MID_KABUM if loja == "KABUM" else AWIN_MID_ALIEXPRESS
            
            # Limpa parâmetros de rastreio velhos da URL original para não dar conflito
            url_limpa = url_original.split('?')[0] 
            
            # Codifica a URL no formato que a Awin exige (ued)
            url_encoded = urllib.parse.quote(url_limpa, safe='')
            
            # Monta o Deep Link Oficial da Awin
            link_awin = f"https://www.awin1.com/cread.php?awinmid={merchant_id}&awinaffid={AWIN_AFFILIATE_ID}&ued={url_encoded}"
            return link_awin

        # --- LÓGICA EXISTENTE ---
        elif loja == "MAGALU":
            if "magazinevoce.com.br/magazinecelle" not in url_original:
                codigo_produto = url_original.split('/')[-2] 
                return f"https://www.magazinevoce.com.br/magazinecelle/p/{codigo_produto}/"
            return url_original
            
        elif loja == "AMAZON":
            parsed = urllib.parse.urlparse(url_original)
            query = urllib.parse.parse_qs(parsed.query)
            query['tag'] = ['celle-20'] 
            new_query = urllib.parse.urlencode(query, doseq=True)
            return parsed._replace(query=new_query).geturl()
            
        elif loja == "SHOPEE":
            return url_original
            
    except Exception as e:
        print(f"Erro ao gerar link afiliado: {e}")
        return url_original

def gerar_link_ml_via_barra_topo(driver):
    print("| 🔗 ML: Buscando barra de afiliado no topo...")
    try:
        def validar_link_ml(link_value):
            return bool(link_value and any(dominio in link_value for dominio in ["meli.la", "mercadolivre", "ml.com"]))

        def tentar_obter_link_da_caixa():
            seletores_input = [
                "input.andes-form-control__field",
                ".andes-form-control__field input",
                "input[data-testid='copy_link_input']",
                "input[type='text'][value*='mercadolivre']",
                "input[type='text'][value*='meli']",
                "[data-testid='link-input'] input",
                "input[placeholder*='meli']",
                "input[aria-label*='link']"
            ]
            for seletor_input in seletores_input:
                try:
                    caixa_link = WebDriverWait(driver, 8).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, seletor_input))
                    )
                    link_final = caixa_link.get_attribute("value")
                    if validar_link_ml(link_final):
                        print(f"| 🎯 SUCESSO! Link capturado direto do campo: {link_final}")
                        return link_final
                except Exception:
                    continue
            return None

        def tentar_copiar_clipboard():
            botao_copiar_seletores = [
                "button[data-testid='copy-button__label_link']",
                "button[aria-label*='opiar']",
                "//button[contains(., 'Copiar')]"
            ]
            for seletor_copia in botao_copiar_seletores:
                try:
                    tipo = By.XPATH if "//" in seletor_copia else By.CSS_SELECTOR
                    botao = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((tipo, seletor_copia))
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao)
                    driver.execute_script("arguments[0].click();", botao)
                    print(f"| 🟢 Clique no botão de copiar: {seletor_copia}")
                    for _ in range(6):
                        link_final = pyperclip.paste()
                        if validar_link_ml(link_final):
                            print(f"| 🎯 SUCESSO! Link copiado: {link_final}")
                            return link_final
                        time.sleep(0.5)
                except Exception:
                    continue
            return None

        # PASSO 1: Tenta abrir o modal de geração de link
        botao_encontrado = False
        seletores_botao = [
            "button[data-testid='generate_link_button']",
            "//button[contains(., 'Compartilhar')]",
            "//button[contains(., 'compartilhar')]",
            "[data-testid='share-button']",
            "button[aria-label*='ompartilh']",
            "button[data-testid='share_button']",
            "//button[contains(., 'Gerar link')]",
            "//button[contains(., 'Link')]"
        ]

        for seletor in seletores_botao:
            try:
                tipo = By.XPATH if "//" in seletor else By.CSS_SELECTOR
                btn = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((tipo, seletor)))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", btn)
                print(f"| ✅ Botão encontrado: {seletor}")
                botao_encontrado = True
                break
            except Exception:
                continue

        if not botao_encontrado:
            print("| ⚠️ Nenhum botão de compartilhar encontrado")
            return None

        print("| ⏳ Aguardando modal do ML para gerar link...")
        time.sleep(2)

        # 1) Tenta capturar diretamente do campo input do modal (mais confiável)
        link_final = tentar_obter_link_da_caixa()
        if link_final:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return link_final

        # 2) Fallback: tenta pegar a URL atual da barra (menos ideal, mas útil quando o modal falha)
        try:
            atual = driver.current_url
            if atual and any(dom in atual for dom in ["meli.la", "mercadolivre", "ml.com"]):
                # Limpa querystrings para ter uma chave estável
                parsed = urllib.parse.urlparse(atual)
                cleaned = parsed._replace(query="").geturl()
                print(f"| ⚠️ Fallback: usando URL atual como link: {cleaned}")
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                return cleaned
        except Exception as e_fallback:
            print(f"| ⚠️ Fallback por URL atual falhou: {e_fallback}")

        print("| ⚠️ Falha: não consegui capturar o link do modal nem pela URL atual.")

    except Exception as e:
        print(f"| ❌ Erro ao gerar link: {e}")
    finally:
        try:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except:
            pass

    return None

def extrair_dados_produto_ml(driver, preco_maximo=None):
    # Inicialização
    titulo, image_url = "Produto Mercado Livre", None
    preco_atual, preco_antigo = None, None
    nota, vendas_count = 0.0, 0
    is_best_seller, is_platinum = False, False

    # 1. TÍTULO (Aguardar carregar)
    try:
        titulo_elem = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.ui-pdp-title"))
        )
        titulo = titulo_elem.text.strip()
    except: pass

    # 2. PREÇOS (Com suporte a centavos)
    try:
        container_preco = driver.find_element(By.CSS_SELECTOR, ".ui-pdp-price__second-line")
        fraction = container_preco.find_element(By.CSS_SELECTOR, ".andes-money-amount__fraction").text.replace(".", "")
        try:
            cents = container_preco.find_element(By.CSS_SELECTOR, ".andes-money-amount__cents").text
            preco_atual = float(f"{fraction}.{cents}")
        except:
            preco_atual = float(fraction)

        # Preço Antigo
        try:
            old_fraction = driver.find_element(By.CSS_SELECTOR, ".ui-pdp-price__original-value .andes-money-amount__fraction").text.replace(".", "")
            preco_antigo = float(old_fraction)
        except: pass
    except: pass

    # --- FILTRO DE PREÇO (Early Exit) ---
    if preco_maximo and preco_atual and preco_atual > preco_maximo:
        return titulo, preco_atual, preco_antigo, 0.0, None, 0, False, False

    # 3. NOTA E POPULARIDADE (Usando os seletores que você enviou)
    nota = 0.0
    vendas_count = 0

    try:
        # Espera o bloco de avaliações carregar (essencial!)
        WebDriverWait(driver, 4).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".ui-pdp-review__rating")))

        # Captura a Nota (ex: 4.7)
        elem_nota = driver.find_element(By.CSS_SELECTOR, ".ui-pdp-review__rating")
        nota = float(elem_nota.text.replace(",", "."))
        
        # Captura a Quantidade (ex: 1387)
        elem_vendas = driver.find_element(By.CSS_SELECTOR, ".ui-pdp-review__amount")
        texto_vendas = elem_vendas.text
        
        # Limpa TUDO: tira os parênteses e pontos (ex: "(1.387)" vira "1387")
        vendas_limpo = re.sub(r'[^\d]', '', texto_vendas)
        if vendas_limpo:
            vendas_count = int(vendas_limpo)

        print(f"| ⭐ Nota: {nota} | 📈 Avaliações: {vendas_count}")

    except Exception as e:
        print(f"| ⚠️ Qualidade não detectada (pode ser produto sem venda ainda)")
        nota = 0.0
        vendas_count = 0

    # 4. VENDEDOR E SELOS
    try:
        vendedor_info = driver.find_element(By.CSS_SELECTOR, ".ui-pdp-seller__header-title, .ui-pdp-seller-info").text.lower()
        if any(termo in vendedor_info for termo in ["platinum", "gold", "oficial", "melhor"]):
            is_platinum = True
            
        # Selo de mais vendido
        if driver.find_elements(By.CSS_SELECTOR, ".ui-pdp-promotions-pill-label__container"):
            is_best_seller = True
    except: pass

    # 5. IMAGEM HD
    try:
        img = driver.find_element(By.CSS_SELECTOR, "figure.ui-pdp-gallery__figure img, img.ui-pdp-image")
        image_url = img.get_attribute("src")
        if image_url and "mlstatic.com" in image_url:
            image_url = re.sub(r'-[A-Z]\.(webp|jpg|jpeg|png)$', r'-O.\1', image_url)
            image_url = image_url.replace("D_Q_NP_", "D_NQ_NP_")
    except: pass

    return titulo, preco_atual, preco_antigo, nota, image_url, vendas_count, is_best_seller, is_platinum


def gerar_link_amazon_sitestripe(driver):
    print("| 🔗 AMAZON: Iniciando captura SiteStripe...")
    
    try:
        # PASSO 1: Clicar no botão inicial "Obter link: Texto"
        try:
            print("| 🖱️ Abrindo menu 'Obter link'...")
            botao_abrir = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "amzn-ss-get-link-button"))
            )
            driver.execute_script("arguments[0].click();", botao_abrir)
            # Pequena pausa para o popover carregar o conteúdo interno
            time.sleep(2) 
        except Exception as e:
            print(f"| ❌ Não encontrei o botão 'Obter link': {e}")
            return None

        # PASSO 2 NOVO: Ir direto na caixa de texto e capturar o link pré-selecionado
        try:
            print("| 🖱️ Capturando o link direto da caixa de texto...")
            # 'amzn-ss-text-shortlink-textarea' é o ID padrão da caixinha com o link curto da Amazon
            campo_do_link = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "amzn-ss-text-shortlink-textarea"))
            )
            
            # Pegamos o link de dentro do atributo 'value' da caixa de texto
            link_curto = campo_do_link.get_attribute('value')
            
            # Se por acaso o value vier vazio (raro), tentamos o texto puro
            if not link_curto:
                link_curto = campo_do_link.text

        except Exception as e:
            print(f"| ❌ O menu abriu, mas não encontrei a caixa com o link: {e}")
            return None

        # PASSO 3: Validar se o link foi capturado com sucesso
        if link_curto and "amzn.to" in link_curto:
            print(f"| ✅ SUCESSO! Link extraído: {link_curto}")
            
            # Tenta fechar o popover para não atrapalhar o próximo item
            try:
                driver.execute_script("document.querySelector('.a-popover-header button').click();")
            except: 
                pass
                
            return link_curto
        
        print("| ❌ Falha: A caixa de texto foi encontrada, mas o link estava vazio ou inválido.")
        return None

    except Exception as e:
        print(f"| ❌ Erro geral na captura: {e}")
        return None

def gerar_link_magalu_oficial(driver):
    print("| 🔗 MAGALU: Tentando gerar link curto oficial...")
    
    try:
        # --- PASSO 1: ENCONTRAR E CLICAR NO BOTÃO "GERAR LINK" ---
        botao_gerar = None
        seletores_botao = [
            '[data-testid="phm-button-desktop"]',
            "//button[contains(., 'Gerar link')]",
            "//div[contains(text(), 'Gerar link')]",
            "[data-testid='generate-link-button']"
        ]
        
        for seletor in seletores_botao:
            try:
                tipo = By.XPATH if "//" in seletor else By.CSS_SELECTOR
                # Mudança: esperar ser CLICÁVEL (element_to_be_clickable)
                botao_gerar = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((tipo, seletor))
                )
                
                if botao_gerar:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_gerar)
                    time.sleep(0.5)
                    break 
            except:
                continue
            
        if not botao_gerar:
            print("| ⚠️ Botão 'Gerar link' não encontrado (Verifique se está logado).")
            return None
            
        # Clica via JavaScript para evitar bloqueios de outros elementos na frente
        driver.execute_script("arguments[0].click();", botao_gerar)
        
        # --- PASSO 2: AGUARDA O MODAL E CAPTURA O LINK ---
        print("| ⏳ Aguardando modal...")
        seletor_input = '[data-testid="copy-to-clipboard-input"]'
        
        try:
            # Espera até 10 segundos para o modal processar o link
            campo_link = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, seletor_input))
            )
            
            link_curto = campo_link.get_attribute("value")
            
            if link_curto and ("onelink.me" in link_curto or "magalu" in link_curto):
                print(f"| 🎯 LINK CURTO CAPTURADO: {link_curto}")
                
                # Tenta fechar o modal com ESC
                try:
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                except:
                    pass
                    
                return link_curto
            else:
                print(f"| ⚠️ Valor inválido capturado: {link_curto}")
                
        except Exception as e:
            print(f"| ❌ O modal abriu, mas o link não apareceu: {e}")

    except Exception as e:
        # Este é o except que faltava para fechar o primeiro try
        print(f"| ❌ Falha crítica na função de link: {e}")
    
    return None

def processar_feed_mercadolivre(driver, alvo, produtos_processados_set, preco_maximo=None):
    print(f"\n======== {alvo['nome']} (DETALHADO) ========")
    driver.get(alvo['url_lista'])
    time.sleep(3) # Tempo suficiente para o layout Poly carregar

    links_para_visitar = []
    seletores_card = [".poly-card", ".ui-search-result", ".andes-card", "[data-item-id]"]
    seletores_link = ["a.poly-component__title", "a.ui-search-result__link", "a[href*='mercadolivre']", "a.poly-component-link"]

    try:
        cards = []
        for seletor_card in seletores_card:
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, seletor_card)
                if cards:
                    print(f"| ✅ Cards encontrados usando: {seletor_card} ({len(cards)} itens)")
                    break
            except:
                continue

        if not cards:
            print(f"| ❌ Nenhum card encontrado com os seletores disponíveis")
            return

        print(f"| FEED: Analisando vitrine de {len(cards)} itens...")

        for card in cards[:40]:
            try:
                # --- NOVO FILTRO DE VITRINE ---
                if preco_maximo:
                    try:
                        preco_vitrine_texto = card.find_element(By.CSS_SELECTOR, ".poly-price__current .andes-money-amount__fraction").text
                        preco_vitrine = extrair_valor_numerico(preco_vitrine_texto)

                        if preco_vitrine and preco_vitrine > preco_maximo:
                            continue
                    except:
                        pass

                url = None
                for seletor_link in seletores_link:
                    try:
                        link_elem = card.find_element(By.CSS_SELECTOR, seletor_link)
                        url = link_elem.get_attribute("href")
                        if url and "mercadolivre" in url:
                            break
                    except:
                        continue

                if url:
                    links_para_visitar.append(url)
            except:
                continue
    except Exception as e:
        print(f"| ❌ Erro ao ler feed: {e}")
        return

    # 👇 NOVO CONTADOR AQUI 👇
    produtos_enviados_nesta_lista = 0

    # Grupo principal usado para o cache (mantém compatibilidade por grupo)
    grupo_principal = GRUPOS_ALVO[0].replace("[CANAL]", "").strip()

    for url_produto in links_para_visitar:
        # Verifica se já bateu a meta logo no início do loop
        if produtos_enviados_nesta_lista >= 5:
            print(f"| 🛑 Limite de 5 produtos atingido para {alvo['nome']}. Finalizando lista!")
            break
            
        # Checagem RÁPIDA NO CACHE usando a URL (evita abrir a página desnecessariamente)
        try:
            if verificar_se_ja_enviou_24h(url_produto, grupo_principal):
                print(f"⏭️ Produto já enviado nos últimos {int(CACHE_RETENCAO_SECONDS/3600)}h, pulando antes de abrir...")
                continue
        except Exception:
            pass

        try:
            driver.get(url_produto)
            
            # Extração dos 8 valores
            titulo, preco_atual, preco_antigo, nota, img_url, vendas_count, is_best_seller, is_platinum = extrair_dados_produto_ml(driver, preco_maximo=preco_maximo)  

            # --- LÓGICA DE FILTRAGEM ---
            vendedor_elite = is_platinum or is_best_seller
            popularidade_ok = vendas_count >= 50 
            satisfacao_ok = nota >= 4.3 if nota > 0 else True

            # Se não for elite e não tiver vendas, ou se a nota for ruim: REJEITA
            #if not (vendedor_elite or popularidade_ok) or not satisfacao_ok:
            #    print(f"| ❌ REJEITADO: Qualidade/Vendedor insuficiente ({vendas_count} vend. / Nota {nota})")
            #    continue
                
            if titulo in produtos_processados_set:
                print(f"| 🚫 DUPLICADO: '{titulo[:25]}...' já enviado.")
                continue

            # --- FILTRO DE PREÇO MÁXIMO ---
            if preco_maximo and preco_atual and preco_atual > preco_maximo:
                print(f"| 💲 REJEITADO (Preço): R${preco_atual:.2f} > limite de R${preco_maximo:.0f}")
                continue

            if preco_atual is None: 
                print("| ⚠️ Pulei: Preço não identificado.")
                continue

            # --- GERAÇÃO DE LINK E ENVIO ---
            print(f"| 🔎 Analisando: {titulo[:30]}... | Elite: {vendedor_elite} | Vendas: {vendas_count}")
            
            if produto_eh_bloqueado(titulo):
                print(f"| 🚫 BLOQUEADO: Título contém termo proibido.")
                continue

            link_afiliado = gerar_link_ml_via_barra_topo(driver)
            
            if not link_afiliado:
                print("| 🔗 Pulei: Falha ao gerar link de afiliado.")
                continue

            # ==========================================================
            # NOVA FORMATAÇÃO: MERCADO LIVRE COM COPY INTELIGENTE
            # ==========================================================
            
            # 1. Tenta gerar a chamada inteligente padrão
            chamada = gerar_chamada_inteligente(titulo, preco_atual, alvo.get("categoria", ""))
            
            # 2. GATILHO DE URGÊNCIA: Se for link relâmpago, substitui a frase!
            if "lightning" in alvo.get("url_lista", ""):
                chamada = random.choice([
                    "⚡ <b>OFERTA RELÂMPAGO MERCADO LIVRE! CORRE!</b> ⏱️",
                    "⏳ <b>TEMPO ACABANDO! Achadinho Relâmpago no ML!</b>",
                    "⚡ <b>PISCOU, PERDEU! Oferta com tempo limitado!</b>",
                    "🏃‍♀️ <b>CORRE QUE É RELÂMPAGO! Desconto no ML!</b> ⚡"
                ])

            # 3. Formata os preços
            bloco_preco = f"✅ <b>Por: {formatar_preco_br(preco_atual)}</b>"
            if preco_antigo and preco_antigo > preco_atual:
                desconto = int(((preco_antigo - preco_atual) / preco_antigo) * 100)
                bloco_preco = (
                    f"❌ <s>De: {formatar_preco_br(preco_antigo)}</s>\n"
                    f"✅ <b>Por: {formatar_preco_br(preco_atual)}</b> ({desconto}% OFF) 📉"
                )

            # 4. Junta tudo na mensagem final
            mensagem = (
                f"{chamada}\n\n"
                f"📦 <b>{titulo}</b>\n\n"
                f"{bloco_preco}\n"
            )
            
            if nota > 0:
                mensagem += f"⭐ <b>Avaliação: {nota}/5.0</b>\n\n"
            else:
                mensagem += "\n"
                
            mensagem += (
                f"🛒 <b>COMPRE AQUI:</b> 👇\n"
                f"👉 <a href='{link_afiliado}'>CLIQUE PARA VER NO SITE</a>"
            )

            # Disparo para os canais
            enviar_telegram(mensagem, link_afiliado, img_url)

            teve_envio_whats = False
            caminho_foto = None
            try:
                if img_url:
                    caminho_foto = baixar_imagem_temporaria(img_url, "temp_ml.jpg")

                for grupo in GRUPOS_ALVO:
                    if verificar_se_ja_enviou_24h(titulo, grupo):
                        continue

                    if caminho_foto:
                        enviar_whatsapp_robusto(driver, grupo, mensagem, caminho_foto)
                    else:
                        enviar_whatsapp(driver, grupo, mensagem)
                    
                    # Salva também a URL do produto no cache para checagens futuras sem abrir a página
                    registrar_envio_24h(titulo, grupo, url=url_produto)
                    teve_envio_whats = True
                    human_delay(2, 4)

            finally:
                if caminho_foto and os.path.exists(caminho_foto):
                    try: os.remove(caminho_foto)
                    except: pass

            if teve_envio_whats:
                produtos_processados_set.add(titulo)
                # 👇 AUMENTA O CONTADOR E AVISA NA TELA 👇
                produtos_enviados_nesta_lista += 1
                print(f"| ✅ Sucesso ({alvo['nome']}): {produtos_enviados_nesta_lista}/5")

                # 🔄 Retorna para a aba do Mercado Livre após todos os envios
                try:
                    for handle in driver.window_handles:
                        driver.switch_to.window(handle)
                        if "mercadolivre" in driver.current_url.lower() or "mercado" in driver.title.lower():
                            print("| 🔙 Voltado para a aba do Mercado Livre")
                            break
                except Exception as e:
                    print(f"| ⚠️ Não conseguiu voltar para ML: {e}")

            human_delay(5, 10)

        except Exception as e:
            print(f"| ❌ Erro ao processar produto: {e}")
            continue

def selecionar_alvos_por_grupo(lista_alvos, grupo):
    return [alvo for alvo in lista_alvos if alvo.get('grupo') == grupo]

def preparar_mensagem_alerta_categoria(nome_categoria):
    nome_categoria_upper = nome_categoria.upper()

    mensagens = {
        "CELULARES": "<b>⚡ Ofertas de Celulares no ar!</b>\nO robô encontrou preços excelentes em smartphones, acessórios e lançamentos. 👇📱✨",
        "GAMES": "<b>🎮🔥 Promoções de Games!</b>\nControles, jogos, cadeiras e acessórios gamer com preço baixo detectado. 👇🔥",
        "PCGAMER": "<b>🖥️⚡ Achados para PC Gamer!</b>\nGabinetes, RAM, SSD, coolers e hardware com descontos reais. 👇💥",
        "TELEVISOES": "<b>📺✨ Ofertas de TVs atualizadas!</b>\nSmart TVs, 4K, 144Hz e modelos premium com preço especial. 👇⚡",
        "BELEZA": "<b>💄✨ Achados de Beleza!</b>\nSkincare, cabelo e perfumaria com descontos verificados pelo robô. 👇🌸",
        "PERIFERICOS": "<b>⌨️🔥 Promoções de Periféricos!</b>\nMouse, teclado, mousepad e teclados mecânicos com preço reduzido. 👇⚡",
        "AUDIO": "<b>🎧💥 Ofertas de Áudio!</b>\nFones, headsets, caixas e soundbars com descontos reais. 👇🔊",
        "MOVEIS": "<b>🪑✨ Ofertas de Móveis!</b>\nMesas, cadeiras, organização e decoração com preço baixo confirmado. 👇🏡",
        "NOTEBOOKS": "<b>💻⚡ Promoções de Notebooks!</b>\nModelos para estudo, trabalho e gamer com quedas de preço. 👇🔥",
        "ELETRODOMESTICOS": "<b>🏠🔥 Ofertas de Eletrodomésticos!</b>\nGeladeira, fogão, lava e seca e muito mais com desconto real. 👇⚡",
        "ELETROPORTATEIS": "<b>⚡✨ Promoções de Eletroportáteis!</b>\nAir fryer, cafeteira, mixer, aspirador e outros com preço reduzido. 👇🔥",
        "BELEZA": "<b>🌸 Achadinhos de Beleza!</b>\nMeninas, o robô encontrou promoções de skincare, cabelo e maquiagem que valem a pena. 👇✨",
        "CASA": "<b>🏠✨ Para sua Casa!</b>\nOrganizadores, decoração e itens de cozinha com preço baixo pra deixar tudo lindo. 👇💖",
        "UTILIDADES": "<b>🍳 Praticidade na Cozinha!</b>\nAir fryer, potes herméticos e utensílios que facilitam a vida com desconto real. 👇🔥",
    }
    
    return mensagens.get(nome_categoria_upper, f"<b>✨ Novo Ciclo de Ofertas na Categoria {nome_categoria.capitalize()}!</b> 👇")

# =========================================================
# CONFIGURAÇÕES E CREDENCIAIS
# =========================================================

ARQUIVO_HISTORICO =  "historico_precos.csv"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TERMOS_BLOQUEADOS = [
    # --- CONTROLES E ACESSÓRIOS DE TV ---
    "controle remoto",
    "controle para tv",
    "controle de tv",
    "controle universal",
    
    # --- IMPRESSÃO E ESCRITÓRIO ---
    "cartucho",
    "toner",
    "tinta para impressora",
    "tinta de impressora",
    "refil de tinta",
    
    # --- PEÇAS, REPAROS E USADOS ---
    "usado",
    "recondicionado",
    "vitrine",
    "reparo",
    "peça de reposição",
    "peças para",
    "display lcd", # Muito comum aparecer como se fosse o celular
    "tela touch",
    
    # --- ACESSÓRIOS BARATOS E GENÉRICOS ---
    "capinha",
    "película",
    "genérico",
    "paralelo",
    
    # --- PRODUTOS FORA DO NICHO ---
    "freezer horizontal",
    "caminhão",
    "pneu",
    "calota",
    "chocadeira",
    "incubadora"
]

# =====================================================
# LISTAS MESTRAS (ESTRATÉGIA DE GESTOR DE TRÁFEGO)
# =====================================================

LISTA_MESTRE_KABUM = [
    {
        "nome": "KaBuM! - Periféricos",
        "url_lista": "https://www.kabum.com.br/promocao/PERIFERICOSOFFICE", 
        "dominio_base": "https://www.kabum.com.br",
        "loja": "KABUM",
        "seletor_item_lista": 'a[href^="/produto/"]',
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'span.text-sm.line-clamp-2',
        "seletor_preco_detalhe": 'span.text-base.font-semibold',
        "seletor_preco_antigo": 'span.line-through',
        "delay_min": 5, "delay_max": 10,
        "grupo": "NOITE",
        "categoria": "PCGAMER"
    }
]

LISTA_MESTRE_ALIEXPRESS = [
    {
        "nome": "AliExpress - Ofertas Superiores",
        "url_lista": "https://www.aliexpress.com/ssr/300000455/Kf4fNDFeTy?spm=a2g0o.home.tab.2.38c73f40ahovnI&disableNav=YES&pha_manifest=ssr&_immersiveMode=true&_gl=1*q8qxfr*_gcl_au*NDExMjc4MjE1LjE3NzQ1NDkzMjM.*_ga*NjcwOTE4NzU4LjE3NzQ1NDkzMjQ.*_ga_VED1YSGNC7*czE3NzU4Mjg5MDgkbzIkZzEkdDE3NzU4Mjg5ODEkajU3JGwwJGgw",
        "dominio_base": "https://pt.aliexpress.com",
        "loja": "ALIEXPRESS",
        "seletor_item_lista": 'div.search-card-item, a.search-card-item',
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-pl="product-title"]',
        "seletor_preco_detalhe": '.product-price-value',
        "seletor_preco_antigo": '.product-price-original',
        "delay_min": 8, "delay_max": 15,
        "grupo": "TARDE",
        "categoria": "UTILIDADES"
    }
]

LISTA_MESTRE_MAGALU = [

    # --- NOVO LINK MANUAL (ADICIONE ISTO AQUI) ---
    {
        "nome": "Magazine Você - Decoração", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/decoracao/l/de/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "NOITE", 
        "categoria": "CASA"
    },
    # ---------------------------------------------

    # --- GRUPO MANHÃ (Foco: Casa, Rotina e Beleza) ---
    {
        "nome": "Magazine Você - Eletroportáteis", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/eletroportateis/l/ep/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "MANHA",
        "categoria": "ELETROPORTATEIS"
    }, 
    {
        "nome": "Magazine Você - Beleza e Perfumaria", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/beleza-perfumaria/l/pf/",
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "MANHA",
        "categoria": "BELEZA"
    },
    {
        "nome": "Magazine Você - Móveis e Escritório", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/moveis/l/mo/",
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "MANHA", # MUDANÇA ESTRATÉGICA: De Tarde para Manhã
        "categoria": "MOVEIS"
    }, 

    # --- GRUPO ALMOÇO (Foco: Pessoal, Impulso e Mobile) ---
    {
        "nome": "Magazine Você - Celulares", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/celulares-e-smartphones/l/te/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "ALMOCO",
        "categoria": "CELULARES"
    },
    {
        "nome": "Magazine Você - Áudio e Som", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/audio/l/ea/",
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "ALMOCO", # MUDANÇA ESTRATÉGICA: De Tarde para Almoço
        "categoria": "AUDIO"
    }, 

    # --- GRUPO TARDE (Foco: Produtividade e Trabalho) ---
    {
        "nome": "Magazine Você - Notebooks", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/notebook/informatica/s/in/note/",
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "TARDE",
        "categoria": "NOTEBOOKS"
    }, 
    {
        "nome": "Magazine Você - Periféricos", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/acessorios-e-perifericos/informatica/s/in/aprf/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "TARDE",
        "categoria": "PERIFERICOS"
    },

    # --- GRUPO NOITE (Foco: Família, Lazer e Gamer Hardcore) ---
    {
        "nome": "Magazine Você - Televisões", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/tv-e-video/l/et/",
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "NOITE",
        "categoria": "TELEVISOES"
    },
    {
        "nome": "Magazine Você - Eletrodomésticos", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/eletrodomesticos/l/ed/",
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "NOITE",
        "categoria": "ELETRODOMESTICOS"
    }, 
    {
        "nome": "Magazine Você - Games (Consoles/Jogos)", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/games/l/ga/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "NOITE", # MUDANÇA ESTRATÉGICA: De Almoço para Noite
        "categoria": "GAMES"
    },
    {
        "nome": "Magazine Você - PC GAMER", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/pc-gamer/informatica/s/in/pcgm/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "NOITE",
        "categoria": "PCGAMER"
    },
    # Adicione estes itens na sua LISTA_MESTRE_MAGALU
    {
        "nome": "Magazine Você - Esporte e Lazer", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/esporte-e-lazer/l/ep/", 
        "grupo": "TARDE", # Ótimo para preencher o turno da tarde
        "categoria": "UTILIDADES",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "dominio_base": "https://www.magazinevoce.com.br"
    },
    {
        "nome": "Magazine Você - Casa Inteligente", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/casa-inteligente/l/ci/", 
        "grupo": "MANHA", 
        "categoria": "ELETRONICOS",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "dominio_base": "https://www.magazinevoce.com.br"
    }
]

LISTA_MESTRE_AMAZON = [
    # --- MANTIDOS ---
    {
        "nome": "Amazon - Top Eletrônicos",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/electronics/", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "ALMOCO", # Mudado para Almoço
        "categoria": "ELETRONICOS"
    },
    {
        "nome": "Amazon - Produtos Pet",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/pet-products/", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "MANHA", # Ótimo para o horário que as pessoas estão alimentando os pets e notam que a ração está no fim
        "categoria": "PET"
    },
    {
        "nome": "Amazon - Computadores",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/computers/", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "TARDE", # Mudado para Tarde
        "categoria": "COMPUTADORES"
    },
    # --- NOVOS (Estratégia de Variedade) ---
    {
        "nome": "Amazon - Mais Vendidos Livros",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/books/", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "MANHA", # Ótimo para começar o dia
        "categoria": "LIVROS"
    },
    {
        "nome": "Amazon - Cozinha",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/kitchen/", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "MANHA", # Pega o público "Dona de Casa"
        "categoria": "CASA"
    },
    {
        "nome": "Amazon - Recomendações",
        "url_lista": "https://www.amazon.com.br/b/node/122326793011", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "TARDE", # Público masculino/hobby à tarde
        "categoria": "FERRAMENTAS"
    },
    {
        "nome": "Amazon - Cuidados Pessoais",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/beauty/16335314011/", 
        "loja": "AMAZON",
        "grupo": "MANHA", # As pessoas planejam o dia/compras de higiene cedo
        "categoria": "BELEZA",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout',
        "seletor_link_lista": 'a.a-link-normal',
        "dominio_base": "https://www.amazon.com.br"
    },
    {
        "nome": "Amazon - Dispositivos Echo e Alexa",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/amazon-devices/", 
        "loja": "AMAZON",
        "grupo": "NOITE", # Tech e automação combinam com o lazer da noite
        "categoria": "ELETRONICOS",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout',
        "seletor_link_lista": 'a.a-link-normal',
        "dominio_base": "https://www.amazon.com.br"
    }
]

LISTA_MESTRE_ML = [
    # --- MANHÃ: Higiene, Beleza e Pequenas Utilidades ---
    {
        "nome": "ML - Beleza e Cuidados (Ofertas)",
        # Filtro: Beleza + Mais de 30% OFF + Full
        "url_lista": "https://www.mercadolivre.com.br/ofertas?container_id=MLB-OFFERS-SEARCH&category=MLB1246#filter_applied=category&filter_initialize=category&category=MLB1246&discount=30-100",
        "loja": "MERCADOLIVRE",
        "categoria": "BELEZA",
        "grupo": "MANHA",
        "delay_min": 5, "delay_max": 10
    },
    # --- MANHÃ OU ALMOÇO: Compras de necessidade básica e reposição ---
    {
        "nome": "ML - Supermercado (Ofertas)",
        "url_lista": "https://lista.mercadolivre.com.br/supermercado/market/_Deal_cpg-melhores-ofertas_Container_cpg-melhores-ofertas#origin=home_carousel&global_position=6",
        "loja": "MERCADOLIVRE",
        "categoria": "SUPERMERCADO",
        "grupo": "MANHA", # O horário da manhã é excelente para donas de casa planejando o dia
        "delay_min": 5, "delay_max": 10
    },
    # --- PÁSCOA: Compras de Impulso e Sazonal ---
    {
        "nome": "ML - Ofertas do BBB",
        # 👇 COLE O SEU LINK DO MERCADO LIVRE AQUI 👇
        "url_lista": "https://lista.mercadolivre.com.br/_Container_lpsm-bbb-26-ofertas-que-voce-viu-no-programa#c_container_id=MLB1483933-1&c_element_id=31952665-23bf-11f1-895a-b71f69fe2a0f&DEAL_ID=MLB1483933-1&S=landingHubbbb&V=20&T=CarouselDynamic-home&L=VER-MAIS&deal_print_id=313b6da0-23bf-11f1-b47f-a30f9dd2fbea&c_tracking_id=313b6da0-23bf-11f1-b47f-a30f9dd2fbea",
        "loja": "MERCADOLIVRE",
        "categoria": "SUPERMERCADO", # Usamos Supermercado para acionar os gatilhos certos de copy
        "grupo": "MANHA",
        "delay_min": 5, "delay_max": 10
    },
    {
        "nome": "ML - O melhor da Páscoa",
        # 👇 COLE O MESMO LINK AQUI 👇
        "url_lista": "https://lista.mercadolivre.com.br/_Container_mlb-moda-outlet#c_container_id=MLB1075410-1&c_id=%2Fsplinter%2Fcarouselitem&c_element_order=1&c_campaign=moda-carrossel-outlet&c_label=%2Fsplinter%2Fcarouselitem&c_uid=0871e284-3280-11f1-a5b0-4786924062c9&c_element_id=0871e284-3280-11f1-a5b0-4786924062c9&c_content_origin=splinter-default&c_content_type=default&c_global_position=3&deal_print_id=08695700-3280-11f1-ad04-d1756b06fa02&c_tracking_id=08695700-3280-11f1-ad04-d1756b06fa02",
        "loja": "MERCADOLIVRE",
        "categoria": "MODA",
        "grupo": "ALMOCO",
        "delay_min": 5, "delay_max": 10
    },
    {
        "nome": "ML - Animais (Ofertas)",
        "url_lista": "https://www.mercadolivre.com.br/ofertas?container_id=MLB-OFFERS-SEARCH&category=MLB1071#filter_applied=category&filter_initialize=category&category=MLB1071",
        "loja": "MERCADOLIVRE",
        "categoria": "PET",
        "grupo": "TARDE",
        "delay_min": 5, "delay_max": 10
    },

    # --- ALMOÇO: Smartphones, Eletrônicos e Desejos ---
    {
        "nome": "ML - Smartphones e Acessórios",
        # Filtro: Celulares + Ofertas do Dia + Melhores Vendedores
        "url_lista": "https://www.mercadolivre.com.br/ofertas?container_id=MLB-OFFERS-SEARCH&category=MLB1051#filter_applied=category&filter_initialize=category&category=MLB1051",
        "loja": "MERCADOLIVRE",
        "categoria": "CELULARES",
        "grupo": "ALMOCO",
        "delay_min": 5, "delay_max": 10
    },

    # --- TARDE: Ferramentas, Casa e Produtividade ---
    {
        "nome": "ML - Ferramentas e Construção",
        # Filtro: Ferramentas + Ofertas Ativas
        "url_lista": "https://www.mercadolivre.com.br/ofertas?container_id=MLB779362-1&promotion_type=lightning#filter_applied=promotion_type&filter_position=2&is_recommended_domain=false&origin=scut",
        "loja": "MERCADOLIVRE",
        "categoria": "FERRAMENTAS",
        "grupo": "TARDE",
        "delay_min": 5, "delay_max": 10
    },

    # --- NOITE: Games, TVs e Eletrodomésticos ---
    {
        "nome": "ML - Consoles e Games",
        # Filtro: Games + Mais Vendidos
        "url_lista": "https://www.mercadolivre.com.br/ofertas?container_id=MLB-OFFERS-SEARCH&category=MLB1144#filter_applied=category&filter_initialize=category&category=MLB1144",
        "loja": "MERCADOLIVRE",
        "categoria": "GAMES",
        "grupo": "NOITE",
        "delay_min": 5, "delay_max": 10
    }
]


# =====================================================
# LISTA ESTRATÉGICA: PÚBLICO FEMININO / TICKET BAIXO
# =====================================================
LISTA_MESTRE_FEMININA = [
    # --- AMAZON: O REI DO SKINCARE E CASA ---
    {
        "nome": "Amazon - Beleza e Skincare",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/beauty/", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "MANHA", # Mulheres costumam olhar isso logo cedo ou no almoço
        "categoria": "BELEZA"
    },
    {
        "nome": "Amazon - Cozinha e Praticidade",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/kitchen/", 
        "dominio_base": "https://www.amazon.com.br",
        "loja": "AMAZON",
        "seletor_item_lista": 'div[id^="p13n-asin-index-"], div.zg-grid-general-faceout', 
        "seletor_link_lista": 'a.a-link-normal',
        "seletor_titulo_detalhe": '#productTitle',
        "seletor_preco_detalhe": '.a-price .a-offscreen', 
        "seletor_preco_antigo": 'span[data-a-strike="true"] .a-offscreen',
        "delay_min": 5, "delay_max": 10,
        "grupo": "TARDE", # Hora do café/lanche
        "categoria": "CASA"
    },

    # --- MAGALU: UTILIDADES DOMÉSTICAS (A "MAGA") ---
    {
        "nome": "Magazine Você - Utilidades Domésticas", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/utilidades-domesticas/l/ud/?page=1&sortOrientation=desc&sortType=soldQuantity", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "ALMOCO",
        "categoria": "UTILIDADES"
    },
    {
        "nome": "Magazine Você - Cama, Mesa e Banho", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/cama-mesa-e-banho/l/cm/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "NOITE", # Hora de relaxar em casa
        "categoria": "CASA"
    },

    # --- SHOPEE: O OURO (ACHADINHOS BARATOS) ---
    # Removido para envio apenas manual
]

MAX_PRODUTOS_A_ANALISAR = 5
DOMINIO_BASE = "https://www.magazineluiza.com.br"

chrome_driver = None


# =========================================================
# FUNÇÕES DE RASTREAMENTO PADRÃO
# =========================================================

def rastrear_lista_produtos(url_lista, driver, seletor_item, seletor_link, dominio_base, max_list_items=40, preco_maximo=None):
    print(f"[SELENIUM] Acessando a lista: {url_lista}")
    driver.get(url_lista)
    
    print("| 🔄 Rolando a página para forçar o carregamento dos produtos...")
    for _ in range(4):
        driver.execute_script("window.scrollBy(0, 600);")
        time.sleep(1.5)
    
    driver.execute_script("window.scrollTo(0, 300);")
    
    if "amazon" in url_lista:
        seletor_item = 'div[data-asin], .zg-grid-general-faceout, div[id^="p13n-asin-index-"], .s-result-item, a.dcl-product-link'
    elif "mercadolivre" in url_lista:
        seletor_item = '.poly-card, .andes-card, .ui-search-result'
    elif "magazinevoce" in url_lista or "magazineluiza" in url_lista:
        seletor_item = 'a[data-testid="product-card-container"], [data-testid="product-card-container"]'

    try:
        print(f"| ⏳ Aguardando títulos aparecerem no HTML...")
        if "magazinevoce" in url_lista or "magazineluiza" in url_lista:
            # ✨ A MÁGICA AQUI: O robô agora é obrigado a esperar o <h2> do título aparecer, e não a caixa vazia!
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="product-title"]'))
            )
        else:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, seletor_item))
            )
    except:
        print(f"| ⚠️ Timeout. O site não carregou os elementos a tempo.")
    
    # Damos mais 2 segundinhos só para garantir que os preços também carregaram
    time.sleep(2)
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    itens_lista = soup.select(seletor_item)
    
    print(f"| 🔍 DEBUG: O robô encontrou {len(itens_lista)} blocos HTML com esse seletor.")
    
    produtos_encontrados = []
    for index, item in enumerate(itens_lista[:max_list_items]):
        # 🕵️ DEBUG EXTREMO: Vai imprimir tudo que tiver dentro da primeira caixa
        if index == 0:
            texto_bruto = item.get_text(separator=' | ', strip=True)
            print(f"| 🕵️ RAIO-X DO ITEM 0: {texto_bruto}")

        try:
            # --- [NOVA LÓGICA DE PREÇO NA VITRINE] ---
            preco_num = None
            if preco_maximo:
                # Tenta encontrar o preço no bloco de texto (o RAIO-X que você viu)
                texto_item = item.get_text(" | ", strip=True)
                # Usa a função que você já tem para converter o texto em número
                preco_num = extrair_valor_numerico(texto_item)

                if preco_num and preco_num > preco_maximo:
                    # Se o preço for maior que o limite, ignora o item agora mesmo!
                    # print(f"| 💸 PNEIRA: Pulando {preco_num} (Limite {preco_maximo})")
                    continue
                
            if item.name == 'a' and item.has_attr('href'):
                link_tag = item
            else:
                link_tag = item.select_one('a')
            
            if link_tag and link_tag.get('href'):
                url_p = link_tag.get('href')
                url_c = dominio_base + url_p if not url_p.startswith('http') else url_p
                
                titulo = ""
                
                # 1. Busca blindada: tenta as tags oficiais da Magalu e KaBuM primeiro
                tit_tag = item.select_one('[data-testid="product-title"]')
                
                if not tit_tag:
                    tit_tag = item.select_one('span.line-clamp-2')
                    
                if not tit_tag:
                    # 2. Tenta achar genéricos, mas PULA a armadilha da "Comissão"
                    for tag in item.select('h2, h3, .name'):
                        texto_temp = tag.get_text(strip=True)
                        if "Comissão" not in texto_temp and len(texto_temp) > 3:
                            tit_tag = tag
                            break
                
                if tit_tag:
                    titulo = tit_tag.get_text(strip=True)
                
                if "Comissão" in titulo:
                    titulo = titulo.split("Comissão")[0].strip()
                
                if not titulo or len(titulo) <= 3:
                    # Se não tem título nas tags de texto, apela para a imagem
                    img_tag = item.select_one('img[data-testid="image"], img')
                    if img_tag:
                        titulo = img_tag.get('title') or img_tag.get('alt') or ""
                
                # 3. Finaliza salvando o produto encontrado
                if titulo and len(titulo) > 3:
                    produtos_encontrados.append({'titulo': titulo, 'url': url_c})
                else:
                    print(f"| ❌ Item ignorado: Título não encontrado.")
            else:
                print(f"| ❌ Item ignorado: Link (href) não encontrado.")
        except Exception as e:
            print(f"| ❌ Erro ao extrair dados de um item: {e}")
            continue
        
    print(f"| ✅ SUCESSO FINAL: {len(produtos_encontrados)} produtos prontos para a fila de envio.")
    return produtos_encontrados

def rastrear_detalhe_produto(produto, driver, alvo):
    url_produto = produto['url']
    print(f"| Analisando detalhe: {produto['titulo']}")

    try:
        driver.get(url_produto)
    except TimeoutException:
        return produto['titulo'], None, None, None, "", False, 0, 0, None, None
    except Exception:
        return produto['titulo'], None, None, None, "", False, 0, 0, None, None

    titulo_final = "Título Desconhecido"
    try:
        # Seletor do seu original (Removida a Shopee)
        elemento_titulo = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.vR6K3w, .vR6K3w, #productTitle"))
        )
        titulo_final = elemento_titulo.text.strip()
    except:
        titulo_final = produto['titulo']
    
    # Filtro anti-comissão no detalhe também
    if "Comissão" in titulo_final:
        titulo_final = titulo_final.split("Comissão")[0].strip()

    try:
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1)
    except: pass

    soup_detalhe = BeautifulSoup(driver.page_source, 'html.parser')

    # CORREÇÃO TÍTULO MAGALU (Sua lógica original)
    if "magazinevoce" in url_produto or "magazineluiza" in url_produto:
        try:
            tit_tag = soup_detalhe.select_one('h1[data-testid="heading-product-title"], h1.header-product__title')
            if tit_tag: titulo_final = tit_tag.get_text(strip=True)
        except: pass

    preco_atual = None
    preco_antigo = None

    try:
        if "amazon" in url_produto:
            seletores_preco = ['.a-price.aok-align-center .a-offscreen', '#price', '#newBuyBoxPrice', '#kindle-price']
            for seletor in seletores_preco:
                elem = soup_detalhe.select_one(seletor)
                if elem:
                    val = extrair_valor_numerico(elem.get_text())
                    if val and val > 0:
                        preco_atual = val; break
            
            elem_antigo = soup_detalhe.select_one('span[data-a-strike="true"] .a-offscreen')
            if not elem_antigo: elem_antigo = soup_detalhe.select_one('#listPrice')
            if elem_antigo:
                preco_antigo = extrair_valor_numerico(elem_antigo.get_text())
        else:
            # Lógica Magalu
            seletores_magalu = [alvo.get("seletor_preco_detalhe"), '[data-testid="price-value"]', '.price-template__text']
            for sel in seletores_magalu:
                if not sel: continue
                elem_preco = soup_detalhe.select_one(sel)
                if elem_preco:
                    val = extrair_valor_numerico(elem_preco.get_text())
                    if val and val > 0:
                        preco_atual = val; break

            elem_antigo = soup_detalhe.select_one('[data-testid="price-original"]')
            if elem_antigo:
                preco_antigo = extrair_valor_numerico(elem_antigo.get_text())
    except: pass

    # --- CAPTURA DE IMAGEM BLINDADA (ATUALIZADA) ---
    image_url = None
    try:
        # 1. Tenta Amazon e Mercado Livre primeiro
        img_elem = soup_detalhe.select_one('img#landingImage, img#imgBlkFront, [data-a-image-name="landingImage"], img.ui-pdp-image')
        if img_elem:
            image_url = img_elem.get('data-zoom') or img_elem.get('data-old-hires') or img_elem.get('src')

        # 2. Se não achou (Magalu e outros), usa os seletores baseados no seu F12
        if not image_url:
            seletores_magalu = [
                'img[data-testid="image-selected-thumbnail"]', # <-- O alvo exato que você mapeou!
                'img[data-testid="image-selected"]', 
                '[data-testid="product-image"] img',
                '[data-testid="image-gallery"] img',
                '.showcase-product__big-img'
            ]
            for sel in seletores_magalu:
                f_elem = soup_detalhe.select_one(sel)
                if f_elem and f_elem.get('src'):
                    image_url = f_elem.get('src')
                    break

        # 3. Tratamento vital de URL (Adiciona https: se o Magalu mandar só //)
        if image_url and image_url.startswith('//'):
            image_url = 'https:' + image_url

        # 4. Tratamento Amazon (Pega a versão em alta resolução)
        if image_url and "amazon" in image_url:
            image_url = re.sub(r'\._AC_.*_\.', '.', image_url)
            
    except Exception as e:
        print(f"| ⚠️ Erro ao capturar imagem: {e}")

    # Cupom (Sua lógica original)
    cupom_codigo = None
    try:
        elem_cupom = soup_detalhe.select_one('input[data-testid="coupon-code-input"]')
        if elem_cupom: cupom_codigo = elem_cupom.get('value')
    except: pass

    # ✅ RETORNO DE 10 VALORES (Obrigatório para o main novo)
    return titulo_final, preco_atual, preco_antigo, image_url, "", True, 0.0, 0, cupom_codigo, None

def rastrear_cupons(url_cupons, driver):
    """
    Rastreia links de ativação e URLs de imagem de cupons usando Selenium.
    """
    print(f"[{time.strftime('%H:%M:%S')}] Iniciando rastreio de cupons (SELENIUM)...")
    
    try:
        driver.get(url_cupons)
        
        SELETOR_CUPOM = "a[data-css-1g36gst]" 
        
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELETOR_CUPOM))
        )
        
        sopa = BeautifulSoup(driver.page_source, 'html.parser')
        
        cupons_encontrados = []
        
        lista_cupons = sopa.find_all('a', {'data-css-1g36gst': True}) 
        
        for cupom_card in lista_cupons:
            link_ativacao = cupom_card.get('href')
            
            img_tag = cupom_card.find('img')
            img_url = img_tag.get('src') if img_tag else None
            
            descricao = 'Desconto/Oferta especial' 
            if img_url:
                match = re.search(r'pmd_([a-zA-Z0-9]+)_', img_url)
                if match:
                    descricao_raw = match.group(1).upper()
                    descricao = f"Cupom: {descricao_raw}"
                    
            if link_ativacao and img_url: 
                print(f"| DEBUG IMAGE URL: {img_url}")
                cupons_encontrados.append({
                    'link_ativacao': link_ativacao,
                    'descricao': descricao,
                    'imagem_url': img_url
                })

        print(f"[{time.strftime('%H:%M:%S')}] Rastreio de cupons concluído. {len(cupons_encontrados)} cupons encontrados.")
        return cupons_encontrados
        
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] ERRO no rastreio de cupons (SELENIUM): {e}")
        return []

    finally:
        pass

def preparar_mensagem_cupons(lista_cupons):
    mensagens_para_envio = []
    for c in lista_cupons:
        mensagem_caption = f"🚨 <b>{c['descricao']}</b> 🚨\n\n"
        mensagem_caption += f"👉 <a href='{c['link_ativacao']}'>CLIQUE AQUI PARA ATIVAR O CUPOM</a>"
        
        mensagens_para_envio.append({
            'mensagem': mensagem_caption,
            'url_link': c['link_ativacao'],
            'image_url': c['imagem_url']
        })
    return mensagens_para_envio

# =========================================================
# FUNÇÕES DE HISTÓRICO E ENVIO
# =========================================================


    
def analisar_historico(arquivo_csv, titulo, preco_atual, preco_antigo=None):
    try:
        # Retornos padrão (veredito vazio para não poluir mensagens normais)
        oportunidade = False
        veredito = ""
        menor_preco = preco_atual

        # 1. GATILHO DE LOJA: O site diz que caiu muito (Blindado contra falsos "De/Por")
        if preco_antigo and preco_atual and preco_antigo > preco_atual:
            desconto_percentual = ((preco_antigo - preco_atual) / preco_antigo) * 100
            if desconto_percentual >= 35: # Exige 35% de desconto real na loja para ativar o alerta
                oportunidade = True
                veredito = f"📉 <b>QUEDA BRUSCA:</b> Minha IA detectou que a loja cortou o preço em {desconto_percentual:.0f}%!"

        # 2. Tenta ler o banco de dados do robô
        import pandas as pd
        import os
        
        if not os.path.exists(arquivo_csv):
            return oportunidade, veredito, preco_atual
            
        df = pd.read_csv(arquivo_csv)
        df_produto = df[df['Produto'] == titulo].copy()

        # Se temos menos de 3 registros, o robô ainda tá "estudando" o produto. Retorna a análise básica.
        if df_produto.shape[0] < 3:
            return oportunidade, veredito, preco_atual
        
        df_produto['Data'] = pd.to_datetime(df_produto['Data'])
        df_produto['Preco'] = df_produto['Preco'].astype(float)

        menor_preco_historico = df_produto['Preco'].min()
        media_3m = df_produto.tail(90)['Preco'].mean()

        # 3. GATILHO DE RECORDE: O preço atual é o menor que o robô já viu na vida!
        if preco_atual < menor_preco_historico:
            preco_formatado = f"{menor_preco_historico:.2f}".replace('.', ',')
            veredito = f"🤖📈 <b>NOVO RECORDE HISTÓRICO:</b> O menor preço que eu já tinha registrado era R$ {preco_formatado}. Bateu o recorde, a hora de comprar é agora!"
            oportunidade = True
            menor_preco = preco_atual
            
        # 4. GATILHO DE MÉDIA: Tá significativamente abaixo do preço normal (pelo menos 15% abaixo)
        elif preco_atual <= (media_3m * 0.85): 
            media_formatada = f"{media_3m:.2f}".replace('.', ',')
            veredito = f"📊 <b>ABAIXO DA MÉDIA:</b> Normalmente esse produto custa R$ {media_formatada} nos meus registros. Tá valendo muito a pena!"
            oportunidade = True
            menor_preco = menor_preco_historico
        
        return oportunidade, veredito, menor_preco
    
    except Exception as e:
        print(f"| ⚠️ Banco de dados em manutenção: {e}")
        return False, "", preco_atual

def enviar_telegram(mensagem_formatada, url_link, image_url=None):
    time.sleep(1)

    if image_url:
        print("[TELEGRAM] Tentando enviar com foto (UPLOAD DE ARQUIVO)...")
        params_photo = {
            'chat_id': TELEGRAM_CHAT_ID,
            'parse_mode': 'HTML',
            'caption': mensagem_formatada
        }

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resposta_img = requests.get(image_url, headers=headers, timeout=10)
            resposta_img.raise_for_status()

            img_bytes = io.BytesIO(resposta_img.content)
            files = {'photo': ('cupom.png', img_bytes)}
            url_api = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'

            resposta = requests.post(url_api, data=params_photo, files=files, timeout=15)
            resposta.raise_for_status()

            print("[TELEGRAM] Mensagem enviada com imagem (upload de arquivo) com sucesso!")
            return
        
        except requests.exceptions.HTTPError as e:
            print(f"[ALERTA] Falha no download ou upload da imagem ({e}). Tentando fallback (sendMessage).")
        except Exception as e:
            print(f"[ALERTA] Erro desconhecido no sendPhoto com upload: {e}. Tentando fallback.")

    print(f"[DEBUG MENSAGEM] Tentando enviar o texto: {mensagem_formatada}")

    print("[TELEGRAM] Enviando como mensagem de texto simples (sendMessage)...")
    params_fallback = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': mensagem_formatada,
        'parse_mode': 'HTML'
    }

    url_api = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'

    try:
        resposta = requests.post(url_api, data=params_fallback, timeout=10)
        resposta.raise_for_status()
        print("[TELEGRAM] Mensagem enviada como texto para o grupo com sucesso!")

    except Exception as e:
        print(f"[ERRO CRÍTICO] Falha total ao enviar mensagem para o Telegram> {e}")

def limpar_interface_whatsapp(driver):
    """Garante que não há modais ou caixas de texto abertas travando a interface."""
    # print("| 🧹 Limpando interface do WhatsApp...")
    try:
        action = ActionChains(driver)
        action.send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)
        action.send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)
        
        # Tenta clicar no botão X (fechar) se ele estiver visível
        botoes_fechar = driver.find_elements(By.XPATH, '//span[@data-icon="x-viewer"] | //div[@aria-label="Fechar"] | //span[@data-icon="x"]')
        for btn in botoes_fechar:
            try:
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
            except: pass
            
    except: pass

# =========================================================
# CONTROLE DE DUPLICIDADE (CACHE) - arquivo definido no topo via ARQUIVO_CACHE_ENVIOS
# =========================================================


# =========================================================
# FUNÇÕES PRINCIPAIS DE ENVIO (DETERMINAM TIPO DINAMICAMENTE)
# =========================================================

def enviar_whatsapp(driver, nome_grupo, mensagem):
    """Envia mensagem de texto simples para um Grupo ou Canal."""
    eh_canal = nome_grupo.startswith("[CANAL]")
    nome_final_chat = nome_grupo.replace("[CANAL]", "").strip()

    if eh_canal:
        # Se é canal, use a função dedicada de canais
        sucesso = enviar_canal_exclusivo(driver, nome_final_chat, mensagem)
        if sucesso:
            print(f"| ✅ Canal enviado com sucesso!")
        else:
            print(f"| ⚠️ Canal falhou, mas tentou voltar para Conversas")
        return sucesso

    # Se é grupo, use o fluxo de envio em grupos
    tipo_log = "WHATSAPP"
    print(f"| 🟢 {tipo_log}: Iniciando envio (Sem Foto) para '{nome_final_chat}'...")

    aba_origem = driver.current_window_handle

    if not focar_aba_whatsapp(driver):
        return

    limpar_interface_whatsapp(driver)

    try:
        # Procura e abre o grupo pelo nome
        xpath_pesquisa = '//input[@role="textbox"][@aria-label="Pesquisar ou começar uma nova conversa"]'
        caixa_pesquisa = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpath_pesquisa))
        )
        caixa_pesquisa.click()
        time.sleep(0.5)
        caixa_pesquisa.send_keys(Keys.CONTROL + "a")
        caixa_pesquisa.send_keys(Keys.BACKSPACE)
        caixa_pesquisa.send_keys(nome_final_chat)
        print(f"| ✍️ Procurando grupo: '{nome_final_chat}'")
        time.sleep(2.5)

        # Clica no primeiro resultado - com melhor tratamento
        try:
            primeiro_resultado = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@role="listitem"][1]'))
            )
            driver.execute_script("arguments[0].click();", primeiro_resultado)
            print(f"| ✅ Grupo aberto pelo resultado da busca")
        except:
            print(f"| ⚠️ Tentando Enter para abrir grupo...")
            caixa_pesquisa.send_keys(Keys.ENTER)

        time.sleep(3)  # Aguarda o chat carregar

        # Foca na caixa de texto do chat
        xpath_caixa_texto = '//div[@id="main"]//div[@contenteditable="true"]'
        msg_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, xpath_caixa_texto))
        )

        msg_box.click()
        time.sleep(0.5)
        msg_box.send_keys(Keys.CONTROL + "a")
        msg_box.send_keys(Keys.BACKSPACE)

        print("| ⏳ Passo 4: Colando a mensagem...")
        msg_final = formatar_para_whatsapp(mensagem)
        simular_digitacao(driver, msg_box, msg_final)

        print("| ⏳ Aguardando 5 segundos para o WhatsApp gerar o Link Preview...")
        time.sleep(5)

        msg_box.send_keys(Keys.ENTER)
        print(f"| ✅ {tipo_log}: Mensagem enviada com sucesso!")
        human_delay(2, 5)
        return True

    except Exception as e:
        print(f"| ❌ {tipo_log}: Erro ao enviar mensagem: {e}")
        return False

    finally:
        limpar_interface_whatsapp(driver)
        # NÃO volta para aba original aqui - deixa no WhatsApp para o próximo grupo/canal


def enviar_whatsapp_robusto(driver, nome_grupo, mensagem, caminho_imagem):
    """Envia imagem com legenda para um Grupo ou Canal."""
    eh_canal = nome_grupo.startswith("[CANAL]")
    nome_final_chat = nome_grupo.replace("[CANAL]", "").strip()

    if eh_canal:
        # Se é canal, use a função dedicada de canais
        sucesso = enviar_canal_exclusivo(driver, nome_final_chat, mensagem, caminho_imagem)
        if sucesso:
            print(f"| ✅ Canal com foto enviado com sucesso!")
        else:
            print(f"| ⚠️ Canal com foto falhou, mas tentou voltar para Conversas")
        return sucesso

    # Se é grupo, use o fluxo de envio com foto em grupos
    tipo_log = "WHATSAPP"
    print(f"| 📸 {tipo_log}: Iniciando entrega com foto para '{nome_final_chat}'...")

    aba_origem = driver.current_window_handle

    if not focar_aba_whatsapp(driver):
        return

    try:
        # Procura e abre o grupo pelo nome
        xpath_pesquisa = '//input[@role="textbox"][@aria-label="Pesquisar ou começar uma nova conversa"]'
        caixa_pesquisa = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpath_pesquisa))
        )
        caixa_pesquisa.click()
        time.sleep(0.5)
        caixa_pesquisa.send_keys(Keys.CONTROL + "a")
        caixa_pesquisa.send_keys(Keys.BACKSPACE)
        caixa_pesquisa.send_keys(nome_final_chat)
        print(f"| ✍️ Procurando grupo: '{nome_final_chat}'")
        time.sleep(2.5)

        # Clica no primeiro resultado - com melhor tratamento
        try:
            primeiro_resultado = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@role="listitem"][1]'))
            )
            driver.execute_script("arguments[0].click();", primeiro_resultado)
            print(f"| ✅ Grupo aberto pelo resultado da busca")
        except:
            print(f"| ⚠️ Tentando Enter para abrir grupo...")
            caixa_pesquisa.send_keys(Keys.ENTER)

        time.sleep(3)  # Aguarda o chat carregar

        # Cola a imagem do Clipboard
        copiar_imagem_para_clipboard(caminho_imagem)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

        print("| ⏳ Aguardando editor de legenda...")
        time.sleep(3)  # Tempo maior para o modal carregar

        # Múltiplos seletores para encontrar o campo de legenda
        xpath_legenda_opcoes = [
            '//div[@aria-label="Adicionar legenda"]',
            '//div[contains(@aria-label, "legenda")]',
            '//span[text()="Adicionar legenda"]/../following-sibling::div//div[@contenteditable="true"]',
            '//div[@role="dialog"]//div[@contenteditable="true"]',
            '//div[contains(@class, "modal")]//div[@contenteditable="true"]',
            '//div[@data-testid="chat-input"]//div[@contenteditable="true"]',
            '//div[@role="textbox"][@contenteditable="true"]',
            '//div[@id="main"]//div[@contenteditable="true"]'
        ]

        legenda_box = None
        for xpath in xpath_legenda_opcoes:
            try:
                legenda_box = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                print(f"| ✅ Campo de legenda encontrado com seletor: {xpath[:50]}...")
                break
            except:
                continue

        if not legenda_box:
            print("| ⚠️ Campo de legenda não encontrado, tentando element ativo...")
            time.sleep(1)
            legenda_box = driver.switch_to.active_element
            if not legenda_box or legenda_box.tag_name == "body":
                raise Exception("Campo de legenda não encontrado e elemento ativo é inválido")

        driver.execute_script("arguments[0].focus();", legenda_box)
        time.sleep(0.5)

        legenda_box.send_keys(Keys.CONTROL + "a")
        legenda_box.send_keys(Keys.BACKSPACE)
        time.sleep(0.5)

        msg_final = formatar_para_whatsapp(mensagem)
        pyperclip.copy(msg_final)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

        human_delay(1, 3)
        print(f"| 🚀 Disparando o ENVIO para o {tipo_log}...")

        try:
            legenda_box.send_keys(Keys.ENTER)
            human_delay(1, 2)
        except: pass

        # Cliques físicos de garantia
        seletores_enviar = ['//div[@aria-label="Enviar"]', '//span[@data-icon="send"]', '//button[contains(@aria-label, "Enviar")]', '//span[@data-icon="send-light"]/..']
        for seletor in seletores_enviar:
            botoes = driver.find_elements(By.XPATH, seletor)
            if botoes:
                print(f"| 🎯 Botão 'Enviar' encontrado ({seletor})! Clicando...")
                driver.execute_script("arguments[0].click();", botoes[0])
                time.sleep(1)
                break

        try:
            modal_aberto = driver.find_elements(By.XPATH, '//span[@data-icon="x-viewer"]')
            if modal_aberto:
                print("| 🛠️ Modal ainda aberto. Tentando Enter forçado no elemento ativo...")
                driver.switch_to.active_element.send_keys(Keys.ENTER)
        except: pass

        time.sleep(2)
        print(f"| ✅ {tipo_log}: Missão cumprida!")
        return True

    except Exception as e:
        print(f"| ❌ {tipo_log}: Erro no envio robusto: {e}")
        try:
            botao_fechar = driver.find_element(By.XPATH, '//span[@data-icon="x-viewer"]')
            botao_fechar.click()
        except: pass
        return False

    finally:
        limpar_interface_whatsapp(driver)
        # NÃO volta para aba original aqui - deixa no WhatsApp para o próximo grupo/canal
        # driver.switch_to.window(aba_origem)  # ← Removido para manter na aba do WhatsApp

def normalizar_texto(texto):
    """LIMPEZA PROFUNDA: Remove espaços, pontuação e converte para minúsculo."""
    if not texto: return ""
    # Remove caracteres especiais se quiser ser radical (opcional)
    # Mas só strip e lower já resolvem 99%
    return texto.strip().lower()

def verificar_se_ja_enviou_24h(titulo, grupo=None):
    """
    Retorna True se o produto já foi enviado nas últimas N segundos (CACHE_RETENCAO_SECONDS).
    Se 'grupo' for informado, verifica POR GRUPO (permite repetir em outro grupo).
    """
    titulo_chave = normalizar_texto(titulo)
    if grupo:
        titulo_chave = f"{grupo}::{titulo_chave}"
    cache = carregar_cache()
    
    if titulo_chave not in cache:
        return False
    
    timestamp_envio = cache[titulo_chave]
    agora = time.time()
    
    if (agora - timestamp_envio) < CACHE_RETENCAO_SECONDS:
        horas_restantes = (CACHE_RETENCAO_SECONDS - (agora - timestamp_envio)) / 3600
        print(f"| ⏳ CACHE: '{titulo[:20]}...' bloqueado por mais {horas_restantes:.1f}h.")
        return True
    else:
        del cache[titulo_chave]
        salvar_cache(cache)
        return False

def registrar_envio_24h(titulo, grupo=None, url=None):
    """Registra no cache tanto pelo título quanto (opcional) pela URL do produto.

    Isso permite pular itens futuros com base na URL/ID sem abrir o produto.
    """
    def _salvar_chave(chave, cache):
        cache[chave] = time.time()

    cache = carregar_cache()

    # Salva chave baseada no título
    titulo_chave = normalizar_texto(titulo)
    if grupo:
        titulo_chave = f"{grupo}::{titulo_chave}"
    _salvar_chave(titulo_chave, cache)

    # Se fornecer URL, também salva uma chave baseada na URL limpa (sem query)
    if url:
        try:
            parsed = urllib.parse.urlparse(url)
            cleaned = parsed._replace(query="").geturl()
            chave_url = normalizar_texto(cleaned)
            if grupo:
                chave_url = f"{grupo}::{chave_url}"
            _salvar_chave(chave_url, cache)
            print(f"| 💾 MEMÓRIA: URL também salva no cache: {cleaned}")
        except Exception:
            pass

    salvar_cache(cache)
    print(f"| 💾 MEMÓRIA: '{titulo[:20]}...' salvo no cache.")

def main(alvos_a_rodar, preco_maximo=None):
    if preco_maximo:
        print(f"--- ASSISTENTE INTELIGENTE INICIADO (⚡ RELÂMPAGO ATÉ R${preco_maximo:.0f}) ---")
    else:
        print("--- ASSISTENTE INTELIGENTE INICIADO (MODO NAVEGAÇÃO DIRETA) ---")

    # --- NOVO TRECHO DE CÓDIGO: LÓGICA DE PULAR ---
    categorias_para_pular = []
    if "--pular" in sys.argv:
        try:
            # Pega tudo que vem depois da palavra '--pular'
            indice_pular = sys.argv.index("--pular")
            # Converte para maiúsculo para garantir (ex: moveis -> MOVEIS)
            categorias_para_pular = [x.upper() for x in sys.argv[indice_pular + 1:]]
            print(f"| 🚫 MODALIDADE FILTRO ATIVA: Pulando {categorias_para_pular}")
        except: pass
    # ----------------------------------------------

    driver = iniciar_driver()
    
    # --- CORREÇÃO: SEPARAÇÃO BLINDADA DE ABAS (ATUALIZADO) ---
    aba_whatsapp = focar_aba_whatsapp(driver)
    
    if aba_whatsapp:
        print("| ✅ WhatsApp isolado e mapeado com segurança.")
    else:
        print("| ⚠️ Falha crítica ao mapear ou abrir o WhatsApp.")

    # 2. Garante que a aba de trabalho (vitrine) NÃO é o WhatsApp
    if driver.current_window_handle == aba_whatsapp:
        print("| 🔄 Criando aba exclusiva para caçar ofertas...")
        driver.execute_script("window.open('about:blank', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        
    aba_navegacao = driver.current_window_handle 
    # ---------------------------------------------------------

    CATEGORIAS_ALERTADAS = set()
    PRODUTOS_PROCESSADOS_HOJE = set() 

    try: 
        # CABEÇALHO DO TURNO RELÂMPAGO
        if preco_maximo:
            CABECALHOS_RELAMPAGO = {
                50: "⚡ <b>TURNO RELÂMPAGO: TUDO ATÉ R$50!</b>\n🎯 Só achadinhos que cabem no bolso! Confira 👇",
                100: "⚡ <b>TURNO RELÂMPAGO: OFERTAS ATÉ R$100!</b>\n🔥 Seleção especial com preços imbatíveis 👇",
                200: "⚡ <b>TURNO RELÂMPAGO: SELEÇÃO ATÉ R$200!</b>\n🛍️ Os melhores produtos com desconto real 👇",
            }
            msg_relampago = CABECALHOS_RELAMPAGO.get(
                int(preco_maximo),
                f"⚡ <b>TURNO RELÂMPAGO: TUDO ATÉ R${preco_maximo:.0f}!</b>\n🏷️ Ofertas selecionadas só pra você 👇"
            )
            enviar_telegram(msg_relampago, None, None)
            
            # CORREÇÃO: Cabeçalho relâmpago com tratamento de nomes limpos para o WhatsApp
            for grupo in GRUPOS_ALVO:
                try: 
                    eh_canal_inicial = grupo.startswith("[CANAL]")
                    nome_limpo_inicial = grupo.replace("[CANAL]", "").strip() if eh_canal_inicial else grupo.strip()
                    
                    if eh_canal_inicial:
                        enviar_canal_exclusivo(driver, nome_limpo_inicial, msg_relampago, None)
                    else:
                        enviar_whatsapp(driver, nome_limpo_inicial, msg_relampago)
                except: pass
            time.sleep(2)

        # LOOP PRINCIPAL DE LOJAS/LISTAS
        for alvo in alvos_a_rodar:
            categoria_atual = alvo.get('categoria', '').upper()
            if categoria_atual in categorias_para_pular:
                print(f"| ⏭️ SKIPPED: Categoria '{categoria_atual}' ignorada.")
                continue

            try: driver.switch_to.window(aba_navegacao)
            except: pass

            if alvo.get("loja") == "MERCADOLIVRE":
                processar_feed_mercadolivre(driver, alvo, PRODUTOS_PROCESSADOS_HOJE, preco_maximo=preco_maximo)
                continue
            
            # TODO: Adicionar raspagem da Shopee aqui
            # Quando integrado, usar estrutura similar ao ML com extração de preço, título e link de afiliado
            # Link modelo: https://shopee.com.br/search?keyword=...&data=produtos
            # Afiliado: usar shope.ee ou link universal da Shopee
            
            nome_categoria = alvo['categoria']
            print(f"\n======== {alvo['nome']} ({nome_categoria}) ========")

            try:
                OFERTAS_DINAMICAS = rastrear_lista_produtos(
                    alvo['url_lista'], driver, alvo['seletor_item_lista'],
                    alvo['seletor_link_lista'], alvo['dominio_base'],
                    max_list_items=40 
                )
            except Exception as e:
                print(f"| ❌ Erro ao ler lista: {e}")
                continue

            if not OFERTAS_DINAMICAS: continue
            
            ofertas_unicas = []
            urls_vistas = set()
            for o in OFERTAS_DINAMICAS:
                if o['url'] not in urls_vistas:
                    ofertas_unicas.append(o)
                    urls_vistas.add(o['url'])
            
            print(f"| ENCONTRADOS: {len(ofertas_unicas)} itens únicos.")

            PRODUTOS_VALIDOS = 0
            INDICE = 0
            
            while PRODUTOS_VALIDOS < 5 and INDICE < len(ofertas_unicas):
                driver.switch_to.window(aba_navegacao)
                produto = ofertas_unicas[INDICE]
                INDICE += 1

                # Filtro de cache rápido (Verifica apenas no grupo principal para ver se o item é novo)
                grupo_principal = GRUPOS_ALVO[0].replace("[CANAL]", "").strip()
                if verificar_se_ja_enviou_24h(produto['titulo'], grupo_principal):
                    print(f"| ⏭️ PANTALHA: '{produto['titulo'][:25]}...' já enviado. Próximo...")
                    continue

                try:
                    driver.get(produto['url'])
                except: continue
                
                titulo, preco_atual, preco_antigo, image_url, nome_autor, passou_filtro, nota, qtd_reviews, cupom_cod, cupom_val = rastrear_detalhe_produto(
                    produto, driver, alvo
                )

                # Geração de link curto
                url_final = None
                if alvo.get("loja") == "AMAZON":
                    url_final = gerar_link_amazon_sitestripe(driver)
                elif alvo.get("loja") == "MAGALU" or "magazine" in alvo.get("url_lista", ""):
                    url_final = gerar_link_magalu_oficial(driver)
                    if not url_final: url_final = gerar_link_afiliado(produto['url'], "MAGALU")
                elif alvo.get("loja") in ["KABUM", "ALIEXPRESS"]:
                    url_final = gerar_link_afiliado(produto['url'], alvo.get("loja"))
                else:
                    url_final = gerar_link_afiliado(produto['url'], "MAGALU")

                if not url_final or not passou_filtro or preco_atual is None:
                    continue

                if preco_maximo and preco_atual > preco_maximo:
                    continue

                # Montagem e envio da mensagem
                chamada = gerar_chamada_inteligente(titulo, preco_atual, alvo.get("categoria", ""), nome_autor)
                oportunidade, veredito, menor_preco = analisar_historico(ARQUIVO_HISTORICO, titulo, preco_atual, preco_antigo)
                atualizar_historico(ARQUIVO_HISTORICO, titulo, preco_atual)

                mensagem_final = f"<b>{chamada}</b>\n\n"

                if oportunidade:
                    mensagem_final += f"🚨 <b>{veredito}</b> 🚨\n\n"
                    
                mensagem_final += f"📦 {titulo.strip()}\n\n"
                
                if preco_antigo and preco_atual and preco_antigo > preco_atual:
                    desconto = int(((preco_antigo - preco_atual) / preco_antigo) * 100)
                    mensagem_final += f"❌ <s>De: {formatar_preco_br(preco_antigo)}</s>\n"
                    mensagem_final += f"✅ <b>Por: {formatar_preco_br(preco_atual)}</b> ({desconto}% OFF) 📉\n"
                elif preco_atual:
                    mensagem_final += f"✅ <b>Preço Especial: {formatar_preco_br(preco_atual)}</b> 💰\n"
                    
                if nota > 0:
                    mensagem_final += f"⭐ <b>Avaliação:</b> {nota}/5.0\n"

                if cupom_cod:
                    mensagem_final += f"\n🎟️ <b>Use o cupom: {cupom_cod}</b>\n"

                mensagem_final += f"\n🛒 <b>COMPRE AQUI:</b> 👇\n<a href='{url_final}'>CLIQUE PARA VER NO SITE</a>"

                # 1. Envia para o Telegram primeiro
                enviar_telegram(mensagem_final, url_final, image_url)
                
                teve_envio_real = False
                
                # 2. Tenta baixar a foto
                caminho_foto = None
                if image_url:
                    caminho_foto = baixar_imagem_temporaria(image_url)

                try:
                    # ASSEGURA QUE O ROBÔ VOLTOU PARA A ABA DO WHATSAPP
                    whatsapp_encontrado = False
                    for handle in driver.window_handles:
                        try:
                            driver.switch_to.window(handle)
                            if "whatsapp" in driver.title.lower() or "web.whatsapp" in driver.current_url:
                                whatsapp_encontrado = True
                                aba_whatsapp = handle
                                break
                        except:
                            continue
                    
                    if not whatsapp_encontrado:
                        print(f"| ⚠️ Alerta: Não consegui pular para a aba do WhatsApp.")
                        continue
                    
                    # ==========================================================
                    # 🚀 ETAPA 1: ENVIO OBRIGATÓRIO PARA O GRUPO TRADICIONAL
                    # ==========================================================
                    nome_grupo_tradicional = "Achadinhos da Celle • AI"
                    sucesso_grupo = False
                    
                    try:
                        print("| 🔄 Garantindo foco na aba de Conversas normais...")
                        xpath_aba_conversas = '//*[local-name()="title" and contains(text(), "wds-ic-chat")]/ancestor::button | //*[local-name()="title" and contains(text(), "wds-ic-chat")]/ancestor::span'
                        botao_conversas = WebDriverWait(driver, 12).until(
                            EC.presence_of_element_located((By.XPATH, xpath_aba_conversas))
                        )
                        driver.execute_script("arguments[0].click();", botao_conversas)
                        time.sleep(2)

                        print(f"| 🔍 Buscando na lista de chats o grupo: '{nome_grupo_tradicional}'...")
                        
                        xpath_caixa_busca = '//input[@role="textbox"][@aria-label="Pesquisar ou começar uma nova conversa"] | //input[@data-tab="3"]'
                        caixa_busca = WebDriverWait(driver, 12).until(
                            EC.presence_of_element_located((By.XPATH, xpath_caixa_busca))
                        )
                        caixa_busca.click()
                        time.sleep(0.5)
                        
                        caixa_busca.send_keys(Keys.CONTROL + "a")
                        caixa_busca.send_keys(Keys.BACKSPACE)
                        caixa_busca.send_keys(nome_grupo_tradicional)
                        time.sleep(2)
                        
                        caixa_busca.send_keys(Keys.ENTER)
                        print("| ⌨️ Pressionado ENTER para abrir o grupo.")
                        time.sleep(3)
                        
                        xpath_caixa_texto = '//div[@id="main"]//div[@contenteditable="true"] | //footer//div[@contenteditable="true"]'
                        msg_box = WebDriverWait(driver, 12).until(
                            EC.presence_of_element_located((By.XPATH, xpath_caixa_texto))
                        )
                        msg_box.click()
                        time.sleep(0.5)

                        if caminho_foto and os.path.exists(caminho_foto):
                            print("| 📸 Preparando imagem e jogando para a Área de Transferência...")
                            copiar_imagem_para_clipboard(caminho_foto) 
                            time.sleep(1)
                            
                            msg_box.send_keys(Keys.CONTROL + "v")
                            print("| 📋 Imagem colada no container do grupo!")
                            time.sleep(3.5)
                            
                            xpath_legenda = '//div[contains(@class, "lexical-rich-text-input")]//div[@contenteditable="true"]'
                            msg_box = WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, xpath_legenda))
                            )
                            msg_box.click()

                        msg_final_whats = formatar_para_whatsapp(mensagem_final)
                        simular_digitacao(driver, msg_box, msg_final_whats)
                        time.sleep(1.5)
                        
                        msg_box.send_keys(Keys.ENTER)
                        print(f"| 🚀 Sucesso! Oferta enviada para o grupo: '{nome_grupo_tradicional}'")
                        sucesso_grupo = True
                        teve_envio_real = True
                        time.sleep(3)
                        
                    except Exception as e_txt:
                        print(f"| ❌ Erro ao processar envio para o grupo: {e_txt}")
                        sucesso_grupo = False

                    # ==========================================================
                    # 📢 ETAPA 2: ENVIO IMEDIATO PARA O CANAL (LOGO EM SEGUIDA!)
                    # ==========================================================
                    if sucesso_grupo:
                        print("| 📢 Acionando gatilho imediato para o Canal da Celle...")
                        # Dispara a função do canal que criamos
                        enviar_canal_exclusivo(driver, nome_grupo_tradicional, mensagem_final, caminho_foto)
                        
                        # Salva o produto na memória para não repetir (inclui link final quando possível)
                        try:
                            registrar_envio_24h(titulo, nome_grupo_tradicional, url=url_final)
                        except Exception:
                            registrar_envio_24h(titulo, nome_grupo_tradicional)
                        human_delay(DELAY_MIN_ENTRE_MENSAGENS, DELAY_MAX_ENTRE_MENSAGENS)
                                    
                    if teve_envio_real:
                        PRODUTOS_VALIDOS += 1
                        print(f"| ✅ Sucesso ({alvo['nome']}): {PRODUTOS_VALIDOS}/5")
                finally:
                    # Limpa arquivos residuais temporários
                    if caminho_foto and os.path.exists(caminho_foto):
                        try: os.remove(caminho_foto)
                        except: pass
                    # Retorna o foco do driver para a aba de ofertas
                    try: driver.switch_to.window(aba_navegacao)
                    except: pass

    except Exception as e:
        print(f"| ❌ Erro Crítico no processamento geral: {e}")

    finally:
        print("--- FIM DO TURNO ---")

if __name__ == "__main__":

    try:
        ARGUMENTO_PRINCIPAL = sys.argv[1]
    except IndexError:
        ARGUMENTO_PRINCIPAL = "MULHER" 
    
    if ARGUMENTO_PRINCIPAL == "--cupons":
        URL_CUPONS = 'https://especiais.magazineluiza.com.br/magazinevoce/cupons/?showcase=magazinecelle'
        print(f"\n| === MODO CUPONS AGENDADO: {time.strftime('%H:%M:%S')} === |")
        
        driver = iniciar_driver() 
        try:
            cupons = rastrear_cupons(URL_CUPONS, driver)
            lista_mensagens = preparar_mensagem_cupons(cupons)
            
            if lista_mensagens:
                for item in lista_mensagens:
                    enviar_telegram(
                        mensagem_formatada=item['mensagem'], 
                        url_link=item['url_link'], 
                        image_url=item['image_url']
                    )
            else:
                print("| NENHUM CUPOM: Nenhum cupom novo encontrado neste turno.")
        finally:
            if driver: driver.quit()
        sys.exit(0)

    else:
        GRUPO_ATUAL = ARGUMENTO_PRINCIPAL.upper()
        LISTA_ALVOS_A_RODAR = []

        if GRUPO_ATUAL == "MULHER" or GRUPO_ATUAL == "FEMININO":
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_FEMININA
        elif GRUPO_ATUAL == "TODOS" or GRUPO_ATUAL == "GERAL":
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_MAGALU + LISTA_MESTRE_AMAZON + LISTA_MESTRE_ML + LISTA_MESTRE_FEMININA + LISTA_MESTRE_KABUM + LISTA_MESTRE_ALIEXPRESS
        elif GRUPO_ATUAL == "AMAZON":
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_AMAZON
        elif GRUPO_ATUAL == "ML" or GRUPO_ATUAL == "MERCADOLIVRE":
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_ML
        
        # --- AQUI ESTÁ O SEU BLOCO NOVO PARA TESTAR A AWIN ---
        elif GRUPO_ATUAL == "AWIN":
            print(f"🕒 Iniciando teste focado na AWIN (KaBuM e AliExpress)...")
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_KABUM + LISTA_MESTRE_ALIEXPRESS
            main(LISTA_ALVOS_A_RODAR)
            sys.exit(0)
        # -----------------------------------------------------

        elif GRUPO_ATUAL.startswith("RELAMPAGO"):
            try:
                PRECO_LIMITE_RELAMPAGO = float(GRUPO_ATUAL.replace("RELAMPAGO", ""))
                LISTA_ALVOS_A_RODAR = LISTA_MESTRE_ML + LISTA_MESTRE_AMAZON + LISTA_MESTRE_MAGALU
                main(LISTA_ALVOS_A_RODAR, preco_maximo=PRECO_LIMITE_RELAMPAGO)
                sys.exit(0)
            except ValueError:
                sys.exit(1)
        elif GRUPO_ATUAL.startswith("MAGALU") and any(c.isdigit() for c in GRUPO_ATUAL):
            try:
                preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL)) 
                main(LISTA_MESTRE_MAGALU, preco_maximo=preco_limite)
            except: pass
        elif GRUPO_ATUAL.startswith("AMAZON") and any(c.isdigit() for c in GRUPO_ATUAL):
            try:
                preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL))
                main(LISTA_MESTRE_AMAZON, preco_maximo=preco_limite)
            except: pass
        elif GRUPO_ATUAL.startswith("ML") and any(c.isdigit() for c in GRUPO_ATUAL):
            try:
                preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL))
                main(LISTA_MESTRE_ML, preco_maximo=preco_limite)
                sys.exit(0) 
            except: pass
        else:
            print(f"🕒 Configurando turno estratégico: {GRUPO_ATUAL}")
            alvos_magalu = selecionar_alvos_por_grupo(LISTA_MESTRE_MAGALU, GRUPO_ATUAL)
            alvos_amazon = selecionar_alvos_por_grupo(LISTA_MESTRE_AMAZON, GRUPO_ATUAL)
            alvos_ml = selecionar_alvos_por_grupo(LISTA_MESTRE_ML, GRUPO_ATUAL)
            alvos_fem = selecionar_alvos_por_grupo(LISTA_MESTRE_FEMININA, GRUPO_ATUAL)
            alvos_kabum = selecionar_alvos_por_grupo(LISTA_MESTRE_KABUM, GRUPO_ATUAL)
            alvos_ali = selecionar_alvos_por_grupo(LISTA_MESTRE_ALIEXPRESS, GRUPO_ATUAL)
            
            LISTA_ALVOS_A_RODAR = alvos_magalu + alvos_amazon + alvos_ml + alvos_fem + alvos_kabum + alvos_ali

        num_alvos = len(LISTA_ALVOS_A_RODAR)
        
        if num_alvos == 0:
            main(LISTA_MESTRE_FEMININA)
        else:
            main(LISTA_ALVOS_A_RODAR)