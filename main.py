from flask import Flask, request, jsonify
import os
import re
import requests
import time
from flask_cors import CORS
from dotenv import load_dotenv
load_dotenv() # Moved up
TOKEN = os.getenv("DISCORD_TOKEN") # Moved here
from threading import Timer
import discord

# Inicialização do bot Discord para leitura de mensagens

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = discord.Client(intents=intents)

# Carregar variáveis de ambiente
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

app = Flask(__name__)
CORS(app, resources={r"/send": {"origins": "*"}})

# Configuração do logger
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

# In-Memory Cache for Sent IPs:
# `sent_ips` is an in-memory Python set used as a cache to track IP addresses
# that have already been processed and sent to Discord.
#
# Implications of In-Memory Nature:
# - Volatility: The cache state is lost if the application restarts.
# - Scalability Issues: In a multi-instance deployment (e.g., running multiple
#   processes or containers of this app for load balancing), each instance would
#   have its own independent `sent_ips` cache. This would lead to inconsistent
#   behavior, as an IP processed by one instance would not be known to others,
#   potentially causing duplicate messages.
# - Single Point of Failure: Tied to the health of the single process.
#
# Alternatives for Persistent/Shared Cache:
# For robust, scalable, and persistent caching, an external service like Redis,
# Memcached, or a database (e.g., PostgreSQL, MySQL with appropriate caching
# strategies) would be required. This would allow all instances to share a common
# cache state.
sent_ips = set()

def clear_sent_ips():
    """
    Função que limpa os IPs enviados a cada 1 hora.
    This cache clearing is in-memory and specific to this single process.
    If scaled to multiple instances, each would clear its own cache independently.
    """
    global sent_ips
    sent_ips.clear()
    print("🔄 Cache de IPs resetado.")

# Agendar a limpeza a cada 30 minutos com Timer recursivo
def schedule_cache_reset():
    """
    Schedules the `clear_sent_ips` function to run periodically using a Timer.
    This Timer-based scheduling is in-memory and tied to this specific process.
    In a multi-instance deployment, each instance would run its own independent Timer,
    leading to multiple, uncoordinated cache clearing operations if a shared cache
    (like Redis) was used without a centralized scheduling mechanism.
    For distributed tasks or cron jobs, consider solutions like Celery with a message
    broker, or Kubernetes CronJobs.
    """
    def reset():
        if sent_ips:
            clear_sent_ips()
        schedule_cache_reset()  # reagenda após execução
        print("🔄 Timer to cache cleanses.")
    Timer(1800, reset).start()  # 1800 segundos = 30 minutos

schedule_cache_reset()

@app.after_request
def log_request_info(response):
    """Logs information about the request and response."""
    app.logger.info(
        f'{request.remote_addr} - "{request.method} {request.url}" {response.status_code}'
    )
    return response

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
    # requester_ip = request.remote_addr # Removed as it's now logged by @app.after_request
    # logging.info(f"Requisição recebida de IP: {requester_ip}") # Removed

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

    # Process Startup Model:
    # The Flask web server and the Discord bot are started in the same process,
    # each running in its own thread.
    #
    # Implications:
    # - Simplicity: Easy to manage for small applications or single-instance deployments.
    # - Fault Isolation: A critical unhandled exception in one thread (e.g., in a Flask route
    #   or Discord bot event handler) could potentially crash the entire process, affecting both
    #   the web server and the bot.
    # - Scaling: Both components scale together. If the bot becomes resource-intensive,
    #   the web server performance might be impacted, and vice-versa. They cannot be scaled
    #   independently (e.g., running multiple instances of the web server without also running
    #   multiple instances of the bot).
    # - GIL Limitations: For CPU-bound tasks, Python's Global Interpreter Lock (GIL) means
    #   that threads may not achieve true parallelism on multi-core processors.
    #   (Though for I/O-bound tasks like these, threading is generally effective).
    #
    # Alternatives for Robust/Scalable Deployments:
    # - Separate Processes: Run the Flask app and the Discord bot as completely separate
    #   processes. This can be achieved using:
    #     - A process manager like Gunicorn or uWSGI for the Flask application.
    #     - Running the Discord bot script independently (e.g., `python bot_script.py`).
    #     - Tools like Supervisor or systemd to manage these separate processes.
    #   This improves fault isolation and allows independent scaling.
    # - Containerization: Package each component (Flask app, Discord bot) into its own
    #   Docker container and manage them with an orchestrator like Docker Compose or Kubernetes.

    # Flask server configuration
    port = int(os.getenv("PORT", "5001"))
    flask_debug_env = os.getenv("FLASK_DEBUG", "false").lower()
    debug_mode = flask_debug_env in ["true", "1", "yes"]

    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, debug=debug_mode, use_reloader=False)).start()
    bot.run(TOKEN)
