import discord
from openai import OpenAI
from discord.ext import commands
import os
import re
import json
import time
import random

# 引入你的資料庫邏輯
from database import get_user_profile, update_user_profile, add_to_history

# 全域變數：紀錄發話時間戳記
msg_cooldowns = []

# 路徑設定
KEYWORD_LIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "keyword_list.txt")
SYSTEM_RULE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "system_rule.txt")
PROMPT_INJECTION_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "prompt_injection_list.txt")

# 吵架模式設定
WAR_TIMEOUT = 30 * 60  # 30 分鐘後自動解除機器人戰爭狀態
WAR_MAX_REPLIES = 3    # 機器人對戰最多回覆次數

# 心情模式設定
MOOD_TIMEOUT = 20 * 60  # 20 分鐘內沿用同一個心情
MOOD_POOL = ["屁孩", "溫柔", "普通"]
MOOD_WEIGHTS = [40, 35, 25]
MOOD_INSTRUCTIONS = {
    "屁孩": "【當前心情：屁孩模式】陰陽怪氣、嘴硬、炫耀，自認比對方聰明，死不認錯。",
    "溫柔": "【當前心情：撫媚模式】感受對方情緒，給予溫暖體貼的回應，帶一點點傲嬌。",
    "普通": "【當前心情：普通模式】依對方的情緒和話題自然回應，不刻意強調人設。",
}

def parse_openai_response(text):
    if '<DATABASE_UPDATE>' in text:
        try:
            message_content, json_str = text.split('<DATABASE_UPDATE>', 1)
            data_to_update = json.loads(json_str.strip())
            return message_content.strip(), data_to_update
        except json.JSONDecodeError:
            return text, None
    return text, None

def read_keyword_filter():
    try:
        with open(KEYWORD_LIST_PATH, 'r', encoding='UTF-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []

def read_prompt_injection_list():
    try:
        with open(PROMPT_INJECTION_PATH, 'r', encoding='UTF-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []

def read_system_rule():
    try:
        with open(SYSTEM_RULE_PATH, 'r', encoding='UTF-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""

def setup_openai_api(bot: commands.Bot, api_key: str):
    if not api_key:
        print("未提供 OpenAI API 金鑰。")
        return

    prompt_injection_keywords = read_keyword_filter() + read_prompt_injection_list()
    my_system_instruction = read_system_rule()

    try:
        client = OpenAI(api_key=api_key)
        print("OpenAI API (GPT-4o-mini) 已成功配置")
    except Exception as e:
        print(f"無法配置 OpenAI API：{e}")
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

        other_bots = [u for u in message.mentions if u.id != bot.user.id]
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

            current_role = user_profile.get('current_role', '')
            user_info = f"使用者資訊: 名稱: {user_profile.get('name', '未知')}, 你的當前角色: {current_role if current_role else '預設屁孩'}\n" if user_profile else ""

            # --- 心情模式（連動 20 分鐘判斷：有近期訊息就沿用，否則重新抽） ---
            last_mood = user_profile.get('current_mood') if user_profile else None
            if last_mood and recent_history:
                current_mood = last_mood
            else:
                current_mood = random.choices(MOOD_POOL, weights=MOOD_WEIGHTS)[0]
                update_user_profile(user_id, {"current_mood": current_mood})
            mood_instruction = MOOD_INSTRUCTIONS[current_mood]

            # --- 戰爭狀態記憶邏輯 ---
            war_instruction = ""
            is_bot_war = False
            is_user_war = False
            target_mention = ""

            # 1. 判定當前對象
            actual_target_id = None
            if other_bots:
                actual_target_id = other_bots[0].id
            elif message.reference and message.reference.resolved:
                resolved_author = message.reference.resolved.author
                if resolved_author.bot and resolved_author.id != bot.user.id:
                    actual_target_id = resolved_author.id

            # 2. 從 user_profile 讀取上次的戰爭狀態
            last_war_target = user_profile.get('last_war_target') if user_profile else None
            last_war_time = user_profile.get('last_war_time', 0) if user_profile else 0
            war_reply_count = user_profile.get('war_reply_count', 0) if user_profile else 0

            # 3. 若當前沒有新目標，判斷是否延續上次的戰爭
            # 條件：30分鐘內且回覆次數未超過 3 次
            if not actual_target_id and last_war_target:
                if time.time() - last_war_time <= WAR_TIMEOUT and war_reply_count < WAR_MAX_REPLIES:
                    actual_target_id = last_war_target
                else:
                    # 超時或達到回覆上限，清除戰爭狀態
                    update_user_profile(user_id, {"last_war_target": None, "last_war_time": None, "war_reply_count": 0})

            # 4. 根據對象生成指令
            if actual_target_id:
                is_bot_war = True
                target_mention = f"<@{actual_target_id}>"
                war_instruction = (
                    f"\n【最高指令：對外戰爭】對象是機器人 {target_mention}。"
                    f"\n1. 必須以本體「細膩屁孩」立場回擊，禁止使用其他身分。"
                    f"\n2. **格式要求：每一則回覆的最開頭必須是 {target_mention}，嚴禁省略。**"
                    f"\n3. **格式禁令：禁止使用任何括號 ( ) 內容，嚴禁輸出內心戲或神態描述，僅限純文字對話。**"
                )
                # 更新戰爭目標、時間戳記與回覆計數
                update_user_profile(user_id, {
                    "last_war_target": actual_target_id,
                    "last_war_time": time.time(),
                    "war_reply_count": war_reply_count + 1
                })

            elif "吵架" in user_input or "廢物" in user_input or "爛" in user_input:
                is_user_war = True
                target_mention = f"<@{message.author.id}>"
                war_instruction = (
                    f"\n【關係衝突指令】當前與你對話的是 {target_mention}。"
                    f"\n1. 必須嚴格遵循「{current_role if current_role else '屁孩'}」與對方之間的「身份關係」來決定回覆基調。"
                    f"\n2. 所有的衝突表現（不滿、戲弄、勸誡或反擊）必須符合該角色的社會地位與位格設定，例如：若角色是女僕，面對挑釁應表現出委屈、受傷或卑微的勸誡；若為老師，應使用嚴厲但有教養的斥責或調教語氣；若為流氓，應表現出粗魯、不講理的態度(無腦噴髒話也沒關係)。"
                    f"\n回覆開頭須標記 {target_mention}。"
                    f"\n3. **格式禁令：禁止使用任何括號 ( ) 內容，僅限純文字對話。**"
                    f"\n4. 維持劇情張力與跳 Tone 的性格，回覆開頭須標記 {target_mention}。"
                )
            else:
                # 一般對話，清除戰爭記憶
                if user_profile and user_profile.get('last_war_target'):
                    update_user_profile(user_id, {"last_war_target": None, "last_war_time": None, "war_reply_count": 0})

            # 吵架模式時不套用心情（戰鬥優先）
            mood_tag = "" if (is_bot_war or is_user_war) else f"\n{mood_instruction}"
            full_input = f"【最近對話紀錄】\n{history_context}\n{user_info}使用者輸入: {user_input}{war_instruction}{mood_tag}"

            async with message.channel.typing():
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": my_system_instruction},
                        {"role": "user", "content": full_input}
                    ],
                    temperature=0.85
                )

                raw_response = response.choices[0].message.content
                # 強制在程式端過濾掉括號內心戲（雙重保險）
                raw_response = re.sub(r'\(.*?\)', '', raw_response).strip()
                full_response, data_to_update = parse_openai_response(raw_response)
                if data_to_update:
                    new_data = {}
                    if 'keywords' in data_to_update:
                        old_keywords = set(user_profile.get('keywords', [])) if user_profile else set()
                        new_data['keywords'] = list(old_keywords.union(set(data_to_update['keywords'])))
                    update_user_profile(user_id, new_data)

            await message.channel.send(full_response)
            msg_cooldowns.append(time.time())

            # --- 紀錄邏輯判定 ---
            # 只有機器人吵架會記錄，使用者吵架不記錄
            if is_bot_war or not is_user_war:
                add_to_history(user_id, "user", user_input)
                add_to_history(user_id, "bot", full_response)

        except Exception as e:
            print(f"❌ OpenAI API 錯誤: {e}")
            await message.channel.send("我現在懶得理你。")

        await bot.process_commands(message)
