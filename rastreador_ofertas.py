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
ARQUIVO_HISTORICO = "historico_ofertas.csv"
AQUIVO_CACHE_ENVIO = "cache_envios_24h.json"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

GRUPOS_ALVO = ["Achadinhos da Celle • AI"]

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

def verificar_se_ja_enviou_24h(titulo, grupo=None):
    chave = f"{grupo}::{titulo.strip().lower()}" if grupo else titulo.strip().lower()
    cache = carregar_cache()
    cache[chave] = time.time()
    salvar_cache(cache)

def atualizar_historico(arquivo_csv, titulo, preco_coletado):
    if not preco or preco <= 0: return
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    nova_linha = pd.DataFrame([{'Data': data_hoje, 'Preco': preco, 'Produto': titulo}])
    if not os.path.exists(ARQUIVO_HISTORICO):
        nova_linha.to_csv(ARQUIVO_HISTORICO, index=False)
    else:
        df = pd.read_csv(ARQUIVO_HISTORICO)
        if not ((df['Produto'] == titulo) & (df['Data'] == data_hoje)).any():
            pd.concat([df, nova_linha]).to_csv(ARQUIVO_HISTORICO, index=False)

# --- CORE DO RASTREADOR (RPA) ---

def iniciar_driver():
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    except:
        options = Options()
        options.add_argument("--start-maximized")
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)     

def focar_aba_whatsapp(driver):
    print("| 🔍 Procurando aba do WhatsApp...")
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        time.sleep(1)
        if "whatsapp" in driver.title.lower() or "web.whatsapp" in driver.current_url:
            driver.execute_script("window.focus();")
            return True
    return False

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
    """Verifica se o título contém algum termo da lista de bloqueio."""
    if not titulo: return False
    titulo_lower = titulo.lower()
    for termo in TERMOS_BLOQUEADOS:
        if termo.lower() in titulo_lower:
            return True
    return False

def gerar_chamada_inteligente(titulo, preco_atual, categoria="", autor=""):
    """Lê o título, o preço e a categoria para criar uma frase de impacto com a persona do Robô da Celle."""
    import random 
    import re
    
    if not titulo: return random.choice(["🤖 Bi-bi-bop! ALERTA DE OFERTA!", "🚨 ACHADINHO LIBERADO PELA CELLE!"])
    
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
            "A Celle me avisou: setup de respeito pra não ter desculpa quando perder no Cuphead! 🎮✨", 
            "Conforto imbatível pra não colocar a culpa do lag em mim! 🛋️🎮",
            "Pra não queimar a cozinha no Overcooked e jogar de boa! 🎮🍳"
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
        
    # 10. SALA VIP: SUPERMERCADO E LIMPEZA (Foco na necessidade e entrega rápida)
    if categoria_upper == "SUPERMERCADO" or re.search(r'\b(azeite|café|cafe|cápsula|sabão|sabao|omo|ariel|amaciante|papel higiênico|fralda|leite|nutella|limpeza|veja)\b', titulo_lower):
        
        # Sub-nicho: Azeite (Ouro líquido - Gatilho de alívio)
        if "azeite" in titulo_lower:
            return random.choice([
                "O roubo do azeite acabou! Minha IA farejou esse preço justo pra você fazer o estoque! 🫒📉",
                "Alerta de ouro líquido na promoção! Pode colocar no carrinho sem medo de chorar! ✨🛒"
            ])
            
        # Sub-nicho: Café (Combustível - Piada com a persona do robô/tech)
        elif re.search(r'\b(café|cafe|cápsula|nespresso|três corações|dolce gusto)\b', titulo_lower):
            return random.choice([
                "Combustível de humano detectado com sucesso! Seus níveis de bateria agradecem (e o bolso também)! ☕🤖",
                "Pra garantir a energia do dia a dia (e aguentar a rotina) com desconto! ⚡☕"
            ])
            
        # Sub-nicho: Fraldas (Gatilho de utilidade máxima e economia)
        elif "fralda" in titulo_lower:
            return random.choice([
                "Atenção mamães e papais: hora de fazer o estoque! Fralda no precinho pra salvar o orçamento do mês! 👶💸",
                "Meus processadores calcularam: essa promo de fralda tá valendo muito a pena! 🍼📉"
            ])
            
        # Sub-nicho: Limpeza / Sabão (Gatilho de dona de casa/rotina)
        elif re.search(r'\b(sabão|sabao|omo|ariel|amaciante|veja|detergente)\b', titulo_lower):
            return random.choice([
                "Manutenção da base ativada! Estoque de limpeza garantido sem pesar no bolso! 🧼✨",
                "O fim do sofrimento no supermercado! Produto de primeira pesado chegando direto na sua porta! 🧺📉"
            ])
            
        # Genérico Supermercado (Gatilho do ML Full / Entrega rápida)
        else:
            return random.choice([
                "Fazer mercado sem sair de casa e pagando menos? Meus algoritmos aprovam essa ideia! 🛒⚡",
                "Aquela comprinha de mês que chega voando na sua casa! Aproveita o desconto! 📦💨",
                "Achadinho de despensa liberado pela Celle! Reponha o estoque pagando preço de atacado! 🥫💸"
            ])

    # 11. SALA VIP: MARCAS QUERIDINHAS E BEBIDAS (Gatilhos de Identificação e Autoridade)
    
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


    # 12. FALLBACK DE PREÇO
    if preco_atual and preco_atual <= 40:
        return random.choice([
            "Aquele precinho camarada que a gente ama! 😍",
            "Menos de R$ 40? O robô aqui aprova colocar no carrinho! 🛒"
        ])

    # 13. GATILHOS GENÉRICOS DE ALTO IMPACTO
    return random.choice([
        "🤖 Bi-bi-bop! A inteligência artificial aqui farejou esse achadinho!", 
        "🚨 ALERTA DE OFERTA DA CELLE!", 
        "🔥 ESSE DESCONTO VALE A PENA!", 
        "✨ Enquanto a Celle não olha, eu separei esse achadinho pra vocês:"
    ])

    
def gerar_link_afiliado(url_original, loja):
    try:
        if loja == "MAGALU":
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
        # Abre o modal de compartilhamento
        try:
            btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='generate_link_button']")))
            btn.click()
        except:
            botao_alt = driver.find_element(By.XPATH, "//button[contains(., 'Compartilhar')]")
            driver.execute_script("arguments[0].click();", botao_alt)

        print("| Aguardando modal e gerando link...")
        time.sleep(2.5) # Tempo essencial para o ML processar o encurtador

        # PLANO A: Ler direto da caixinha de texto (Muito mais seguro que o botão copiar)
        try:
            # Esse seletor busca o campo de input onde o link https://meli.la/ aparece no seu print
            caixa_link = driver.find_element(By.CSS_SELECTOR, "input.andes-form-control__field, .andes-form-control__field")
            link_final = caixa_link.get_attribute("value")
            
            # Adicionamos 'meli.la' na lista de domínios permitidos
            if link_final and any(dominio in link_final for dominio in ["meli.la", "mercadolivre", "ml.com"]):
                print(f"| 🎯 SUCESSO! Link capturado direto do campo: {link_final}")
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                return link_final
        except:
            pass

        # PLANO B: Se o de cima falhar, tenta o botão de copiar físico
        botao_copiar = driver.find_element(By.CSS_SELECTOR, "button[data-testid='copy-button__label_link']")
        driver.execute_script("arguments[0].click();", botao_copiar)
        time.sleep(1)
        link_final = pyperclip.paste()
        
        if any(dom in link_final for dom in ["meli.la", "mercadolivre"]):
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return link_final

    except Exception as e:
        print(f"| ❌ Erro ao gerar link: {e}")
        try: ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except: pass
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

# =========================================================
# PARTE SHOPEE (CORRIGIDA)
# =========================================================


def processar_painel_shopee(driver, produtos_processados_set, preco_maximo=None):
    if preco_maximo:
        print(f"\n======== 🟠 SHOPEE PAINEL (ATÉ R${preco_maximo:.0f}) ========")
    else:
        print("\n======== 🟠 SHOPEE (PAINEL -> NOVA ABA SEGURA) ========")
    url_painel = "https://affiliate.shopee.com.br/offer/product_offer"
    
    # 1. BLINDAGEM DE CONTEXTO
    try:
        url_atual = driver.current_url
    except Exception:
        print("| ⚠️ Contexto perdido. Recuperando foco...")
        try:
            if len(driver.window_handles) > 0:
                driver.switch_to.window(driver.window_handles[0])
                url_atual = driver.current_url
            else: return
        except: return

    if url_painel not in url_atual:
        try:
            driver.get(url_painel)
        except:
            print("| ❌ Erro ao carregar URL do Painel Shopee.")
            return
    
    print("\n" + "="*50)
    print("🚨 INSTRUÇÃO: Aguardando carregamento da lista (Max 60s)...")
    print("="*50)
    
    try:
        wait = WebDriverWait(driver, 60)
        aba_painel = driver.current_window_handle 

        print("| ⏳ Aguardando lista de ofertas...")
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Obter link')]")))
        print("| ✅ Lista carregada! Prosseguindo...")

        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1)

        print("| 🕵️ Mapeando produtos no painel...")
        # Pega a lista inicial
        botoes_painel = driver.find_elements(By.XPATH, "//*[contains(text(), 'Obter link')]")
        # Filtra visíveis
        produtos_encontrados = [b for b in botoes_painel if b.is_displayed()]
        qtd_encontrada = len(produtos_encontrados)
        print(f"| ✅ Produtos listados: {qtd_encontrada}")

        contador_envios = 0
        MAX_SHOPEE = 3

        # Loop seguro usando índice
        for i in range(qtd_encontrada):
            if contador_envios >= MAX_SHOPEE: break
            
            # Garante foco no Painel a cada iteração
            if driver.current_window_handle != aba_painel:
                driver.switch_to.window(aba_painel)
            
            print(f"| --- Processando Item {i+1}/{qtd_encontrada} ---")

            try:
                # Recarrega lista para evitar StaleElement
                botoes_painel = driver.find_elements(By.XPATH, "//*[contains(text(), 'Obter link')]")
                produtos_encontrados = [b for b in botoes_painel if b.is_displayed()]
                
                if i >= len(produtos_encontrados): break
                botao_ref = produtos_encontrados[i]

                # Tenta achar o container do produto
                card_painel = None
                try:
                    card_painel = botao_ref.find_element(By.XPATH, "./ancestor::div[contains(@class, 'offer-card') or contains(@class, 'product-item') or contains(@style, 'margin')]")
                except:
                    # Fallback genérico: sobe 5 níveis
                    card_painel = botao_ref.find_element(By.XPATH, "./../../../../..")

                titulo_previo = "Produto Shopee"
                try:
                    titulo_previo = card_painel.text.split('\n')[0]
                except: pass

                if titulo_previo in produtos_processados_set: 
                    print(f"| ⏭️ Já processado hoje. Pulando.")
                    continue

                if produto_eh_bloqueado(titulo_previo):
                    print(f"| 🚫 BLOQUEADO: '{titulo_previo}' contém termo proibido.")
                    produtos_processados_set.add(titulo_previo)
                    continue

                print(f"| 👆 Tentando abrir produto: {titulo_previo[:30]}...")

                abas_antes = set(driver.window_handles) 

                # Scroll até o elemento
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", card_painel)
                time.sleep(1)

                # Clique
                try:
                    link_clicavel = card_painel.find_element(By.TAG_NAME, "img")
                    driver.execute_script("arguments[0].click();", link_clicavel)
                except:
                    driver.execute_script("arguments[0].click();", card_painel)

                print("| ⏳ Aguardando nova aba (5s)...")
                time.sleep(5) 
                
                abas_depois = set(driver.window_handles)
                nova_aba_conjunto = abas_depois - abas_antes
                
                if not nova_aba_conjunto:
                    print("| ⚠️ Clique falhou (sem nova aba). Pulando item.")
                    continue
                
                aba_produto = list(nova_aba_conjunto)[0]
                driver.switch_to.window(aba_produto)
                
                # --- NA ABA DO PRODUTO ---
                # (Daqui pra baixo segue a lógica normal de extração)
                
                preco = 0.0
                preco_antigo = None
                
                titulo = None
                try:
                    seletores_titulo = ["h1.vR6K3w", ".vR6K3w", "div.shopee-product-info__header__title", "span.y9e30P", "h1", ".name"]
                    for sel in seletores_titulo:
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, sel)
                            if elem.text.strip():
                                titulo = elem.text.strip()
                                break
                        except: continue
                except: pass

                if not titulo: titulo = titulo_previo

                # Removemos a verificação global de 24h daqui, pois agora ela é feita por grupo no momento do envio.

                # Extração Preços (TESTE)
                preco = 0.0
                preco_antigo = None
                try:
                    seletores_atual = [".IZPeQz.B67UQ0", ".pqTWkA", ".shopee-product-info__header__real-price"]
                    for sel in seletores_atual:
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, sel)
                            valor = extrair_valor_numerico(elem.text)
                            if valor and valor > 0:
                                preco = valor
                                break
                        except: continue
                    
                    seletores_antigo = [".ZA5sW5", ".v67p8K", ".shopee-product-info__header__price-before"]
                    for sel in seletores_antigo:
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, sel)
                            valor = extrair_valor_numerico(elem.text)
                            if valor and valor > 0:
                                preco_antigo = valor
                                break
                        except: continue
                except: pass

                # DETECÇÃO DE OFERTA RELÂMPAGO
                eh_relampago = False
                try:
                    if driver.find_elements(By.CSS_SELECTOR, ".wV4oFQ"):
                        eh_relampago = True
                except: pass

                if preco <= 0:
                    print("| ⚠️ Preço não identificado. Fechando aba...")
                    driver.close()
                    driver.switch_to.window(aba_painel)
                    continue

                # FILTRO DE PREÇO MÁXIMO (TURNO RELÂMPAGO)
                if preco_maximo and preco > preco_maximo:
                    print(f"| 💲 REJEITADO (Preço): R${preco:.2f} > limite de R${preco_maximo:.0f}")
                    driver.close()
                    driver.switch_to.window(aba_painel)
                    continue

                # Extração Vendas
                vendas_count = 0
                try:
                    sel_vendas = [".aleSBU span.AcmPRb", ".v9335u", ".shopee-product-info__header__sold-count"]
                    for sel in sel_vendas:
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, sel)
                            texto = elem.text.lower()
                            if "mil" in texto:
                                match_m = re.search(r"(\d+[\d\.,]*)", texto)
                                if match_m:
                                    val_m = match_m.group(1).replace(",", ".")
                                    vendas_count = int(float(val_m) * 1000)
                            else:
                                m_v = re.search(r"(\d+)", texto)
                                if m_v: vendas_count = int(m_v.group(1))
                            if vendas_count > 0: break
                        except: continue
                except: pass

                # Nota
                nota = 0.0
                try:
                    sel_nota = [".F9RHbS.dQEiAI.jMXp4d", "div.shopee-product-rating__rating"]
                    for sel in sel_nota:
                        try:
                            elem = driver.find_element(By.CSS_SELECTOR, sel)
                            nota = float(elem.text.strip())
                            if nota > 0: break
                        except: continue
                except: pass

                # Imagem
                img_url = None
                try:
                    imgs = driver.find_elements(By.TAG_NAME, "img")
                    for img in imgs:
                        src = img.get_attribute("src")
                        if src and "http" in src and int(img.get_attribute("width") or 0) > 200:
                            img_url = src
                            break
                except: pass

                # Link Afiliado
                print("| 🔗 Clicando em 'Obter link'...")
                link_afiliado = None
                try:
                    btn_gerar = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.get-link-btn")))
                    btn_gerar.click()
                    time.sleep(2)
                    try:
                        input_link = driver.find_element(By.XPATH, "//input[contains(@value, 'shopee')]")
                        link_afiliado = input_link.get_attribute("value")
                    except:
                        btn_copiar = driver.find_element(By.XPATH, "//button[contains(., 'Copiar Link')]")
                        btn_copiar.click()
                        time.sleep(1)
                        link_afiliado = pyperclip.paste()
                except: pass

                print("| 🔙 Fechando aba do produto...")
                if driver.current_window_handle == aba_produto:
                    driver.close()
                driver.switch_to.window(aba_painel)

                # FILTROS DE QUALIDADE (OBRIGATÓRIO)
                if not link_afiliado or not "shope.ee" in link_afiliado:
                    print(f"| ❌ REJEITADO: Link de afiliado inválido.")
                    continue

                if not titulo or titulo == "Produto Shopee":
                    print(f"| ❌ REJEITADO: Título não capturado.")
                    continue
                
                if preco <= 0:
                    print(f"| ❌ REJEITADO: Preço não capturado.")
                    continue

                if not img_url:
                    print(f"| ❌ REJEITADO: Imagem não capturada.")
                    continue

                # ENVIO (CÓDIGO INTELIGENTE)
                chamada = gerar_chamada_inteligente(titulo, preco)
                if eh_relampago:
                    chamada = "⚡ <b>OFERTA RELÂMPAGO! CORRE!</b>"
                
                msg = (
                    f"<b>{chamada}</b>\n\n"
                    f"📦 <b>{titulo}</b>\n\n"
                )
                
                if preco_antigo and preco_antigo > preco:
                    desconto = int(((preco_antigo - preco) / preco_antigo) * 100)
                    msg += f"❌ <s>De: {formatar_preco_br(preco_antigo)}</s>\n"
                    msg += f"✅ <b>Por: {formatar_preco_br(preco)}</b> ({desconto}% OFF) 📉\n"
                else:
                    msg += f"✅ <b>Preço Especial: {formatar_preco_br(preco)}</b> 💰\n"
                
                if nota > 0: msg += f"⭐ <b>Avaliação: {nota}/5.0</b>\n"
                
                msg += (
                    f"\n🛒 <b>COMPRE AQUI:</b> 👇\n"
                    f"👉 <a href='{link_afiliado}'>CLIQUE PARA VER NO SITE</a>"
                )

                enviar_telegram(msg, link_afiliado, img_url)
                
                # --- ENVIO PARA TODOS OS GRUPOS CONFIGURADOS ---
                teve_envio_whats = False
                caminho_foto = None
                if img_url:
                    caminho_foto = baixar_imagem_temporaria(img_url)

                try:
                    for grupo in GRUPOS_ALVO:
                        if verificar_se_ja_enviou_24h(titulo, grupo):
                            print(f"| ⏭️ Ignorando grupo '{grupo}': Já enviado nas últimas 24h.")
                            continue

                        print(f"| 🟢 Enviando para o grupo: {grupo}")
                        if caminho_foto:
                            enviar_whatsapp_robusto(driver, grupo, msg, caminho_foto)
                        else:
                            enviar_whatsapp(driver, grupo, msg)
                        
                        registrar_envio_24h(titulo, grupo)
                        teve_envio_whats = True
                finally:
                    if caminho_foto and os.path.exists(caminho_foto):
                        try: os.remove(caminho_foto)
                        except: pass

                if teve_envio_whats:
                    produtos_processados_set.add(titulo)
                    if isinstance(contador_envios, int):
                        contador_envios += 1
                else:
                    print(f"| ℹ️ Produto '{titulo[:20]}...' já enviado para todos os grupos hoje.")
            
            except Exception as e:
                print(f"| ⚠️ Erro ao processar item {i}: {e}")
                try: 
                    if len(driver.window_handles) > 1: driver.close()
                    driver.switch_to.window(aba_painel)
                except: pass
                continue

    except Exception as e:
        print(f"| ❌ Erro Crítico Shopee: {e}")

def processar_shopee_manual(driver, produtos_processados_set, preco_maximo=None):
    if preco_maximo:
        if preco_maximo > 50:
             print(f"\n======== 🟠 SHOPEE MANUAL (ACHADINHOS SHOPEE) ========")
        else:
             print(f"\n======== 🟠 SHOPEE MANUAL (ATÉ R${preco_maximo:.0f}) ========")
    else:
        print("\n======== 🟠 SHOPEE (MODO MANUAL) ========")
    
    # --- CORREÇÃO DE BLINDAGEM AQUI ---
    try:
        # Tenta pegar a janela atual. Se o navegador tiver fechado, vai dar erro aqui.
        aba_navegacao = driver.current_window_handle
    except Exception as e:
        print(f"| ❌ ERRO DE CONEXÃO: O navegador parece ter sido fechado.")
        print(f"| ⚠️ Detalhe: {e}")
        # Tenta recuperar pegando a primeira janela disponível
        try:
            if len(driver.window_handles) > 0:
                driver.switch_to.window(driver.window_handles[0])
                aba_navegacao = driver.current_window_handle
                print("| ✅ Recuperado: Focando na primeira aba disponível.")
            else:
                print("| 🛑 Fatal: Nenhuma aba disponível. Encerrando manual.")
                return
        except:
            print("| 🛑 Fatal: Não foi possível reconectar ao Chrome.")
            return
    # ----------------------------------

    arquivo_links = "shopee_links.txt"

    aba_navegacao = driver.current_window_handle # Salva logo no início
    
    if not os.path.exists(arquivo_links):
        print(f"| ⚠️ Arquivo '{arquivo_links}' não encontrado. Adicione links no formato: link|link_afil")
        return

    links_a_processar = []
    with open(arquivo_links, "r", encoding="utf-8") as f:
        linhas = f.readlines()
        for linha in linhas:
            if "|" in linha and not linha.strip().startswith("#"):
                partes = linha.split("|")
                url_prod = partes[0].strip()
                url_afil = partes[1].strip()
                if "http" in url_prod and "http" in url_afil:
                    links_a_processar.append((url_prod, url_afil))

    if not links_a_processar:
        print("| ℹ️ Nenhum link válido no arquivo.")
        return

    # CABEÇALHO DE TURNO DE PREÇO
    if preco_maximo:
        CABECALHOS_PRECO = {
            50: "🎯 <b>ACHADINHOS DE ATÉ R$50!</b>\n✨ Seleção especial com preço baixo garantido 👇",
            100: "💰 <b>OFERTAS DE ATÉ R$100!</b>\n🔥 Produtos incríveis que cabem no bolso 👇",
            200: "🛍️ <b>SELEÇÃO ATÉ R$200!</b>\n📦 Os melhores achados do dia 👇",
        }
        msg_cabecalho = CABECALHOS_PRECO.get(
            int(preco_maximo),
            f"🏷️ <b>ACHADINHOS DE ATÉ R${preco_maximo:.0f}!</b>\n✨ Confira a seleção especial 👇"
        )
        enviar_telegram(msg_cabecalho, None, None)
        try:
            enviar_whatsapp(driver, "Instagram @celle.tech", msg_cabecalho)
        except: pass
        time.sleep(2)
        # Garante volta para a aba de navegação após o cabeçalho
        try: driver.switch_to.window(aba_navegacao)
        except: pass

    aba_navegacao = driver.current_window_handle

    for url_produto, link_afiliado in links_a_processar:
        print(f"\n| --- Processando Link Manual ---")
        try:
            # Tenta focar na aba de trabalho (opcional)
            try: driver.switch_to.window(aba_navegacao)
            except: pass
            
            url_str = str(url_produto)
            print(f"| 🌐 Carregando: {url_str[:50]}...")
            driver.get(url_produto)
            time.sleep(7) 

            # Tenta capturar o título com múltiplos seletores
            titulo = "Produto Shopee"
            seletores_titulo = [
                "h1.vR6K3w", # Fornecido pelo usuário
                ".vR6K3w",
                ".shopee-product-info__header__title",
                "span.y9e30P",
                "div._44qnta span",
                "h1",
                ".Vp_hYp"
            ]
            
            for sel in seletores_titulo:
                try:
                    elem_t = driver.find_element(By.CSS_SELECTOR, sel)
                    texto = elem_t.text.strip()
                    if texto and len(texto) > 10:
                        titulo = texto
                        break
                except: pass

            if titulo == "Produto Shopee":
                print(f"| 🔍 DEBUG: Falha ao capturar título. URL atual: {driver.current_url[:50]}...")

            preco = 0.0
            preco_antigo = None
            try:
                for sel in [".IZPeQz.B67UQ0", ".pqTWkA", ".v67p8K"]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, sel)
                        val = extrair_valor_numerico(el.text)
                        if val: preco = val; break
                    except: pass
                
            # Procura preço antigo (riscado)
                for sel in [".ZA5sW5", ".v67p8K", ".tD_S5S", ".Y76N_x"]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, sel)
                        val = extrair_valor_numerico(el.text)
                        if val and val > preco: preco_antigo = val; break
                    except: pass
            except: pass

            # DETECÇÃO DE OFERTA RELÂMPAGO
            eh_relampago = False
            try:
                if driver.find_elements(By.CSS_SELECTOR, ".wV4oFQ"):
                    eh_relampago = True
            except: pass

            if preco <= 0:
                print(f"| 🔍 DEBUG: Falha ao capturar preço. URL: {url_str[:50]}...")
                continue

            # FILTRO DE PREÇO MÁXIMO (TURNO)
            if preco_maximo and preco > preco_maximo:
                print(f"| 💲 REJEITADO (Preço): R${preco:.2f} > limite de R${preco_maximo:.0f}")
                continue

            img_url = None
            try:
                # Tenta capturar imagem principal
                imgs = driver.find_elements(By.TAG_NAME, "img")
                for img in imgs:
                    src = img.get_attribute("src")
                    if src and "http" in src and int(img.get_attribute("width") or 0) > 200:
                        img_url = src; break
                
                if not img_url:
                    # Tenta forçar carregamento via scroll se imagem falhar
                    driver.execute_script("window.scrollTo(0, 400);")
                    time.sleep(2)
                    imgs = driver.find_elements(By.TAG_NAME, "img")
                    for img in imgs:
                        src = img.get_attribute("src")
                        if src and "http" in src and int(img.get_attribute("width") or 0) > 200:
                            img_url = src; break
            except: pass

            if not img_url:
                print(f"| 🔍 DEBUG: Falha ao capturar imagem.")

            # EXTRAÇÃO DE QUALIDADE (SELETORES FORNECIDOS PELO USUÁRIO)
            nota_produto = 0.0
            qtd_avaliacoes = 0
            qtd_vendas = 0

            try:
                # 1. Nota (ex: 4.8)
                elem_nota = driver.find_element(By.CSS_SELECTOR, ".dQEiAI.jMXp4d")
                val_nota = elem_nota.text.strip().replace(',', '.')
                match_n = re.search(r'(\d+\.?\d*)', val_nota)
                if match_n: nota_produto = float(match_n.group(1))
            except: pass

            try:
                # 2. Número de Avaliações (ex: 3,4mil)
                # O usuário indicou que está em um .F9RHbS dentro de um botão que contém "Avaliações"
                btns = driver.find_elements(By.CSS_SELECTOR, "button.flex.e2p50f")
                for b in btns:
                    if "Avaliações" in b.text:
                        elem_q = b.find_element(By.CSS_SELECTOR, ".F9RHbS")
                        val_q = elem_q.text.strip().lower()
                        # Lógica de conversão "mil"
                        multiplicador = 1
                        if "mil" in val_q:
                            multiplicador = 1000
                            val_q = val_q.replace("mil", "").replace(",", ".").strip()
                        
                        match_q = re.search(r'(\d+\.?\d*)', val_q)
                        if match_q: qtd_avaliacoes = int(float(match_q.group(1)) * multiplicador)
                        break
            except: pass

            try:
                # 3. Quantidade de Vendas (ex: 7mil+)
                elem_v = driver.find_element(By.CSS_SELECTOR, ".AcmPRb")
                val_v = elem_v.text.strip().lower()
                multiplicador_v = 1
                if "mil" in val_v:
                    multiplicador_v = 1000
                    val_v = val_v.replace("mil", "").replace("+", "").replace(",", ".").strip()
                
                match_v = re.search(r'(\d+\.?\d*)', val_v)
                if match_v: qtd_vendas = int(float(match_v.group(1)) * multiplicador_v)
            except: pass

            print(f"| QUALIDADE: Nota {nota_produto} | Avaliações: {qtd_avaliacoes} | Vendas: {qtd_vendas}")

            # VALIDAÇÃO DE QUALIDADE (OBRIGATÓRIO)
            if not titulo or titulo == "Produto Shopee":
                print(f"| ⚠️ REJEITADO (Manual): Título não capturado ({titulo}).")
                continue
            
            if preco <= 0:
                print(f"| ⚠️ REJEITADO (Manual): Preço não encontrado.")
                continue
            
            if not img_url:
                print(f"| ⚠️ REJEITADO (Manual): Imagem não encontrada.")
                continue

            # FILTROS DE QUALIDADE (Mínimos sugeridos)
            if nota_produto > 0 and nota_produto < 4.5:
                print(f"| ❌ REJEITADO: Nota baixa ({nota_produto}).")
                continue
            
            if qtd_avaliacoes > 0 and qtd_avaliacoes < 10:
                print(f"| ❌ REJEITADO: Poucas avaliações ({qtd_avaliacoes}).")
                continue

            # A verificação global de 24h foi removida daqui, pois agora ela é feita por grupo no momento do envio.
            
            if titulo in produtos_processados_set:
                print(f"| ⏭️ Já processado nesta sessão. Pulando.")
                continue

            # ENVIO MANUAL INTELIGENTE
            chamada = gerar_chamada_inteligente(titulo, preco)
            if eh_relampago:
                chamada = "⚡ <b>OFERTA RELÂMPAGO! CORRE!</b>"
            
            msg = (
                f"<b>{chamada}</b>\n\n"
                f"📦 <b>{titulo}</b>\n\n"
            )

            if nota_produto > 0:
                estrelas = "⭐" * int(nota_produto)
                msg += f"{estrelas} ({nota_produto})\n"
            
            if preco_antigo and preco_antigo > preco:
                desc = int(((preco_antigo - preco) / preco_antigo) * 100)
                msg += f"❌ <s>De: R$ {formatar_preco_br(preco_antigo)}</s>\n"
                msg += f"✅ <b>Por: R$ {formatar_preco_br(preco)}</b> ({desc}% OFF) 📉\n"
            else:
                msg += f"✅ <b>Preço: R$ {formatar_preco_br(preco)}</b>\n"
            
            msg += (
                f"\n🛒 <b>COMPRE AQUI:</b> 👇\n"
                f"👉 <a href='{link_afiliado}'>CLIQUE PARA VER</a>"
            )

            enviar_telegram(msg, link_afiliado, img_url)
            
            # --- ENVIO PARA TODOS OS GRUPOS CONFIGURADOS ---
            teve_envio_whats = False
            caminho_foto = None
            if img_url:
                caminho_foto = baixar_imagem_temporaria(img_url)

            try:
                for grupo in GRUPOS_ALVO:
                    if verificar_se_ja_enviou_24h(titulo, grupo):
                        print(f"| ⏭️ Ignorando grupo '{grupo}': Já enviado nas últimas 24h.")
                        continue

                    print(f"| 🟢 Enviando para o grupo: {grupo}")
                    if caminho_foto:
                        enviar_whatsapp_robusto(driver, grupo, msg, caminho_foto)
                    else:
                        enviar_whatsapp(driver, grupo, msg)
                    
                    registrar_envio_24h(titulo, grupo)
                    teve_envio_whats = True
            finally:
                if caminho_foto and os.path.exists(caminho_foto):
                    try: os.remove(caminho_foto)
                    except: pass

            if teve_envio_whats:
                produtos_processados_set.add(titulo)
                print(f"| ✅ Enviado com sucesso!")
            else:
                print(f"| ℹ️ Produto '{titulo[:20]}...' já enviado para todos os grupos hoje.")
            
            time.sleep(3)

        except Exception as e:
            print(f"| ⚠️ Erro: {e}")
            continue

    print("\n| ✅ Fim do processamento manual!")



def gerar_link_amazon_sitestripe(driver):
    print("| 🔗 AMAZON: Iniciando captura SiteStripe...")
    
    try:
        time.sleep(4) 

        try:
            print("| Procurando botão ID: 'amzn-ss-get-link-button'...")
            
            botao = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "amzn-ss-get-link-button"))
            )
            
            driver.execute_script("arguments[0].click();", botao)
            print("| ✅ Botão CLICADO com sucesso!")
            
        except Exception as e:
            print(f"| ❌ Erro ao clicar no botão: {e}")
            try:
                driver.find_element(By.ID, "amzn-ss-text-link").click()
            except: pass
            return None

        try:
            caixa = WebDriverWait(driver, 8).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#amzn-ss-text-shortlink-textarea, textarea[id*='shortlink']"))
            )
            time.sleep(1.5)
            link_curto = caixa.get_attribute("value")

            if link_curto and "amzn.to" in link_curto:
                print(f"| 🎯 LINK CAPTURADO: {link_curto}")
                
                try:
                    driver.execute_script("document.querySelector('button[class*=\"close-popover\"]').click()")
                except: pass
                
                return link_curto
        except:
            print("| ❌ Botão clicado, mas a caixa de link não apareceu.")
            
    except Exception as e:
        print(f"| ❌ Falha técnica no SiteStripe: {e}")

    return None

def gerar_link_magalu_oficial(driver):
    print("| 🔗 MAGALU: Tentando gerar link curto oficial...")
    
    try:
        # 1. TENTA ENCONTRAR E CLICAR NO BOTÃO "GERAR LINK"
        botao_gerar = None
        
        # Adicionei o data-testid que você encontrou: "phm-button-desktop"
        seletores_botao = [
            '[data-testid="phm-button-desktop"]',   # O seletor mais novo e preciso
            "//button[contains(., 'Gerar link')]",  # Texto exato
            "//div[contains(text(), 'Gerar link')]", # Às vezes é uma DIV
            "[data-testid='generate-link-button']", # Seletor técnico comum
            ".button-generate-link"                 # Classe legada
        ]
        
        for seletor in seletores_botao:
            try:
                if "//" in seletor:
                    botao_gerar = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, seletor))
                    )
                else:
                    botao_gerar = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, seletor))
                    )
                
                # Garante que o botão está visível e clicável antes de tentar
                if botao_gerar and botao_gerar.is_displayed():
                    # Move a tela até o botão (ajuda muito o Selenium a não falhar)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao_gerar)
                    time.sleep(0.5)
                    break 
            except: continue
            
        if not botao_gerar:
            print("| ⚠️ Botão 'Gerar link' não encontrado (Você está logada?).")
            return None
            
        # Clica no botão
        driver.execute_script("arguments[0].click();", botao_gerar)
        
        # 2. AGUARDA O MODAL E PEGA O LINK
        print("| ⏳ Aguardando modal...")
        
        campo_link = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[value*='divulgador.magalu']"))
        )
        
        link_curto = campo_link.get_attribute("value")
        
        if link_curto:
            print(f"| 🎯 LINK CURTO CAPTURADO: {link_curto}")
            
            try:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except: pass
            
            return link_curto

    except Exception as e:
        print(f"| ❌ Falha ao gerar link curto Magalu: {e}")
        try: ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except: pass

    return None

def processar_feed_mercadolivre(driver, alvo, produtos_processados_set, preco_maximo=None):
    print(f"\n======== {alvo['nome']} (DETALHADO) ========")
    driver.get(alvo['url_lista'])
    time.sleep(3) # Tempo suficiente para o layout Poly carregar

    links_para_visitar = []
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, ".poly-card")
        print(f"| FEED: Analisando vitrine de {len(cards)} itens...")
        
        # Coleta até 40 links para ter uma margem de segurança contra filtros de preço
        for card in cards[:40]: 
            try:
                link_elem = card.find_element(By.CSS_SELECTOR, "a.poly-component__title")
                url = link_elem.get_attribute("href")
                links_para_visitar.append(url)
            except: continue
    except Exception as e:
        print(f"| ❌ Erro ao ler feed: {e}")
        return

    # 👇 NOVO CONTADOR AQUI 👇
    produtos_enviados_nesta_lista = 0

    for url_produto in links_para_visitar:
        # Verifica se já bateu a meta logo no início do loop
        if produtos_enviados_nesta_lista >= 5:
            print(f"| 🛑 Limite de 5 produtos atingido para {alvo['nome']}. Finalizando lista!")
            break
            
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
                import random
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
                    
                    registrar_envio_24h(titulo, grupo)
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
    "calota"
]

# =====================================================
# LISTAS MESTRAS (ESTRATÉGIA DE GESTOR DE TRÁFEGO)
# =====================================================
LISTA_MESTRE_MAGALU = [

    # --- NOVO LINK MANUAL (ADICIONE ISTO AQUI) ---
    {
        "nome": "Magazine Você - Eletroportáteis (Filtro Manual)", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/eletroportateis/l/ep/price---0:5000/", 
        "dominio_base": "https://www.magazinevoce.com.br",
        "seletor_item_lista": '[data-testid="product-card-container"]', 
        "seletor_link_lista": 'a',
        "seletor_titulo_detalhe": 'h1[data-testid="product-title"]',
        "seletor_preco_detalhe": 'p[data-testid="price-value"]',
        "seletor_preco_antigo": 'p[data-testid="price-original"]',
        "delay_min": 10, "delay_max": 15,
        "grupo": "MANUAL", 
        "categoria": "ELETROPORTATEIS"
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
        "nome": "Magazine Você - Bebês e Brinquedos", 
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/bebes/l/be/", 
        "grupo": "MANHA", # Mães costumam monitorar fraldas e itens de bebê cedo
        "categoria": "UTILIDADES",
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
        "nome": "Amazon - Ferramentas e Construção",
        "url_lista": "https://www.amazon.com.br/gp/bestsellers/hi/", 
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

LISTA_MESTRE_SHOPEE = []

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
        "url_lista": "https://www.magazinevoce.com.br/magazinecelle/utilidades-domesticas/l/ud/", 
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

def rastrear_lista_produtos(url_lista, driver, seletor_item, seletor_link, dominio_base, max_list_items=40):
    print(f"[SELENIUM] Acessando a lista: {url_lista}")
    driver.get(url_lista)
    
    # Seletores Híbridos MUITO mais abrangentes
    if "amazon" in url_lista:
        seletor_item = 'div[data-asin], .zg-grid-general-faceout, div[id^="p13n-asin-index-"]'
    elif "mercadolivre" in url_lista:
        seletor_item = '.poly-card, .andes-card, .ui-search-result'
    elif "magazinevoce" in url_lista or "magazineluiza" in url_lista:
        # Pega qualquer variação de container que o Magalu use na vitrine
        seletor_item = '[data-testid="product-card-container"], [data-testid="product-card"], [data-testid="mod-productcard"], ul[data-testid="list-products"] li, .sc-product-item'

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, seletor_item))
        )
        driver.execute_script("window.scrollTo(0, 1000);") 
        time.sleep(3) 
    except:
        print(f"| ⚠️ Timeout. Tentando extrair via HTML bruto ou vitrine vazia...")
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    itens_lista = soup.select(seletor_item)
    
    produtos_encontrados = []
    for item in itens_lista[:max_list_items]:
        try:
            # 🔥 O SEGREDO TÁ AQUI: Se o próprio item for o link (a), usa ele. Se não, procura dentro.
            if item.name == 'a' and item.has_attr('href'):
                link_tag = item
            else:
                link_tag = item.select_one(seletor_link) if seletor_link else None
                if not link_tag:
                    link_tag = item.select_one('a[href]')
            
            if link_tag and link_tag.get('href'):
                url_p = link_tag.get('href')
                url_c = dominio_base + url_p if not url_p.startswith('http') else url_p
                
                # Extrai o título (procura h2, h3, ou o data-testid do magalu)
                tit_tag = item.select_one('h2, h3, [data-testid="product-title"]')
                if not tit_tag:
                    # Fallback extremo: pega o texto do próprio card se o título sumir
                    titulo = item.get_text(strip=True)[:60] + "..." if item.get_text() else "Produto"
                else:
                    titulo = tit_tag.get_text(strip=True)
                
                produtos_encontrados.append({'titulo': titulo, 'url': url_c})
        except Exception as e: 
            print(f"| ⚠️ Erro ao processar um item específico: {e}")
            continue
        
    print(f"| ✅ SUCESSO: {len(produtos_encontrados)} produtos identificados.")
    return produtos_encontrados

def rastrear_detalhe_produto(produto, driver, alvo):
    url_produto = produto['url']
    print(f"| Analisando detalhe: {produto['titulo']}")

    try:
        driver.get(url_produto)
    except TimeoutException:
        print(f"[⚠️ TIMEOUT] Produto demorou demais. Pulando.")
        return produto['titulo'], None, None, None, "", False, 0, 0
    except Exception as e:
        print(f"[⚠️ ERRO] Falha ao acessar. Detalhes: {e}")
        return produto['titulo'], None, None, None, "", False, 0, 0

    titulo_final = "Título Desconhecido"
    
    try:
        elemento_titulo = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.vR6K3w, .vR6K3w, #productTitle, div.shopee-product-info__header__title"))
        )
        titulo_final = elemento_titulo.text.strip()
    except:
        titulo_final = produto['titulo']
            
    print(f"| Título Confirmado (Prévio): {titulo_final}")

    try:
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1)
    except: pass

    soup_detalhe = BeautifulSoup(driver.page_source, 'html.parser')

    # ==============================================================================
    # 🔥 CORREÇÃO 1: TÍTULO MAGALU (Ignora "Comissão" e pega o H1 real)
    # ==============================================================================
    if "magazinevoce" in url_produto or "magazineluiza" in url_produto:
        try:
            tit_tag = soup_detalhe.select_one('h1[data-testid="heading-product-title"], h1.header-product__title')
            if tit_tag:
                titulo_final = tit_tag.get_text(strip=True)
                print(f"| ✅ Título Corrigido (Magalu): {titulo_final}")
        except: pass

    preco_atual = None
    preco_antigo = None

    try:
        if "amazon" in url_produto:
            # 1. TENTA OS SELETORES PADRÕES PRIMEIRO
            seletores_preco = [
                '.a-price.aok-align-center .a-offscreen', 
                '#price', '#newBuyBoxPrice', '#kindle-price'
            ]
            
            for seletor in seletores_preco:
                elem = soup_detalhe.select_one(seletor)
                if elem:
                    val = extrair_valor_numerico(elem.get_text())
                    if val and val > 0:
                        preco_atual = val; break
                    
            try:
                # Seleciona as caixinhas do grid (Kindle, Audio, Capa Comum)
                caixas_formato = soup_detalhe.select('.formatsRow .swatchElement, #tmmSwatches .swatchElement, li.swatchElement')
                
                melhor_preco_encontrado = None
                
                for caixa in caixas_formato:
                    texto_caixa = caixa.get_text().lower()
                    
                    # Tenta achar o preço dentro da caixinha
                    elem_preco_box = caixa.select_one('.slot-price, .a-color-price')
                    if elem_preco_box:
                        valor_box = extrair_valor_numerico(elem_preco_box.get_text())
                        
                        if valor_box and valor_box > 0:
                            # PRIORIDADE MÁXIMA: Capa Comum ou Dura (Livro Físico)
                            if "comum" in texto_caixa or "dura" in texto_caixa:
                                preco_atual = valor_box
                                print(f"| 📖 Preço Livro Físico encontrado no Grid: R$ {preco_atual}")
                                break # Achamos o físico, para de procurar e usa esse!
                            
                            # Se for Kindle, guarda caso não ache o físico
                            elif "kindle" in texto_caixa:
                                melhor_preco_encontrado = valor_box

                # Se saiu do loop e o preco_atual ainda é do Audiobook (0.00) ou nulo,
                # mas achamos um Kindle ou outro preço válido no grid, usa ele.
                if (preco_atual is None or preco_atual == 0) and melhor_preco_encontrado:
                    preco_atual = melhor_preco_encontrado

            except Exception as e:
                print(f"| Erro ao ler grid de livros: {e}")
            # -----------------------------------------------------------

            # Tenta achar preço antigo (De: R$...)
            elem_antigo = soup_detalhe.select_one('span[data-a-strike="true"] .a-offscreen')
            if not elem_antigo: elem_antigo = soup_detalhe.select_one('#listPrice') # Comum em livros
            
            if elem_antigo:
                preco_antigo = extrair_valor_numerico(elem_antigo.get_text())
        else:
            # --- NOVA LÓGICA MAGALU BLINDADA PARA PREÇOS ---
            # O robô tenta várias "fantasias" que o preço pode estar usando
            seletores_preco_magalu = [
                alvo.get("seletor_preco_detalhe"), # Tenta a regra do dicionário primeiro
                '[data-testid="price-value"]',     # Pega de qualquer tag (div, p, h4)
                '.price-template__text',           # Classe alternativa comum
                'span.price-template__text'
            ]
            
            for sel in seletores_preco_magalu:
                if not sel: continue
                elem_preco = soup_detalhe.select_one(sel)
                if elem_preco:
                    val = extrair_valor_numerico(elem_preco.get_text())
                    if val and val > 0:
                        preco_atual = val
                        break # Achou o preço atual, para de procurar

            # Tenta achar o Preço Antigo (riscado) com a mesma estratégia
            seletores_antigo_magalu = [
                alvo.get("seletor_preco_antigo"),
                '[data-testid="price-original"]',
                '.price-template__from',
                'p[data-testid="price-original"]'
            ]
            
            for sel in seletores_antigo_magalu:
                if not sel: continue
                elem_antigo = soup_detalhe.select_one(sel)
                if elem_antigo:
                    val_antigo = extrair_valor_numerico(elem_antigo.get_text())
                    if val_antigo and preco_atual and val_antigo > preco_atual:
                        preco_antigo = val_antigo
                        break
    except Exception: pass

    # ==============================================================================
    # 📸 EXTRAÇÃO DE IMAGEM EM ALTA DEFINIÇÃO (VERSÃO MESTRE: ML + AMAZON + MAGALU)
    # ==============================================================================
    image_url = None
    try:
        # 1. TENTA SELETORES GERAIS (AMAZON E OUTROS)
        img_elem = soup_detalhe.select_one('img#landingImage, img#imgBlkFront, [data-a-image-name="landingImage"], img.ui-pdp-image, .ui-pdp-gallery__figure__image')
        
        if img_elem:
            # Pega o melhor atributo disponível
            image_url = img_elem.get('data-zoom') or img_elem.get('data-old-hires') or img_elem.get('src')
        
        # 2. FALLBACK PARA MAGAZINE LUIZA
        if not image_url:
            seletores_magalu = [
                'img[data-testid="image-selected-thumbnail"]', 
                'img[data-testid="product-image"]',
                '[data-testid="image-selected"]', 
                '.showcase-product__big-img', 
                'img.main-image'
            ]
            
            # ✅ AGORA SIM: O loop roda passando pela variável correta
            for sel in seletores_magalu:
                f_elem = soup_detalhe.select_one(sel)
                if f_elem and f_elem.get('src'): # Puxa exatamente o link do src
                    image_url = f_elem.get('src')
                    break

        # 3. MÁGICA DA LIMPEZA HD
        if image_url:
            # --- LIMPEZA AMAZON ---
            if "amazon.com" in image_url or "media-amazon.com" in image_url:
                image_url = re.sub(r'\._AC_.*_\.', '.', image_url)
                image_url = re.sub(r'\._SL.*_\.', '.', image_url)
                image_url = re.sub(r'\._SR.*_\.', '.', image_url)
                image_url = re.sub(r'\._SS.*_\.', '.', image_url)

            # --- LIMPEZA MERCADO LIVRE (O segredo do -O.webp) ---
            elif "mlstatic.com" in image_url:
                # Transforma qualquer miniatura (-V, -F, -C) no arquivo ORIGINAL (-O)
                image_url = re.sub(r'-[A-Z]\.(webp|jpg|jpeg|png)$', r'-O.\1', image_url)
            
            print(f"| ✨ Imagem capturada: {image_url.split('/')[-1]}")
            
    except Exception as e:
        print(f"| ❌ Erro ao extrair imagem: {e}")

    # --- Nota e Avaliações (Mantida) ---
    nota_produto = 0.0
    qtd_avaliacoes = 0
    try:
        if "amazon" in url_produto:
            elem_nota = soup_detalhe.select_one('span[data-hook="rating-out-of-text"]') or soup_detalhe.select_one('i[data-hook="average-star-rating"] span')
            if elem_nota:
                match = re.search(r'(\d+\.?\d*)', elem_nota.get_text(strip=True).replace(',', '.'))
                if match: nota_produto = float(match.group(1))
            elem_qtd = soup_detalhe.select_one('#acrCustomerReviewText')
            if elem_qtd:
                match_q = re.search(r'(\d+)', elem_qtd.get_text(strip=True).replace('.', ''))
                if match_q: qtd_avaliacoes = int(match_q.group(1))
        else:
            elem_nota = soup_detalhe.select_one('[data-testid="review-totalizers-rating"]')
            if elem_nota:
                match = re.search(r'(\d+\.?\d*)', elem_nota.get_text(strip=True).replace(',', '.'))
                if match: nota_produto = float(match.group(1))
            elem_qtd = soup_detalhe.select_one('[data-testid="review-totalizers-count"]')
            if elem_qtd:
                match_q = re.search(r'(\d+)', elem_qtd.get_text(strip=True))
                if match_q: qtd_avaliacoes = int(match_q.group(1))
    except: pass

    # --- ATENÇÃO: Desativei o filtro de avaliações para forçar o teste ---
    eh_relevante = True 
    
    # Detecção de Best Seller
    is_best_seller = False
    try:
        if "amazon" in url_produto:
            if soup_detalhe.select('.a-badge-text') and "mais vendido" in soup_detalhe.select('.a-badge-text')[0].get_text().lower():
                is_best_seller = True
        elif soup_detalhe.find(string=re.compile(r"mais vendido", re.IGNORECASE)):
            is_best_seller = True
    except: pass
    
    if is_best_seller: eh_relevante = True 

    # --- EXTRAÇÃO DE CUPOM (MAGALU) ---
    cupom_codigo = None
    try:
        # Busca exatamente o input que você mapeou no HTML
        elem_cupom = soup_detalhe.select_one('input[data-testid="coupon-code-input"]')
        if elem_cupom and elem_cupom.get('value'):
            cupom_codigo = elem_cupom.get('value')
            print(f"| 🎟️ CUPOM DETECTADO: {cupom_codigo}")
    except: pass

    # --- EXTRAÇÃO DE AUTOR (AMAZON LIVROS) ---
    nome_autor = ""
    try:
        if "amazon" in url_produto:
            # Pega todas as caixinhas de autores/tradutores
            autores_spans = soup_detalhe.select('#bylineInfo .author.notFaded')
            for span in autores_spans:
                # Verifica se a contribuição diz "Autor"
                contribuicao = span.select_one('.contribution')
                if contribuicao and 'autor' in contribuicao.get_text().lower():
                    link_autor = span.select_one('a')
                    if link_autor:
                        nome_autor = link_autor.get_text(strip=True)
                        print(f"| ✍️ Autor detectado: {nome_autor}")
                        break # Achou o autor principal, pode parar
    except Exception as e:
        pass

    # --- BLOCO DE DEBUG (MANTENHA ISSO ATÉ FUNCIONAR) ---
    print(f"| 🕵️ DEBUG DO PRODUTO: {titulo_final[:30]}...")
    print(f"|    > Preço Atual: {preco_atual}")
    print(f"|    > Imagem URL: {image_url}")
    print(f"|    > Avaliações: {qtd_avaliacoes} (Relevante? {eh_relevante})")
    if cupom_codigo:
        print(f"|    > Cupom: {cupom_codigo}")
    # ----------------------------------------------------

    # ❌ APAGUE A LINHA DE RETURN ANTIGA E COLOQUE ESSA (agora passando o cupom_codigo):
    return titulo_final, preco_atual, preco_antigo, image_url, nome_autor, eh_relevante, nota_produto, qtd_avaliacoes, cupom_codigo, None

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

def enviar_whatsapp(driver, nome_grupo, mensagem):
    print(f"| 🟢 WHATSAPP: Enviando para o grupo '{nome_grupo}'...")
    
    # --- TROCA PARA A ABA DO WHATSAPP SE NECESSÁRIO ---
    if not focar_aba_whatsapp(driver):
        return

    limpar_interface_whatsapp(driver) # PREVENÇÃO

    try:
        search_box = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
        )
        
        search_box.click()
        search_box.send_keys(Keys.CONTROL + "a")
        search_box.send_keys(Keys.BACKSPACE)
        search_box.send_keys(nome_grupo)
        time.sleep(2)
        search_box.send_keys(Keys.ENTER)
        time.sleep(2)

        msg_box = driver.find_element(By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
        
        # LIMPEZA E FOCO
        msg_box.click()
        msg_box.send_keys(Keys.CONTROL + "a")
        msg_box.send_keys(Keys.BACKSPACE)
        human_delay(1, 2) # Pausa antes de começar a 'digitar'

        # Formata a mensagem para o padrão WhatsApp
        msg_final = formatar_para_whatsapp(mensagem)
        
        simular_digitacao(driver, msg_box, msg_final)
        
        print("| ⏳ Aguardando 5 segundos para o WhatsApp gerar o Link Preview...")
        time.sleep(5) # <--- NOVO TEMPO DE ESPERA OBRIGATÓRIO

        msg_box.send_keys(Keys.ENTER)
        
        print(f"| ✅ WHATSAPP: Mensagem enviada com sucesso!")
        human_delay(2, 5) # Delay pós-envio

    except Exception as e:
        print(f"| ❌ WHATSAPP: Falha ao enviar para o grupo: {e}")
    
    finally:
        limpar_interface_whatsapp(driver) # GARANTIA PARA O PRÓXIMO

def enviar_whatsapp_robusto(driver, nome_grupo, mensagem, caminho_imagem):
    print(f"| 📸 WHATSAPP: Iniciando entrega para '{nome_grupo}'...")
    wait = WebDriverWait(driver, 40)
    
    aba_origem = driver.current_window_handle
    
    # --- TROCA PARA A ABA DO WHATSAPP SE NECESSÁRIO ---
    if not focar_aba_whatsapp(driver):
        return

    try:
        limpar_interface_whatsapp(driver) # PREVENÇÃO

        search_box = wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')))
        search_box.click()
        search_box.send_keys(Keys.CONTROL + "a")
        search_box.send_keys(Keys.BACKSPACE)
        search_box.send_keys(nome_grupo)
        time.sleep(2)
        search_box.send_keys(Keys.ENTER)
        time.sleep(2)

        copiar_imagem_para_clipboard(caminho_imagem)
        chat_box = wait.until(EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')))
        chat_box.click()
        # GARANTE QUE NÃO TEM TEXTO PENDENTE
        chat_box.send_keys(Keys.CONTROL + "a")
        chat_box.send_keys(Keys.BACKSPACE)
        time.sleep(1)
        
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

        print("| ⏳ Aguardando editor de legenda...")
        
        # O problema anterior era que ele achava o chat (tab=10) como legenda.
        # Agora o seletor obriga a ser 'Adicionar legenda' OU ter um aria-label que contenha 'legenda'
        # E EXCLUI explicitamente o data-tab=10
        xpath_legenda = '//div[@aria-label="Adicionar legenda"] | //div[contains(@aria-label, "legenda")] | //span[text()="Adicionar legenda"]/../following-sibling::div//div[@contenteditable="true"]'
        
        try:
            legenda_box = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, xpath_legenda))
            )

            # Validação extra: Se o elemento achado for o chat principal, espera mais um pouco
            if legenda_box.get_attribute("data-tab") == "10":
                 print("| ⚠️ Alerta: Seletor pegou o chat principal. Aguardando modal real...")
                 time.sleep(2)
                 legenda_box = driver.find_element(By.XPATH, xpath_legenda)

        except:
             print("| ⚠️ Modal de legenda não identificado pelo nome padrão. Tentando estratégia de focar no elemento ativo...")
             time.sleep(2)
             legenda_box = driver.switch_to.active_element
        
        driver.execute_script("arguments[0].focus();", legenda_box)
        time.sleep(0.5)
        
        # LIMPEZA DA LEGENDA ANTES DE COLAR
        legenda_box.send_keys(Keys.CONTROL + "a")
        legenda_box.send_keys(Keys.BACKSPACE)
        time.sleep(0.5)

        # Formata a mensagem
        msg_final = formatar_para_whatsapp(mensagem)
        pyperclip.copy(msg_final)
        
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        
        human_delay(1, 3)

        print("| 🚀 Disparando o ENVIO...")
        
        # Tenta dar Enter primeiro
        try:
            legenda_box.send_keys(Keys.ENTER)
            human_delay(1, 2)
        except: pass
        
        # Se ainda estiver na tela de imagem (botão enviar ainda lá), tenta clicar no botão
        try:
            # Lista de seletores possíveis para o botão de enviar (inclui data-icon, aria-label e spans)
            seletores_enviar = [
                '//div[@aria-label="Enviar"]',
                '//span[@data-icon="send"]',
                '//button[contains(@aria-label, "Enviar")]',
                '//span[@data-icon="send-light"]/..'
            ]
            
            for seletor in seletores_enviar:
                botoes = driver.find_elements(By.XPATH, seletor)
                if botoes:
                    print(f"| 🎯 Botão 'Enviar' encontrado ({seletor})! Clicando...")
                    driver.execute_script("arguments[0].click();", botoes[0])
                    time.sleep(1)
                    break 
        except Exception as e:
            print(f"| ⚠️ Falha ao clicar no botão físico: {e}")

        # Verificação final: se o modal de imagem ainda estiver aberto, tenta um Enter forçado
        try:
            modal_aberto = driver.find_elements(By.XPATH, '//span[@data-icon="x-viewer"]')
            if modal_aberto:
                print("| 🛠️ Modal ainda aberto. Tentando Enter forçado no elemento ativo...")
                driver.switch_to.active_element.send_keys(Keys.ENTER)
        except: pass

        time.sleep(2) # Espera técnica para o envio iniciar
        print("| ✅ WHATSAPP: Missão cumprida!")

    except Exception as e:
        print(f"| ❌ WHATSAPP: Erro no envio: {e}")
        # Tenta fechar o modal de imagem se estiver aberto (botão X)
        try:
            botao_fechar = driver.find_element(By.XPATH, '//span[@data-icon="x-viewer"]')
            botao_fechar.click()
        except: pass
    
    finally:
        limpar_interface_whatsapp(driver) # GARANTIA DE LIMPEZA
        
        # Volta para a aba que estava antes de tentar enviar (para não quebrar o fluxo principal)
        try:
            driver.switch_to.window(aba_origem)
        except: pass
        print("| 🔄 Voltando para o rastreio...")

# =========================================================
# CONTROLE DE DUPLICIDADE (CACHE 24H - VERSÃO BLINDADA)
# =========================================================
ARQUIVO_CACHE_ENVIOS = "cache_envios_24h.json"



def normalizar_texto(texto):
    """LIMPEZA PROFUNDA: Remove espaços, pontuação e converte para minúsculo."""
    if not texto: return ""
    # Remove caracteres especiais se quiser ser radical (opcional)
    # Mas só strip e lower já resolvem 99%
    return texto.strip().lower()

def verificar_se_ja_enviou_24h(titulo, grupo=None):
    """
    Retorna True se o produto já foi enviado nas últimas 24h.
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
    
    if (agora - timestamp_envio) < 172800:
        horas_restantes = (172800 - (agora - timestamp_envio)) / 3600
        print(f"| ⏳ CACHE: '{titulo[:20]}...' bloqueado por mais {horas_restantes:.1f}h.")
        return True
    else:
        del cache[titulo_chave]
        salvar_cache(cache)
        return False

def registrar_envio_24h(titulo, grupo=None):
    titulo_chave = normalizar_texto(titulo)
    if grupo:
        titulo_chave = f"{grupo}::{titulo_chave}"
    cache = carregar_cache()
    cache[titulo_chave] = time.time()
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
    
    # --- CORREÇÃO: SEPARAÇÃO BLINDADA DE ABAS ---
    aba_whatsapp = None
    
    # 1. Primeiro, caça o WhatsApp em todas as abas abertas
    if focar_aba_whatsapp(driver):
        aba_whatsapp = driver.current_window_handle
        print("| ✅ WhatsApp isolado com segurança.")
    else:
        print("| ⚠️ WhatsApp não detectado nas abas iniciais.")

    # 2. Garante que a aba de trabalho (vitrine) NÃO é o WhatsApp
    # Se a aba atual for o Zap, o robô cria uma aba nova em branco só pra ele.
    if driver.current_window_handle == aba_whatsapp:
        print("| 🔄 Criando aba exclusiva para caçar ofertas...")
        driver.execute_script("window.open('about:blank', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        
    # Agora sim, define a aba de navegação com 100% de certeza que não vai esmagar o Zap
    aba_navegacao = driver.current_window_handle 
    # ----------------------------------------------

    CATEGORIAS_ALERTADAS = set()
    PRODUTOS_PROCESSADOS_HOJE = set() 

    try: # Este é o try da linha 2462
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
            for grupo in GRUPOS_ALVO:
                try: enviar_whatsapp(driver, grupo, msg_relampago)
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
            if alvo.get("loja") == "SHOPEE":
                processar_painel_shopee(driver, PRODUTOS_PROCESSADOS_HOJE, preco_maximo=preco_maximo)
                continue
            
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

            # --- NOVO LOOP INTELIGENTE (AGORA DENTRO DO FOR DE LOJAS) ---
            PRODUTOS_VALIDOS = 0
            INDICE = 0
            
            while PRODUTOS_VALIDOS < 5 and INDICE < len(ofertas_unicas):
                driver.switch_to.window(aba_navegacao)
                produto = ofertas_unicas[INDICE]
                INDICE += 1

                # Filtro de cache rápido por grupo
                ja_enviado_em_todos = True
                for grupo in GRUPOS_ALVO:
                    if not verificar_se_ja_enviou_24h(produto['titulo'], grupo):
                        ja_enviado_em_todos = False
                        break
                
                if ja_enviado_em_todos:
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
                else:
                    url_final = gerar_link_afiliado(produto['url'], "MAGALU")

                if not url_final or not passou_filtro or preco_atual is None:
                    continue

                if preco_maximo and preco_atual > preco_maximo:
                    continue

                # ==========================================================
                # SUBSTITUA A PARTIR DAQUI: Montagem e envio da mensagem
                # ==========================================================
                
                # 1. Chama a inteligência de Copy!
                chamada = gerar_chamada_inteligente(titulo, preco_atual, alvo.get("categoria", ""), nome_autor)

                # 🌟 NOVO: ATIVANDO O CÉREBRO DO HISTÓRICO DE PREÇOS
                oportunidade, veredito, menor_preco = analisar_historico(ARQUIVO_HISTORICO, titulo, preco_atual, preco_antigo)
                atualizar_historico(ARQUIVO_HISTORICO, titulo, preco_atual)

                # 2. Monta o layout limpo e convertido para o seu padrão HTML
                mensagem_final = f"<b>{chamada}</b>\n\n"


                # Se a análise identificou que o preço tá absurdamente bom, grita no grupo!
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

                # ✅ NOVO: Se o robô encontrou um cupom, adiciona com destaque!
                if cupom_cod:
                    mensagem_final += f"\n🎟️ <b>Use o cupom: {cupom_cod}</b>\n"

                mensagem_final += f"\n🛒 <b>COMPRE AQUI:</b> 👇\n<a href='{url_final}'>CLIQUE PARA VER NO SITE</a>"

                # 1. Envia para o Telegram primeiro
                enviar_telegram(mensagem_final, url_final, image_url)
                
                teve_envio_real = False
                
                # 2. Tenta baixar a foto (se o Magalu tiver deixado a URL disponível)
                caminho_foto = None
                if image_url:
                    caminho_foto = baixar_imagem_temporaria(image_url)

                try:
                    for grupo in GRUPOS_ALVO:
                        if not verificar_se_ja_enviou_24h(titulo, grupo):
                            
                            # O Pulo do Gato para imagens ausentes:
                            if caminho_foto:
                                enviar_whatsapp_robusto(driver, grupo, mensagem_final, caminho_foto)
                            else:
                                # Se não tem imagem, manda só o texto e o link (o zap puxa a capa)
                                enviar_whatsapp(driver, grupo, mensagem_final)
                                
                            registrar_envio_24h(titulo, grupo)
                            teve_envio_real = True
                            
                            # Pausa essencial para não ser banido pelo WhatsApp
                            human_delay(DELAY_MIN_ENTRE_MENSAGENS, DELAY_MAX_ENTRE_MENSAGENS)
                            
                    if teve_envio_real:
                        PRODUTOS_VALIDOS += 1
                        print(f"| ✅ Sucesso ({alvo['nome']}): {PRODUTOS_VALIDOS}/5")
                finally:
                    # Limpa o PC
                    if caminho_foto and os.path.exists(caminho_foto):
                        try: os.remove(caminho_foto)
                        except: pass
                    # Volta o foco para a vitrine para caçar o próximo
                    driver.switch_to.window(aba_navegacao)

                # ==========================================================
                # FIM DA SUBSTITUIÇÃO (Aqui embaixo já fica o FIM DO LOOP 'for alvo')
                # ==========================================================

        # FIM DO LOOP 'for alvo in alvos_a_rodar'
        # O recuo aqui deve ser o mesmo do 'try' da linha 2462

    except Exception as e:
        print(f"| ❌ Erro Crítico no processamento geral: {e}")

    finally:
        print("--- FIM DO TURNO ---")

if __name__ == "__main__":

    try:
        # Tenta pegar o argumento digitado (ex: python script.py TODOS)
        ARGUMENTO_PRINCIPAL = sys.argv[1]
    except IndexError:
        # --- MUDANÇA ESTRATÉGICA: O PADRÃO AGORA É FEMININO ---
        # Se você só clicar no arquivo, ele vai rodar o modo "MULHER"
        ARGUMENTO_PRINCIPAL = "MULHER" 
    
    # --- MODO CUPONS (Mantido intacto) ---
    if ARGUMENTO_PRINCIPAL == "--cupons":
        URL_CUPONS = 'https://especiais.magazineluiza.com.br/magazinevoce/cupons/?showcase=magazinecelle'
        print(f"\n| === MODO CUPONS AGENDADO: {time.strftime('%H:%M:%S')} === |")
        
        driver = iniciar_driver() 
        try:
            cupons = rastrear_cupons(URL_CUPONS, driver)
            lista_mensagens = preparar_mensagem_cupons(cupons)
            
            if lista_mensagens:
                print(f"| ENVIANDO: Encontrados {len(lista_mensagens)} cupons para envio com imagem.")
                for item in lista_mensagens:
                    enviar_telegram(
                        mensagem_formatada=item['mensagem'], 
                        url_link=item['url_link'], 
                        image_url=item['image_url']
                    )
                print("| SUCESSO: Envio de cupons concluído.")
            else:
                print("| NENHUM CUPOM: Nenhum cupom novo encontrado neste turno.")
        finally:
            if driver: driver.quit()
        sys.exit(0)

    # --- MODO OFERTAS (Lógica Nova) ---
    else:
        GRUPO_ATUAL = ARGUMENTO_PRINCIPAL.upper()
        LISTA_ALVOS_A_RODAR = []

        # 1. MODO FEMININO (O Novo Padrão)
        if GRUPO_ATUAL == "MULHER" or GRUPO_ATUAL == "FEMININO":
            print("💅 MODO FOCO: Público Feminino (Ticket Baixo)!")
            # Roda a lista estratégica feminina + Shopee (que elas amam)
            # Nota: Certifique-se que LISTA_MESTRE_FEMININA foi criada lá em cima!
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_FEMININA

        # 2. MODO GERAL (Antigo "TODOS") - Use 'python script.py TODOS' para ativar
        elif GRUPO_ATUAL == "TODOS" or GRUPO_ATUAL == "GERAL":
            print("🌍 MODO GERAL: Rodando TODAS as listas (Demorado)!")
            # Junta tudo que existe
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_MAGALU + LISTA_MESTRE_AMAZON + LISTA_MESTRE_ML + LISTA_MESTRE_SHOPEE + LISTA_MESTRE_FEMININA

        # 3. MODOS ESPECÍFICOS POR LOJA (Para testes)
        elif GRUPO_ATUAL == "AMAZON":
            print("📦 MODO DE TESTE: Apenas AMAZON!")
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_AMAZON
        elif GRUPO_ATUAL == "ML" or GRUPO_ATUAL == "MERCADOLIVRE":
            print("📦 MODO DE TESTE: Apenas MERCADO LIVRE!")
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_ML
        elif GRUPO_ATUAL == "SHOPEE":
            print("📦 MODO DE TESTE: Apenas SHOPEE!")
            LISTA_ALVOS_A_RODAR = LISTA_MESTRE_SHOPEE
        # 4. MODOS MANUAIS (Shopee Links.txt)
        # Substitua o antigo bloco "MANUAL" e o "SHOPEE" por este unificado:
        elif GRUPO_ATUAL.startswith("MANUAL") or GRUPO_ATUAL.startswith("SHOPEE"):
            print("📝 MODO MANUAL PURO: Apenas links do arquivo 'shopee_links.txt'!")
            
            # Tenta pegar preço limite se tiver (ex: MANUAL50 ou SHOPEE100)
            preco_limite = None
            if any(c.isdigit() for c in GRUPO_ATUAL):
                try:
                    preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL)) # Extrai só o número
                    print(f"🏷️ FILTRO DE PREÇO ATIVO: Até R${preco_limite:.0f}")
                except: pass
            
            # Inicia o driver APENAS para o processamento manual
            # Não chamamos a função main(), então ele não abre Magalu/Amazon
            d_manual = iniciar_driver()
            try:
                processar_shopee_manual(d_manual, set(), preco_maximo=preco_limite)
            finally:
                if d_manual: d_manual.quit()
            
            sys.exit(0) # Encerra o script aqui para garantir

        # 5. TURNOS RELÂMPAGO (TODAS AS LOJAS COM FILTRO DE PREÇO)
        elif GRUPO_ATUAL.startswith("RELAMPAGO"):
            try:
                PRECO_LIMITE_RELAMPAGO = float(GRUPO_ATUAL.replace("RELAMPAGO", ""))
                print(f"⚡ TURNO RELÂMPAGO: Todas as lojas até R${PRECO_LIMITE_RELAMPAGO:.0f}!")
                LISTA_ALVOS_A_RODAR = LISTA_MESTRE_SHOPEE + LISTA_MESTRE_ML + LISTA_MESTRE_AMAZON + LISTA_MESTRE_MAGALU
                main(LISTA_ALVOS_A_RODAR, preco_maximo=PRECO_LIMITE_RELAMPAGO)
                # Também processa links manuais com o mesmo filtro
                print("\n🚀 [RELÂMPAGO] Processando links manuais com filtro...")
                d_manual = iniciar_driver()
                try:
                    processar_shopee_manual(d_manual, set(), preco_maximo=PRECO_LIMITE_RELAMPAGO)
                finally:
                    if d_manual: d_manual.quit()
                sys.exit(0)
            except ValueError:
                print(f"❌ Argumento inválido: '{GRUPO_ATUAL}'. Use RELAMPAGO50, RELAMPAGO100... etc.")
                sys.exit(1)

        # --- NOVOS MODOS INDIVIDUAIS POR LOJA (COM PREÇO) ---
        
        # 1. MAGALU R$ XX
        elif GRUPO_ATUAL.startswith("MAGALU") and any(c.isdigit() for c in GRUPO_ATUAL):
            try:
                preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL)) # Extrai só o número
                print(f"🛍️ MODO MAGALU - TETO: R${preco_limite:.0f}")
                # Roda só as listas do Magalu
                main(LISTA_MESTRE_MAGALU, preco_maximo=preco_limite)
            except: print("❌ Erro ao ler preço. Use MAGALU50, MAGALU100...")

        # 2. AMAZON R$ XX
        elif GRUPO_ATUAL.startswith("AMAZON") and any(c.isdigit() for c in GRUPO_ATUAL):
            try:
                preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL))
                print(f"📦 MODO AMAZON - TETO: R${preco_limite:.0f}")
                main(LISTA_MESTRE_AMAZON, preco_maximo=preco_limite)
            except: print("❌ Erro ao ler preço. Use AMAZON50...")

       # 3. MERCADO LIVRE R$ XX (Versão Corrigida)
        elif GRUPO_ATUAL.startswith("ML") and any(c.isdigit() for c in GRUPO_ATUAL):
            try:
                preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL))
                print(f"🤝 MODO MERCADO LIVRE - TETO: R${preco_limite:.0f}")
                # Aqui passamos a lista TODA, o filtro de preço será feito dentro do main
                main(LISTA_MESTRE_ML, preco_maximo=preco_limite)
                sys.exit(0) # Adicione isso para ele não tentar rodar o 'else' abaixo
            except: print("❌ Erro ao ler preço. Use ML50...")

        # 4. SHOPEE MANUAL R$ XX
        elif GRUPO_ATUAL.startswith("SHOPEE") and any(c.isdigit() for c in GRUPO_ATUAL):
            try:
                preco_limite = float(re.sub(r'[^0-9]', '', GRUPO_ATUAL))
                print(f"🟠 MODO SHOPEE MANUAL - TETO: R${preco_limite:.0f}")
                # Shopee é especial: vai direto para o manual
                d_manual = iniciar_driver()
                try:
                    processar_shopee_manual(d_manual, set(), preco_maximo=preco_limite)
                finally:
                    if d_manual: d_manual.quit()
            except: print("❌ Erro ao ler preço. Use SHOPEE50...")

        # ----------------------------------------------------

        # 4. MODOS POR TURNO (MANHA, TARDE, NOITE, ALMOCO)
        else:
            print(f"🕒 Configurando turno estratégico: {GRUPO_ATUAL}")
            
            # --- CORREÇÃO AQUI: BUSCA EM TODAS AS LOJAS MESTRAS ---
            alvos_magalu = selecionar_alvos_por_grupo(LISTA_MESTRE_MAGALU, GRUPO_ATUAL)
            alvos_amazon = selecionar_alvos_por_grupo(LISTA_MESTRE_AMAZON, GRUPO_ATUAL)
            alvos_ml = selecionar_alvos_por_grupo(LISTA_MESTRE_ML, GRUPO_ATUAL)
            alvos_fem = selecionar_alvos_por_grupo(LISTA_MESTRE_FEMININA, GRUPO_ATUAL)
            alvos_shopee = selecionar_alvos_por_grupo(LISTA_MESTRE_SHOPEE, GRUPO_ATUAL)
            
            # Junta tudo em uma única lista de ataque
            LISTA_ALVOS_A_RODAR = alvos_magalu + alvos_amazon + alvos_ml + alvos_fem + alvos_shopee

        # Validação final para não rodar vazio
        num_alvos = len(LISTA_ALVOS_A_RODAR)
        print(f"| DEBUG: Encontrados {num_alvos} alvos para o comando '{GRUPO_ATUAL}'.")

        if num_alvos == 0:
            print(f"\n[🛑 ERRO] Nenhuma lista encontrada para '{GRUPO_ATUAL}'.")
            print("| Carregando lista FEMININA de segurança...")
            main(LISTA_MESTRE_FEMININA)
        else:
            # Roda Magalu/Amazon (mas agora NÃO fecha o navegador no fim)
            main(LISTA_ALVOS_A_RODAR)

            # Agora passamos para a Shopee
            if GRUPO_ATUAL == "ALMOCO":
                print("\n🚀 [AUTO] Processando links manuais da Shopee (Horario de Almoco)...")
                
                # REAPROVEITA O DRIVER GLOBO (chrome_driver)
                # Não precisa chamar iniciar_driver() de novo se o anterior ainda está vivo.
                # Mas por segurança, chamamos ele, pois ele verifica se já existe conexão.
                d_manual = iniciar_driver() 
                
                try:
                    processar_shopee_manual(d_manual, set())
                except Exception as e:
                    print(f"| ❌ Erro na Shopee: {e}")
                finally:
                    # AGORA SIM, no final de tudo, podemos fechar
                    if d_manual: d_manual.quit()
