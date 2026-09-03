import requests
import time
from datetime import datetime
import os
import logging

# Configuração de logs (mostra tudo no console do Railway)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ==================== CONFIGURAÇÕES ====================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logging.error("❌ BOT_TOKEN não definido nas variáveis de ambiente!")
    exit(1)

URL = f"https://api.telegram.org/bot{TOKEN}/"

# ==================== FUNÇÕES DE CÁLCULO ====================
def calcular_rsi(precos, periodo=14):
    if len(precos) < periodo + 1:
        return 50
    ganhos = 0
    perdas = 0
    for i in range(1, periodo + 1):
        diferenca = precos[-i] - precos[-i-1]
        if diferenca >= 0:
            ganhos += diferenca
        else:
            perdas += abs(diferenca)
    ganhos_medio = ganhos / periodo
    perdas_medio = perdas / periodo
    if perdas_medio == 0:
        return 100
    rs = ganhos_medio / perdas_medio
    return 100 - (100 / (1 + rs))

def calcular_ma(precos, periodo):
    if len(precos) < periodo:
        return precos[-1] if precos else 0
    return sum(precos[-periodo:]) / periodo

# ==================== BUSCAR DADOS ====================
def buscar_dados():
    dados = {}
    # 1) Preço, RSI, médias da Binance
    try:
        url_binance = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=200"
        resp = requests.get(url_binance, timeout=10)
        resp.raise_for_status()
        velas = resp.json()
        fechamentos = [float(v[4]) for v in velas]
        preco_atual = fechamentos[-1]
        dados['preco'] = preco_atual
        dados['rsi'] = calcular_rsi(fechamentos)
        dados['ma5'] = calcular_ma(fechamentos, 5)
        dados['ma10'] = calcular_ma(fechamentos, 10)
        dados['ma30'] = calcular_ma(fechamentos, 30)
        dados['ma50'] = calcular_ma(fechamentos, 50)
        dados['ma200'] = calcular_ma(fechamentos, 200)
        preco_ontem = fechamentos[-2] if len(fechamentos) > 1 else preco_atual
        dados['variacao'] = ((preco_atual - preco_ontem) / preco_ontem) * 100
        logging.info("✅ Dados da Binance obtidos com sucesso.")
    except Exception as e:
        logging.error(f"❌ Erro na Binance: {e}")
        # Fallback para não quebrar (valores fictícios)
        dados['preco'] = 65000
        dados['rsi'] = 50
        dados['ma5'] = 64000
        dados['ma10'] = 63500
        dados['ma30'] = 62000
        dados['ma50'] = 61000
        dados['ma200'] = 58000
        dados['variacao'] = 0

    # 2) Fear & Greed
    try:
        url_fng = "https://api.alternative.me/fng/?limit=1"
        resp = requests.get(url_fng, timeout=10)
        resp.raise_for_status()
        dados['fng'] = int(resp.json()['data'][0]['value'])
        logging.info("✅ Fear & Greed obtido.")
    except Exception as e:
        logging.error(f"❌ Erro no Fear & Greed: {e}")
        dados['fng'] = 50

    # 3) Cotação do dólar (BRL)
    try:
        url_dolar = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
        resp = requests.get(url_dolar, timeout=10)
        resp.raise_for_status()
        dados['dolar'] = float(resp.json()['USDBRL']['bid'])
        logging.info("✅ Cotação do dólar obtida.")
    except Exception as e:
        logging.error(f"❌ Erro na cotação do dólar: {e}")
        dados['dolar'] = 5.2

    return dados

# ==================== ANÁLISE ====================
def analisar(dados):
    score_tec = 0
    if dados['preco'] > dados['ma200']:
        score_tec += 0.3
    else:
        score_tec -= 0.3

    if dados['rsi'] > 80:
        score_tec -= 0.3
    elif dados['rsi'] < 20:
        score_tec += 0.3

    if dados['preco'] > dados['ma5']:
        score_tec += 0.2
    else:
        score_tec -= 0.2

    score_sent = 0
    if dados['fng'] < 20:
        score_sent += 1.0
    elif dados['fng'] > 80:
        score_sent -= 1.0
    score_sent = score_sent / 1.5

    score_macro = 0
    if dados['dolar'] < 5.5:
        score_macro += 1.0
    elif dados['dolar'] > 6.0:
        score_macro -= 1.0
    score_macro = score_macro / 2

    score_total = (0.25 * score_tec) + (0.05 * score_sent) + (0.10 * score_macro)
    score_total = score_total / 0.4 if score_total != 0 else 0
    score_total = round(score_total, 2)

    if score_total >= 0.8:
        rec = "LONG (COMPRA)"
        emoji = "🟢"
    elif score_total <= -0.8:
        rec = "SHORT (VENDA)"
        emoji = "🔴"
    else:
        rec = "AGUARDAR"
        emoji = "🟡"

    return {'score': score_total, 'rec': rec, 'emoji': emoji}

# ==================== ENVIAR MENSAGEM ====================
def enviar_mensagem(chat_id, texto):
    try:
        payload = {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "Markdown"
        }
        resp = requests.post(URL + "sendMessage", json=payload, timeout=10)
        resp.raise_for_status()
        logging.info(f"✅ Mensagem enviada para {chat_id}")
    except Exception as e:
        logging.error(f"❌ Erro ao enviar mensagem: {e}")

# ==================== PROCESSAR COMANDOS ====================
def processar_comando(chat_id, comando):
    if comando == "/start":
        msg = (
            "🤖 *Bot Analista BTC ativo!*\n\n"
            "Envie /analisar para receber a análise agora.\n"
            "O bot também envia análises automáticas a cada 1 hora."
        )
        enviar_mensagem(chat_id, msg)

def processar_analise(chat_id):
    enviar_mensagem(chat_id, "🔄 Buscando dados do mercado...")
    try:
        dados = buscar_dados()
        analise = analisar(dados)

        msg = f"""
📊 *ANÁLISE BITCOIN* - {datetime.now().strftime('%d/%m/%Y %H:%M')}

💰 Preço: US$ {dados['preco']:,.2f}
📈 Variação 24h: {dados['variacao']:.2f}%
📉 RSI Diário: {dados['rsi']:.1f}
😨 Fear & Greed: {dados['fng']}

---
🎯 *SCORE TOTAL*: **{analise['score']:.2f}**

📌 *RECOMENDAÇÃO*:
{analise['emoji']} {analise['rec']}

---
_Análise automática via Railway_
"""
        enviar_mensagem(chat_id, msg)
    except Exception as e:
        logging.error(f"❌ Erro em processar_analise: {e}")
        enviar_mensagem(chat_id, f"❌ Erro ao gerar análise: {str(e)}")

# ==================== MAIN ====================
def main():
    logging.info("🤖 Bot iniciado!")
    offset = 0
    chat_id = None
    ultima_analise = 0

    while True:
        try:
            url_get = URL + f"getUpdates?offset={offset}&timeout=30"
            resp = requests.get(url_get, timeout=35)
            if resp.status_code == 200:
                dados = resp.json()
                if dados.get('ok'):
                    for update in dados['result']:
                        offset = update['update_id'] + 1
                        if 'message' in update:
                            msg = update['message']
                            chat_id = msg['chat']['id']
                            if 'text' in msg:
                                texto = msg['text']
                                if texto == '/start':
                                    processar_comando(chat_id, texto)
                                elif texto == '/analisar':
                                    processar_analise(chat_id)

            # Análise automática a cada 1 hora (3600 segundos)
            if chat_id and (time.time() - ultima_analise) >= 3600:
                logging.info("⏰ Enviando análise automática...")
                processar_analise(chat_id)
                ultima_analise = time.time()

        except Exception as e:
            logging.error(f"❌ Erro no loop principal: {e}")

        time.sleep(30)  # espera 30 segundos antes de nova verificação

if __name__ == "__main__":
    main()