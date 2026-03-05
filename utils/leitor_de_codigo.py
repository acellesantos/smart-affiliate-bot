import re
import os

def caçar_estrelas():
    nome_arquivo = "CODIGO_SECRETO.txt"
    
    if not os.path.exists(nome_arquivo):
        print(f"❌ O arquivo {nome_arquivo} não foi encontrado na pasta!")
        print("Certifique-se de que rodou o 'espiao_local' antes.")
        return

    print(f"🕵️ Lendo {nome_arquivo} em busca da nota...\n")
    
    with open(nome_arquivo, "r", encoding="utf-8") as f:
        conteudo = f.read()

    # --- ESTRATÉGIA 1: Procurar pelo termo 'ReviewScore' (Usado no parceiro) ---
    print("--- 🔍 PISTAS COM 'ReviewScore' ---")
    # Pega 100 caracteres antes e depois da palavra ReviewScore
    matches = re.findall(r'.{0,80}ReviewScore.{0,80}', conteudo)
    if matches:
        for i, m in enumerate(matches[:3]): # Mostra os 3 primeiros casos
            print(f"[{i+1}] ...{m}...")
    else:
        print("Nenhuma pista com 'ReviewScore'.")

    # --- ESTRATÉGIA 2: Procurar por notas numéricas exatas (ex: >4.8<) ---
    print("\n--- 🔍 PISTAS COM NÚMEROS (4.x ou 5.0) ---")
    # Procura números de 3.0 a 5.0 cercados por > e < (comum em HTML)
    matches_num = re.findall(r'>\s*([345]\.\d)\s*<', conteudo)
    if matches_num:
        print(f"Encontrei estes números que parecem notas: {set(matches_num)}")
        
        # Tenta mostrar o contexto do primeiro número encontrado
        primeira_nota = matches_num[0]
        contexto = re.search(f'.{{0,80}}>{primeira_nota}<.{{0,80}}', conteudo)
        if contexto:
             print(f"Contexto do número {primeira_nota}: \n...{contexto.group()}...")
    else:
        print("Nenhuma nota numérica óbvia encontrada.")

    # --- ESTRATÉGIA 3: Procurar por 'data-testid' ---
    print("\n--- 🔍 PISTAS COM 'data-testid' ---")
    matches_id = re.findall(r'data-testid="[^"]*review[^"]*"', conteudo)
    for m in set(matches_id):
        print(f"Achei este ID: {m}")

if __name__ == "__main__":
    caçar_estrelas()