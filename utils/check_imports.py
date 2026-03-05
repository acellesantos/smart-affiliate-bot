import sys
print(f"Executando com Python: {sys.executable}")

try:
    import selenium
    print("[OK] Selenium instalado.")
    import pandas
    print("[OK] Pandas instalado.")
    import requests
    print("[OK] Requests instalado.")
    import bs4
    print("[OK] BeautifulSoup instalado.")
    print("\n[SUCESSO] Todas as bibliotecas foram carregadas corretamente.")
except ImportError as e:
    print(f"\n[ERRO] Falha ao importar. Detalhe: {e}")
