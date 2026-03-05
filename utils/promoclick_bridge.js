import requests

TOKEN = "8221967404:AAEPBsGwc_5oHm71hwvZKf3UCI3A62DYAZk"
CHAT_ID = "-1003442405256"

def enviar_mensagem(texto):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": texto
    }

    r = requests.post(url, json=payload)
    if r.status_code == 200:
        print("Mensagem enviada!")
    else:
        print("Erro:", r.text)


# Exemplo de envio
enviar_mensagem("PromoClick • Operação Black Friday 🚨")
