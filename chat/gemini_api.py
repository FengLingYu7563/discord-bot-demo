# gemini_api.py
import discord
import google.generativeai as genai #type: ignore
from discord.ext import commands
import os
import json

# model
from database import get_user_profile, update_user_profile

# 使用 os.path.join 來建構路徑，確保跨作業系統相容性
KEYWORD_LIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "keyword_list.txt")
SYSTEM_RULE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "system_rule.txt")

# 新增一個輔助函數來解析 Gemini 的回應
def parse_gemini_response(text):
    """
    解析 Gemini 回應，將訊息內容與資料庫更新資訊分離。
    預期的格式是: "回覆訊息內容 <DATABASE_UPDATE> {"key": "value"}"
    """
    if '<DATABASE_UPDATE>' in text:
        try:
            message_content, json_str = text.split('<DATABASE_UPDATE>', 1)
            # 嘗試解析 JSON 字串
            data_to_update = json.loads(json_str.strip())
            return message_content.strip(), data_to_update
        except json.JSONDecodeError:
            print(f"❌ 解析 Gemini 回應中的 JSON 失敗: {json_str}")
            return text, None
    return text, None

def read_keyword_filter():
    """從檔案讀取關鍵字清單"""
    try:
        with open(KEYWORD_LIST_PATH, 'r', encoding='UTF-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"警告: 找不到檔案 {KEYWORD_LIST_PATH}，將使用空關鍵字清單。")
        return []

def read_system_rule():
    """從檔案讀取系統指令"""
    try:
        with open(SYSTEM_RULE_PATH, 'r', encoding='UTF-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"警告: 找不到檔案 {SYSTEM_RULE_PATH}，將使用空系統指令。")
        return ""
    
def setup_gemini_api(bot: commands.Bot, api_key: str):
    """設定 Gemini API 並註冊 on_message 事件"""
    if not api_key:
        print("❌ 錯誤：未提供 Gemini API 金鑰。")
        return

    prompt_injection_keywords = read_keyword_filter()
    my_system_instruction = read_system_rule()
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=my_system_instruction
        )
        print("✅ Gemini API 已成功配置")
    except Exception as e:
        print(f"❌ 錯誤：無法配置 Gemini API 詳細錯誤：{e}")
        model = None
        return

    @bot.event
    async def on_message(message):
        """處理來自 Discord 的訊息"""
        # 忽略自己的訊息
        if message.author == bot.user:
            return

        is_mentioned = bot.user.mentioned_in(message)
        is_reply_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == bot.user

        # 如果沒有被提及或回覆，則直接處理指令
        if not is_mentioned and not is_reply_to_bot:
            await bot.process_commands(message)
            return

        if model is None:
            await message.channel.send("抱歉，我目前無法連線到 Gemini API。")
            return

        user_input = message.content.replace(f'<@{bot.user.id}>', '').strip()

        # 檢查是否為空的輸入或包含關鍵字
        if not user_input or any(keyword in user_input for keyword in prompt_injection_keywords):
            user_input = "使用者沒有輸入"
                    
        try:
            # 新增: 獲取使用者資料
            user_id = str(message.author.id)
            user_profile = get_user_profile(user_id)
            
            if user_profile:
                user_info_prompt = f"使用者資訊: 名稱: {user_profile.get('name')}, 角色: {user_profile.get('current_role')}\n"
                full_input = user_info_prompt + user_input
            else:
                full_input = user_input
                
            # 顯示「機器人正在打字中...」
            async with message.channel.typing():
                response = model.generate_content(
                    user_input,
                    stream=False,
                    generation_config=genai.types.GenerationConfig(
                        temperature=1
                    )
                )
                
                # 新增: 解析 Gemini 的回應
                full_response, data_to_update = parse_gemini_response(response.text)

                # 如果解析到要更新的資料，則呼叫更新函數
                if data_to_update:
                # 獲取舊的關鍵字和註解
                    old_keywords = set(user_profile.get('keywords', []))
                    old_notes = user_profile.get('gpt_notes', '')

                    # 合併新的資料
                    new_data = {}
                    if 'keywords' in data_to_update:
                        new_keywords = set(data_to_update['keywords'])
                        merged_keywords = list(old_keywords.union(new_keywords))
                        new_data['keywords'] = merged_keywords

                    if 'gpt_notes' in data_to_update:
                        new_notes = data_to_update['gpt_notes']
                        # 這裡的邏輯需要根據你的需求調整
                        # 最簡單的方式是替換，或者你也可以在這裡寫邏輯來合併句子
                        new_data['gpt_notes'] = new_notes

                    # 呼叫更新函數
                    update_user_profile(user_id, new_data)
            
            await message.channel.send(full_response)
        except Exception as e:
            await message.channel.send(f"處理請求時發生了錯誤：{e}")
        
        # 確保在處理完後，讓 bot 繼續處理其他指令
        await bot.process_commands(message)