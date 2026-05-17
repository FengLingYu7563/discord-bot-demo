import discord
import google.generativeai as genai # type: ignore
from discord.ext import commands
import os
import json
import time
import random

# model
from database import get_user_profile, update_user_profile, add_to_history

msg_cooldowns = []

MOOD_TIMEOUT = 20 * 60
MOOD_POOL = ["屁孩", "溫柔", "普通"]
MOOD_WEIGHTS = [40, 35, 25]
MOOD_INSTRUCTIONS = {
    "屁孩": "【當前心情：屁孩模式】陰陽怪氣、嘴硬、炫耀，自認比對方聰明，死不認錯。",
    "溫柔": "【當前心情：撫媚模式】感受對方情緒，給予溫暖體貼的回應，帶一點點傲嬌。",
    "普通": "【當前心情：普通模式】依對方的情緒和話題自然回應，不刻意強調人設。",
}

KEYWORD_LIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "keyword_list.txt")
SYSTEM_RULE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "system_rule.txt")

def parse_gemini_response(text):
    if '<DATABASE_UPDATE>' in text:
        try:
            message_content, json_str = text.split('<DATABASE_UPDATE>', 1)
            data_to_update = json.loads(json_str.strip())
            return message_content.strip(), data_to_update
        except json.JSONDecodeError:
            print(f"解析 Gemini 回應中的 JSON 失敗: {json_str}")
            return text, None
    return text, None

def read_keyword_filter():
    try:
        with open(KEYWORD_LIST_PATH, 'r', encoding='UTF-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"找不到 {KEYWORD_LIST_PATH}，使用空關鍵字清單。")
        return []


def read_system_rule():
    try:
        with open(SYSTEM_RULE_PATH, 'r', encoding='UTF-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"找不到檔案 {SYSTEM_RULE_PATH}")
        return ""

def setup_gemini_api(bot: commands.Bot, api_key: str):
    if not api_key:
        print("提供 Gemini API 金鑰。")
        return

    prompt_injection_keywords = read_keyword_filter()
    my_system_instruction = read_system_rule()

    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=my_system_instruction,
            safety_settings=safety_settings
        )
        print("Gemini API 已成功配置")
    except Exception as e:
        print(f"無法配置 Gemini API 詳細錯誤：{e}")
        model = None
        return

    @bot.event
    async def on_message(message):
        global msg_cooldowns
        if message.author == bot.user:
            return

        is_mentioned = bot.user.mentioned_in(message)
        is_reply_to_bot = message.reference and message.reference.resolved and message.reference.resolved.author == bot.user

        if not is_mentioned and not is_reply_to_bot:
            await bot.process_commands(message)
            return

        current_time = time.time()
        msg_cooldowns = [t for t in msg_cooldowns if current_time - t < 60]
        if len(msg_cooldowns) >= 5:
            return

        other_bots = [u for u in message.mentions if u.bot and u.id != bot.user.id]
        if model is None:
            await message.channel.send("抱歉，我目前無法連線到 Gemini API。")
            return

        user_input = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not user_input or any(keyword in user_input for keyword in prompt_injection_keywords):
            user_input = "使用者沒有輸入"

        try:
            user_id = str(message.author.id)
            user_profile = get_user_profile(user_id)
            
            # --- 獲取對話紀錄（只取 20 分鐘內的訊息）---
            history_context = ""
            now = time.time()
            raw_history = user_profile.get('recent_history', []) if user_profile else []
            recent_history = [h for h in raw_history if now - h.get('t', 0) <= MOOD_TIMEOUT]
            for h in recent_history:
                role_label = "[我說過]" if h.get('r') == 'bot' else "[對方說過]"
                history_context += f"{role_label}: {h.get('m')}\n"

            # --- 心情模式（連動 20 分鐘判斷：有近期訊息就沿用，否則重新抽） ---
            last_mood = user_profile.get('current_mood') if user_profile else None
            if last_mood and recent_history:
                current_mood = last_mood
            else:
                current_mood = random.choices(MOOD_POOL, weights=MOOD_WEIGHTS)[0]
                update_user_profile(user_id, {"current_mood": current_mood})
            mood_instruction = MOOD_INSTRUCTIONS[current_mood]

            if user_profile:
                keywords = user_profile.get('keywords', [])
                observations = user_profile.get('observations', [])
                keywords_str = "、".join(keywords) if keywords else "（尚無記錄）"
                observations_str = "、".join(observations) if observations else "（尚無記錄）"
                user_info_prompt = (
                    f"使用者資訊: 名稱: {user_profile.get('name')}, "
                    f"角色: {user_profile.get('current_role')}\n"
                    f"已知興趣與事實: {keywords_str}\n"
                    f"長期人格觀察: {observations_str}\n"
                )
                full_input = f"【最近對話紀錄】\n{history_context}\n{user_info_prompt}使用者當前輸入: {user_input}"
            else:
                full_input = f"【最近對話紀錄】\n{history_context}\n使用者當前輸入: {user_input}"

            is_war = False
            if other_bots or "吵架" in user_input:
                is_war = True
                if other_bots:
                    target_bot = other_bots[0]
                    full_input += f"\n【緊急指令：開戰模式】對方是機器人 <@{target_bot.id}>。立刻發起猛烈攻擊，回覆開頭必須包含標記。"
            else:
                full_input += f"\n{mood_instruction}"

            async with message.channel.typing():
                response = model.generate_content(
                    full_input,
                    stream=False,
                    generation_config=genai.types.GenerationConfig(temperature=1)
                )
                full_response, data_to_update = parse_gemini_response(response.text)

                if data_to_update:
                    new_data = {}
                    if 'keywords' in data_to_update:
                        old_keywords = set(user_profile.get('keywords', [])) if user_profile else set()
                        new_data['keywords'] = list(old_keywords.union(set(data_to_update['keywords'])))
                    if 'observations' in data_to_update:
                        old_obs = set(user_profile.get('observations', [])) if user_profile else set()
                        new_data['observations'] = list(old_obs.union(set(data_to_update['observations'])))
                    update_user_profile(user_id, new_data)
            
            await message.channel.send(full_response)
            msg_cooldowns.append(time.time())

            if not is_war:
                add_to_history(user_id, "user", user_input)
                add_to_history(user_id, "bot", full_response)

        except Exception as e:
            print(f"Gemini API 發生錯誤: {e}")
            await message.channel.send("我現在懶得理你。")
        
        await bot.process_commands(message)