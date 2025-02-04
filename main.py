import discord
import re
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Ativar intents necessários
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Regex para capturar "steam://connect/IP:PORT/PASSWORD"
    match = re.search(r"steam://connect/([\d.]+:\d+)/(\w+)", message.content)
    
    if match:
        ip_port = match.group(1)  # 203.159.80.52:27053
        password = match.group(2)  # GC7440

        # Mensagem formatada
        response = (
            f"🎮🔹 **Comando Console:** ```connect {ip_port}; password {password}```"
        )
        await message.channel.send(response)

bot.run(TOKEN)