from flask import Flask, request, jsonify
import os
import re
import requests
import time
from flask_cors import CORS
from dotenv import load_dotenv
from threading import Timer
import discord

# Inicialização do bot Discord para leitura de mensagens
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = discord.Client(intents=intents)

# Carregar variáveis de ambiente
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

app = Flask(__name__)
CORS(app, resources={r"/send": {"origins": "*"}})

# Configuração do logger
import logging
logging.basicConfig(level=logging.INFO)

# Armazenamento temporário de IPs já enviados
sent_ips = set()

def clear_sent_ips():
    """Função que limpa os IPs enviados a cada 1 hora."""
    global sent_ips
    sent_ips.clear()
    print("🔄 Cache de IPs resetado.")

# Agendar a limpeza a cada 30 minutos com Timer recursivo
def schedule_cache_reset():
    def reset():
        if sent_ips:
            clear_sent_ips()
        schedule_cache_reset()  # reagenda após execução
        print("🔄 Timer to cache cleanses.")
    Timer(1800, reset).start()  # 1800 segundos = 30 minutos

schedule_cache_reset()

def format_message(ip_port, password, timestamp):
    """Formata a mensagem no formato desejado para o Discord."""
    return {
        "content": f"🎮🔹ᐇ **Console:** ```connect {ip_port}; password {password}```\n"
                   f"⏳ **Expires:** <t:{timestamp}:R>"
    }

@app.route("/send", methods=["POST"])
def send_to_discord():
    """Recebe um IP:PORT/PASSWORD e envia para o Discord se ainda não tiver sido enviado."""
    data = request.json
    if not data or "address" not in data:
        return jsonify({"error": "Formato inválido. Enviar JSON com {'address': 'IP:PORT/PASSWORD'}"}), 400

    # Obter o endereço IP do solicitante
    requester_ip = request.remote_addr
    logging.info(f"Requisição recebida de IP: {requester_ip}")

    # Extrair IP, Porta e Senha usando regex
    match = re.search(r"([\d.]+:\d+)/(\w+)", data["address"])
    if not match:
        return jsonify({"error": "Endereço inválido. Use o formato correto 'IP:PORT/PASSWORD'"}), 400

    ip_port = match.group(1)  # Exemplo: 203.159.80.52:27053
    password = match.group(2)  # Exemplo: GC7440

    # Verificar se já foi enviado
    if ip_port in sent_ips:
        logging.info(f"🔄 IP já enviado: {ip_port}")
        return jsonify({"message": "IP já foi enviado anteriormente, ignorado."}), 200

    # Adicionar ao cache
    sent_ips.add(ip_port)

    timestamp = int(time.time()) + 180

    message = format_message(ip_port, password, timestamp)

    # Enviar para o Discord via Webhook
    response = requests.post(DISCORD_WEBHOOK_URL, json=message)
    if response.status_code == 204:
        return jsonify({"message": "Mensagem enviada com sucesso!"}), 200
    else:
        sent_ips.remove(ip_port)
        return jsonify({"error": "Falha ao enviar mensagem para o Discord"}), 500

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    match = re.search(r"steam://connect/([\d.]+:\d+)/(\w+)", message.content)
    if match:
        ip_port = match.group(1)
        password = match.group(2)
        response = (
            f"🎮🔹ᐇ **Comando Console:** ```connect {ip_port}; password {password}```"
        )
        await message.channel.send(response)

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)).start()
    bot.run(TOKEN)
