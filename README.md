# 🛒 Smart Affiliate Bot | Monitoramento & Automação RPA

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Selenium](https://img.shields.io/badge/Selenium-43B02A?style=for-the-badge&logo=selenium&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Status](https://img.shields.io/badge/Status-Em%20Produ%C3%A7%C3%A3o-success)

Este é um ecossistema completo de **RPA (Robotic Process Automation)** desenvolvido para automatizar a curadoria, validação e postagem de ofertas em grupos de afiliados (WhatsApp e Telegram). O projeto une técnicas avançadas de Web Scraping com análise de dados para garantir que apenas promoções reais sejam enviadas à comunidade.

## 🤖 A Persona: "Celle"
Para humanizar a curadoria e gerar autoridade no nicho de tecnologia e promoções, o projeto utiliza a **Celle**, um avatar 3D que atua como a interface entre o robô e os usuários finais. A Celle representa a "inteligência" por trás da seleção de produtos, aumentando o engajamento e a conversão do grupo **Achadinhos da Celle**.

## ✨ Funcionalidades
- **Scraping Inteligente:** Monitoramento em tempo real (Amazon, Mercado Livre, Magalu e Shopee).
- **Validação com Pandas:** Integração com banco de dados para analisar o histórico de preços e validar se o desconto é genuíno.
- **Segurança & Mimetismo Humano:** Conexão via porta de depuração remota (9222) para evitar detecção por sistemas anti-bot.
- **Gestão de Cache:** Sistema de controle de 24h para evitar spam e reenvio de ofertas duplicadas.
- **Copywriting Dinâmico:** Geração de mensagens persuasivas adaptadas por nicho (Beleza, Tecnologia, Casa).
- **Agendamento por Turnos:** Scripts configurados para rodar em horários estratégicos (Manhã, Tarde e Noite).

## 🛠️ Tecnologias utilizadas
- **Python 3.13** (Core do projeto)
- **Selenium & BeautifulSoup4** (Navegação e extração de dados)
- **Pandas** (Tratamento de dados e histórico de preços)
- **Python-dotenv** (Gestão de variáveis de ambiente e segurança)
- **Git** para versionamento semântico

## 📂 Estrutura do Projeto

A organização segue padrões profissionais de Service Desk para facilitar a manutenção:
```
smart-affiliate-bot/
│
├── rastreador_ofertas.py      # Script principal (Core do Bot)
├── requirements.txt           # Dependências do projeto
├── .gitignore                 # Filtro de segurança (ignora .env e .venv)
│
├── scripts_automacao/         # Arquivos .bat para o Agendador de Tarefas
├── testes_homologacao/        # Scripts de teste e validação de módulos
├── utils/                     # Scripts auxiliares e modo manual
├── documentacao/              # Estratégias de venda e manuais
└── assets/
```

## 🛠️ Como Executar
1. Instale as dependências: `pip install -r requirements.txt`
2. Configure seu arquivo `.env` com os tokens do Telegram e WhatsApp.
3. Inicie o Chrome no modo debug: `chrome.exe --remote-debugging-port=9222`
4. Execute o robô: `python rastreador_ofertas.py`

## 🎯 Objetivo do projeto

Este projeto foi desenvolvido para resolver um problema real de escala e tempo:

- **Automação RPA:** Substituição do trabalho manual de busca por processos automatizados.
- **Transição de Carreira:** Aplicação de conhecimentos de Service Desk em soluções de desenvolvimento.
- **Segurança de Dados:** Implementação de boas práticas com variáveis de ambiente.
- **UX & Branding:** Uso da persona Celle para criar conexão com a comunidade.

## 🔐 Segurança de Dados
Este repositório utiliza variáveis de ambiente (`.env`) e um arquivo `.gitignore` rigoroso para garantir que credenciais de API, tokens de bots e dados sensíveis de navegação nunca sejam expostos publicamente.

---

<p align="center">
  Desenvolvido com ☕ e 🐍 por <strong>Marcelle Santos</strong><br>
  <span style="opacity:0.8; font-size:0.85em;">
    Analista de Service Desk & Desenvolvedora Python 📍 Nova Iguaçu, RJ
  </span>
</p>