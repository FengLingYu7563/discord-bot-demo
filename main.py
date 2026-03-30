import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv
import time

# model
from chat.gemini_api import setup_gemini_api
from chat.openai_api import setup_openai_api

from slash.info import info_group
from database import initialize_database

# === bot Mount time ===
from datetime import datetime
from database import add_uptime_hours, get_total_uptime, set_start_date
bot_start_time = datetime.now()
# === bot Mount time ===

load_dotenv()

bot_token = os.getenv("DISCORD_BOT_TOKEN")
gemini_api_key = os.getenv("GEMINI_API_KEY")
openai_key = os.getenv("OPENAI_API_KEY")

if not bot_token:
    print("找不到 DISCORD_BOT_TOKEN")
    exit()

if not gemini_api_key:
    print("找不到 GEMINI_API_KEY")

# 設定 Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 初始化 Bot 時就設定狀態
bot = commands.Bot(
    command_prefix="!", 
    intents=intents,
    status=discord.Status.online # online(綠燈), idle(黃燈), dnd(紅燈)
)

async def load_extensions():
    """載入所有 Cog 模組"""
    extensions = [
        "slash.chat.profile",
        "slash.mc.minecraft_control",
        "slash.music.music_player",
        "slash.ping_command",
        "slash.help.help" 
    ]
    for extension in extensions:
        try:
            await bot.load_extension(extension)
            print(f"成功載入extension: {extension}")
        except Exception as e:
            print(f"載入extension失敗: {extension}, 錯誤: {e}")
            
@bot.event
async def on_ready():
    """當機器人啟動時觸發"""   
    print(f"✅ 目前登入身份 --> {bot.user}")

    # 改status
    MY_APP_ID = "1095647007324000286"

    # activity = discord.Activity(
    #     type=discord.ActivityType.playing,
    #     name="Music | /help", 
    #     state="尋找 yukino0535 中...", 
        
    #     application_id=MY_APP_ID
    # )
    
    # await bot.change_presence(status=discord.Status.online, activity=activity)
    
    # === bot Mount time ===
    async def update_presence():
        await asyncio.to_thread(set_start_date, datetime.now().strftime("%Y-%m-%d"))
        while True:
            current_hours = (datetime.now() - bot_start_time).total_seconds() / 3600
            total_hours = await asyncio.to_thread(get_total_uptime) + current_hours
            days = int(total_hours // 24) + 1
            await bot.change_presence(
                status=discord.Status.online,
                activity=discord.Activity(
                    type=discord.ActivityType.playing,
                    name="Music | /help",
                    state=f"尋找 yukino0535 的第 {days} 天...",
                    application_id=MY_APP_ID
                )
            )
            await asyncio.sleep(3600)
            await asyncio.to_thread(add_uptime_hours, 1)
    # === bot Mount time ===
    
    print(f"已啟動status")
    
    try:
        # 同步斜線指令
        slash = await bot.tree.sync()
        print(f"✅ 載入 {len(slash)} 個斜線指令")
    except Exception as e:
        print(f"同步斜線指令失敗: {e}")

def main():
    """主程式啟動點"""
    try:
        initialize_database()
    except Exception as e:
        print(f"資料庫初始化失敗：{e}")
        return

    # 調整用哪個 API
    if openai_key:
        print("啟動模式：OpenAI API (GPT-4o-mini)")
        setup_openai_api(bot, openai_key)
    elif gemini_api_key:
        print("啟動模式：Gemini API")
        setup_gemini_api(bot, gemini_api_key)
    else:
        print("找不到任何 API Key (OpenAI 或 Gemini)")

    # 載入 Group 指令
    bot.tree.add_command(info_group)
    
    async def start_bot():
        # 在啟動機器人前載入 Cog
        await load_extensions()
        print("開始運行機器人...")
        await bot.start(bot_token)

    try:
        asyncio.run(start_bot())
    except Exception as e:
        print(f"程式無法啟動。錯誤：{e}")


if __name__ == "__main__":
    main()
