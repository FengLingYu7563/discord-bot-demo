import discord
from discord.ext import commands
from discord import app_commands
import subprocess
import os
import asyncio

POWERSHELL_SCRIPT_PATH = r"C:\Users\user\Downloads\mcServer\backup_minecraft.ps1"

# 允許使用指令的DC ID
ALLOWED_USER_IDS = [
    274512404799291393
]  

class MinecraftControl(commands.Cog):
    """
    處理 Minecraft 伺服器遠端控制的斜線指令 Cog。
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.script_exists = os.path.exists(POWERSHELL_SCRIPT_PATH)
        
        # 啟動時檢查路徑
        if not self.script_exists:
            print(f"⚠️ **警告：找不到 Minecraft 腳本！**")
            print(f"路徑: {POWERSHELL_SCRIPT_PATH}")
            print("`/mc_restart` 指令將被禁用。")
        else:
            print(f"✅ 找到 Minecraft 腳本：{POWERSHELL_SCRIPT_PATH}")

    # --- Slash Command ---

    @app_commands.command(name="mc_restart", description="【需權限】重啟 minecraft 伺服器")
    async def mc_restart_command(self, interaction: discord.Interaction):
        """
        執行備份與重啟腳本。
        """
        # 1. 腳本存在性檢查 (當路徑不存在時，指令會被禁用)
        if not self.script_exists:
            await interaction.response.send_message(
                "❌ **功能已禁用！** 此 Bot 運行的電腦上找不到 Minecraft 備份腳本。",
                ephemeral=True
            )
            return

        # 2. 權限檢查
        if interaction.user.id not in ALLOWED_USER_IDS:
            await interaction.response.send_message(
                "❌ **權限不足！** 您無權執行此指令。", 
                ephemeral=True
            )
            return

        # 3. 回應使用者，確認操作已開始
        await interaction.response.defer(ephemeral=False)
        
        # 4. 執行 PowerShell 腳本
        try:
            command = [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-File", POWERSHELL_SCRIPT_PATH
            ]
            
            result = await asyncio.to_thread(
                subprocess.run, 
                command, 
                capture_output=True, 
                text=True, 
                check=True, 
                encoding='utf-8',
                timeout=200 # 200 秒超時
            )

            # 5. 判斷並發送結果
            output = result.stdout or ""
            if "備份完成" in output and "伺服器已在背景啟動" in output:
                await interaction.followup.send(
                    f"🎉 **伺服器重啟完成！**\n"
                    f"備份與重啟程序已成功執行。伺服器現已在背景啟動。",
                    ephemeral=False
                )
            else:
                 await interaction.followup.send(
                    f"⚠️ **程序完成，但輸出不完整**\n"
                    f"備份與重啟程序已執行，但日誌未包含完整成功訊息。請手動檢查伺服器。",
                    ephemeral=False
                )

        except subprocess.CalledProcessError as e:
            error_output = e.stderr or e.stdout or ""
            if "備份完成" in error_output and "伺服器已在背景啟動" in error_output:
                 await interaction.followup.send(
                    f"⚠️ **程序完成，但有警告**\n"
                    f"備份與重啟程序已成功執行，但存在 **文件鎖定警告** (屬正常現象，可忽略)。",
                    ephemeral=False
                )
            else:
                 await interaction.followup.send(
                    f"❌ **執行失敗！** 腳本執行時發生嚴重錯誤，請檢查伺服器主機日誌。\n"
                    f"錯誤訊息：\n```bash\n{error_output[-1500:]}\n```", 
                    ephemeral=False
                )
        except asyncio.TimeoutError:
            await interaction.followup.send(
                f"⏰ **執行超時！** 腳本執行超過 200 秒，已強制停止等待。請手動檢查伺服器狀態。",
                ephemeral=False
            )
        except Exception as e:
            await interaction.followup.send(
                f"💣 **Bot 內部錯誤！** 無法啟動指令。\n錯誤: `{e}`",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    """將 Cog 加入 Bot"""
    await bot.add_cog(MinecraftControl(bot))