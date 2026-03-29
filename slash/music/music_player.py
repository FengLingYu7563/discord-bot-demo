import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import wavelink
from collections import deque
import random
import os

# === Wavelink channelId Patch（修正 Lavalink v4 必填欄位）===

async def _patched_dispatch_voice_update(self) -> None:
    assert self.guild is not None
    data = self._voice_state["voice"]

    session_id = data.get("session_id")
    token = data.get("token")
    endpoint = data.get("endpoint")

    if not session_id or not token or not endpoint:
        return

    channel_id = str(self.channel.id) if self.channel else None
    if not channel_id:
        return

    request = {
        "voice": {
            "sessionId": session_id,
            "token": token,
            "endpoint": endpoint,
            "channelId": channel_id
        }
    }

    try:
        await self.node._update_player(self.guild.id, data=request)
    except Exception:
        await self.disconnect()
    else:
        self._connection_event.set()

wavelink.Player._dispatch_voice_update = _patched_dispatch_voice_update
# ============================================================


class MusicQueue:
    def __init__(self):
        self.history: deque = deque(maxlen=100)
        self.current: wavelink.Playable | None = None
        self.loop: bool = False
        self.text_channel: discord.TextChannel | None = None

class PriorityPlayModal(discord.ui.Modal, title="插播歌曲"):
    query = discord.ui.TextInput(
        label="歌曲名稱或網址",
        placeholder="輸入後將排在播放清單最前面...",
        required=True
    )

    def __init__(self, music_cog):
        super().__init__()
        self.music_cog = music_cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.music_cog.process_play(interaction, self.query.value, priority=True)

class PaginationView(discord.ui.View):
    def __init__(self, data_list, title, color, music_cog):
        super().__init__(timeout=60)
        self.data_list = list(data_list)
        self.title = title
        self.color = color
        self.music_cog = music_cog
        self.current_page = 0
        self.items_per_page = 10

    def create_embed(self):
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        items = self.data_list[start:end]
        embed = discord.Embed(title=self.title, color=self.color)

        description = ""
        if not items:
            description = "目前清單為空。\n"
        else:
            for i, item in enumerate(items, start=start + 1):
                if isinstance(item, wavelink.Playable):
                    description += f"`{i}.` [{item.title}]({item.uri})\n"
                else:
                    description += f"`{i}.` {item}\n"

        embed.description = description
        max_page = max(0, (len(self.data_list) - 1) // self.items_per_page)
        embed.set_footer(text=f"第 {self.current_page + 1} / {max_page + 1} 頁（共 {len(self.data_list)} 首）")
        return embed

    @discord.ui.button(label="上一頁", style=discord.ButtonStyle.gray)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="插播", style=discord.ButtonStyle.primary)
    async def priority_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PriorityPlayModal(self.music_cog))

    @discord.ui.button(label="下一頁", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.current_page + 1) * self.items_per_page < len(self.data_list):
            self.current_page += 1
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        else:
            await interaction.response.defer()

class MusicControlView(discord.ui.View):
    def __init__(self, music_cog, guild: discord.Guild):
        super().__init__(timeout=None)
        self.music_cog = music_cog
        self.guild = guild
        self.update_buttons()

    def update_buttons(self):
        vc: wavelink.Player | None = self.guild.voice_client
        q = self.music_cog.get_queue(self.guild.id)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "單首循環":
                    child.style = discord.ButtonStyle.success if q.loop else discord.ButtonStyle.secondary
                if child.label == "自動推播":
                    is_auto = (vc.autoplay == wavelink.AutoPlayMode.enabled) if vc else False
                    child.style = discord.ButtonStyle.success if is_auto else discord.ButtonStyle.secondary

    @discord.ui.button(label="暫停/繼續", emoji="⏯️", style=discord.ButtonStyle.primary, row=0)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: wavelink.Player = self.guild.voice_client
        if vc:
            await vc.pause(not vc.paused)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="下一首", emoji="⏭️", style=discord.ButtonStyle.primary, row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: wavelink.Player = self.guild.voice_client
        if vc:
            await vc.skip()
        await interaction.response.defer()

    @discord.ui.button(label="打亂", emoji="🔀", style=discord.ButtonStyle.primary, row=0)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: wavelink.Player = self.guild.voice_client
        if vc and vc.queue:
            vc.queue.shuffle()
            await interaction.response.send_message("🔀 已打亂清單", ephemeral=True)
        else:
            await interaction.response.send_message("清單是空的", ephemeral=True)

    @discord.ui.button(label="單首循環", emoji="🔂", style=discord.ButtonStyle.secondary, row=1)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = self.music_cog.get_queue(self.guild.id)
        q.loop = not q.loop
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="自動推播", emoji="🎵", style=discord.ButtonStyle.secondary, row=1)
    async def auto_recommend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: wavelink.Player = self.guild.voice_client
        if vc:
            if vc.autoplay == wavelink.AutoPlayMode.enabled:
                vc.autoplay = wavelink.AutoPlayMode.partial
            else:
                vc.autoplay = wavelink.AutoPlayMode.enabled
        self.update_buttons()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="播放清單", style=discord.ButtonStyle.gray, row=2)
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: wavelink.Player = self.guild.voice_client
        if not vc:
            return await interaction.response.send_message("目前沒有播放器", ephemeral=True)
        view = PaginationView(list(vc.queue), "🎵 播放清單", discord.Color.blue(), self.music_cog)
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="歷史歌單", style=discord.ButtonStyle.gray, row=2)
    async def history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = self.music_cog.get_queue(self.guild.id)
        view = PaginationView(list(q.history), "📜 歷史歌單", discord.Color.dark_gray(), self.music_cog)
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="刷新面板", style=discord.ButtonStyle.gray, row=2)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: wavelink.Player = self.guild.voice_client
        q = self.music_cog.get_queue(self.guild.id)
        if not vc or not q.current:
            return await interaction.response.send_message("目前沒有播放中的音樂", ephemeral=True)
        embed = self.music_cog.build_now_playing_embed(vc, q.current)
        view = MusicControlView(self.music_cog, self.guild)
        await interaction.response.send_message(embed=embed, view=view)

    @discord.ui.button(label="中斷連接", emoji="⏹️", style=discord.ButtonStyle.danger, row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc: wavelink.Player = self.guild.voice_client
        if vc:
            vc.queue.clear()
            await vc.disconnect()
            await interaction.response.send_message("⏹️ 已中斷連線", ephemeral=True)

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: dict[int, MusicQueue] = {}

    async def connect_nodes(self):
        try:
            await self.bot.wait_until_ready()
            await asyncio.sleep(2)
            if not wavelink.Pool.nodes:
                node = wavelink.Node(
                uri=os.getenv("LAVALINK_URI", "https://lavalinkv4.serenetia.com"),
                password=os.getenv("LAVALINK_PASSWORD", "https://seretia.link/discord"),
                )
                await wavelink.Pool.connect(nodes=[node], client=self.bot)
                print("⏳ [Lavalink] 正在連線，等待節點就緒...")
        except Exception as e:
            print(f"❌ [Lavalink] 連線失敗: {e}")

    def get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]

    # --- 事件監聽 ---
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f"[Lavalink] 節點已就緒: {payload.node.identifier}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = payload.player
        if not player.guild:
            return
        q = self.get_queue(player.guild.id)
        q.current = payload.track
        # 換歌時不主動發通知，讓使用者按「刷新面板」自行查看

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if not player.guild:
            return
        q = self.get_queue(player.guild.id)

        # 記錄歷史
        if q.current:
            q.history.appendleft(q.current)

        # 單首循環
        if q.loop and q.current:
            await player.play(q.current)
        # 下一首
        elif player.queue:
            next_track = player.queue.get()
            q.current = next_track
            await player.play(next_track)
  
    def build_now_playing_embed(self, vc: wavelink.Player, track: wavelink.Playable) -> discord.Embed:
        """建立含進度條的正在播放 embed"""
        position_ms = vc.position if vc else 0
        duration_ms = track.length if track.length else 0

        def fmt(ms):
            s = int(ms / 1000)
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        progress = f"`{fmt(position_ms)} / {fmt(duration_ms)}`" if duration_ms else ""

        embed = discord.Embed(
            title="🎵 正在播放",
            description=f"[{track.title}]({track.uri})\n⏱️ 進度：{progress}",
            color=discord.Color.green()
        )
        if hasattr(track, 'artwork') and track.artwork:
            embed.set_thumbnail(url=track.artwork)
        return embed

    # --- 核心播放邏輯（一般點歌 + 插播共用）---
    async def process_play(self, interaction: discord.Interaction, query: str, priority: bool = False):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        if not interaction.user.voice:
            return await interaction.edit_original_response(content="請先進入語音頻道！")

        channel = interaction.user.voice.channel
        vc: wavelink.Player = interaction.guild.voice_client
        is_first_song = not vc or not vc.playing

        if not vc:
            vc = await channel.connect(cls=wavelink.Player)
            vc.autoplay = wavelink.AutoPlayMode.partial
        elif vc.channel.id != channel.id:
            await vc.move_to(channel)

        q = self.get_queue(interaction.guild.id)
        q.text_channel = interaction.channel

        # 搜尋歌曲
        if not query.startswith("http"):
            tracks = await wavelink.Playable.search(f"ytmsearch:{query}")
        else:
            tracks = await wavelink.Playable.search(query)
            
        if not tracks:
            return await interaction.edit_original_response(content="找不到歌曲")

        if isinstance(tracks, wavelink.Playlist):
            track = tracks.tracks[0]
            await vc.queue.put_wait(track)
            await interaction.edit_original_response(content=f"已加入隊列：**{track.title}**")
        else:
            track = tracks[0]
            if priority:
                try:
                    vc.queue.put_at(0, track)
                except Exception:
                    old_queue = list(vc.queue)
                    vc.queue.clear()
                    await vc.queue.put_wait(track)
                    for t in old_queue:
                        await vc.queue.put_wait(t)
                await interaction.edit_original_response(content=f"已插播：**{track.title}**")
            else:
                await vc.queue.put_wait(track)
                # ephemeral=True，只有自己看得到
                await interaction.edit_original_response(content=f"已加入隊列：**{track.title}**")

        # 第一首歌：開始播放並發出面板
        if is_first_song and not vc.playing:
            next_track = vc.queue.get()
            await vc.play(next_track)
            await asyncio.sleep(0.5)
            q.current = next_track
            embed = self.build_now_playing_embed(vc, next_track)
            view = MusicControlView(self, interaction.guild)
            if q.text_channel:
                await q.text_channel.send(embed=embed, view=view)

    # --- 斜線指令 ---
    @app_commands.command(name="join", description="讓機器人加入你所在的語音頻道")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("請先進入語音頻道！", ephemeral=True)
        channel = interaction.user.voice.channel
        vc: wavelink.Player = interaction.guild.voice_client
        if vc:
            if vc.channel.id == channel.id:
                return await interaction.response.send_message("我已經在這個頻道了！", ephemeral=True)
            await vc.move_to(channel)
            await interaction.response.send_message(f"已移動至 **{channel.name}**", ephemeral=True)
        else:
            await channel.connect(cls=wavelink.Player)
            await interaction.response.send_message(f"已加入 **{channel.name}**", ephemeral=True)
                
    @app_commands.command(name="play", description="點歌（連結或歌名）")
    async def play(self, interaction: discord.Interaction, query: str):
        await self.process_play(interaction, query)

    @app_commands.command(name="playl", description="YouTube 播放清單")
    async def play_playlist(self, interaction: discord.Interaction, url: str):
        if not url.startswith("http"):
            return await interaction.response.send_message("請提供正確的 YouTube 播放清單網址！", ephemeral=True)
        await self.process_play(interaction, url)
    
    @app_commands.command(name="search", description="搜尋，可以選擇要哪一版")
    async def search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        
        tracks = await wavelink.Playable.search(f"ytsearch:{query}")
        if not tracks:
            return await interaction.edit_original_response(content="找不到歌曲")
        
        results = tracks[:20]
        
        description = ""
        for i, track in enumerate(results, 1):
            duration = f"{track.length // 60000}:{(track.length // 1000) % 60:02d}"
            description += f"`{i}.` [{track.title}]({track.uri}) `{duration}`\n"
        
        embed = discord.Embed(title=f"搜尋結果：{query}", description=description, color=discord.Color.blue())
        
        # 用 Select 下拉選單讓使用者選
        options = [
            discord.SelectOption(label=t.title[:100], value=str(i))
            for i, t in enumerate(results)
        ]
        
        select = discord.ui.Select(placeholder="選擇要播放的版本...", options=options)
        
        async def select_callback(select_interaction: discord.Interaction):
            idx = int(select.values[0])
            track = results[idx]
            vc: wavelink.Player = select_interaction.guild.voice_client
            if not select_interaction.user.voice:
                return await select_interaction.response.send_message("請先進入語音頻道！", ephemeral=True)
            if not vc:
                vc = await select_interaction.user.voice.channel.connect(cls=wavelink.Player)
                vc.autoplay = wavelink.AutoPlayMode.partial
            await vc.queue.put_wait(track)
            await select_interaction.response.send_message(f"已加入隊列：**{track.title}**", ephemeral=True)
            if not vc.playing:
                next_track = vc.queue.get()
                q = self.get_queue(select_interaction.guild.id)
                q.text_channel = select_interaction.channel
                await vc.play(next_track)
                await asyncio.sleep(0.5)
                q.current = next_track
                embed = self.build_now_playing_embed(vc, next_track)
                view = MusicControlView(self, select_interaction.guild)
                await q.text_channel.send(embed=embed, view=view)
        
        select.callback = select_callback
        view = discord.ui.View(timeout=30)
        view.add_item(select)
        
        await interaction.edit_original_response(embed=embed, view=view)


async def setup(bot: commands.Bot):
    cog = Music(bot)
    await bot.add_cog(cog)
    asyncio.create_task(cog.connect_nodes())