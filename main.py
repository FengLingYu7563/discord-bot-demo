import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv

# model
from chat.gemini_api import setup_gemini_api
from slash.info import info_group
from database import initialize_database

load_dotenv()

bot_token = os.getenv("DISCORD_BOT_TOKEN")
gemini_api_key = os.getenv("GEMINI_API_KEY")

if not bot_token:
    print("❌ 警告: 找不到 DISCORD_BOT_TOKEN")
    exit()

if not gemini_api_key:
    print("❌ 警告: 找不到 GEMINI_API_KEY")

# 設定 Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def load_extensions():
    """載入所有 Cog 模組"""
    # 要載入的 cog 模組列表
    extensions = [
        "slash.chat.profile",
        "slash.mc.minecraft_control" 
    ]
    for extension in extensions:
        try:
            await bot.load_extension(extension)
            print(f"✅ 成功載入擴展模組: {extension}")
        except Exception as e:
            print(f"❌ 載入擴展模組失敗: {extension}, 錯誤: {e}")
            
@bot.event
async def on_ready():
    """當機器人啟動時觸發"""
    print(f"✅ 目前登入身份 --> {bot.user}")
    try:
        # 同步斜線指令
        slash = await bot.tree.sync()
        print(f"✅ 載入 {len(slash)} 個斜線指令")
    except Exception as e:
        print(f"❌ 同步斜線指令失敗: {e}")

# bot.tree.add_command(info_group)

# def main():
#     """主程式啟動點"""
    
#     setup_gemini_api(bot, gemini_api_key)

#     print("🟢 開始運行機器人...")
#     try:
#         bot.run(bot_token)
#     except Exception as e:
#         print(f"致命錯誤：程式無法啟動。錯誤訊息：{e}")
def main():
    """主程式啟動點"""
    # 在機器人啟動前初始化資料庫
    try:
        initialize_database()
    except Exception as e:
        print(f"❌ 資料庫初始化失敗：{e}")
        return

    # 初始化 Gemini API
    setup_gemini_api(bot, gemini_api_key)

    # 載入 Group 指令 (你原本的方式)
    bot.tree.add_command(info_group)
    
    async def start_bot():
        # 在啟動機器人前載入 Cog
        await load_extensions()
        print("🟢 開始運行機器人...")
        await bot.start(bot_token)

    try:
        asyncio.run(start_bot())
    except Exception as e:
        print(f"❌ 致命錯誤：程式無法啟動。錯誤訊息：{e}")


if __name__ == "__main__":
    main()
