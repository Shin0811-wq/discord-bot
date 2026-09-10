from datetime import datetime, timedelta
import random
import discord
from discord import app_commands
from discord.ext import commands, tasks

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


# ステップ2：時間を選ぶビュー（13:00〜24:00対応）
class EventTimeSelectView(discord.ui.View):

  def __init__(self, bot, event_name, selected_date_str, channel):
    super().__init__(timeout=180)
    self.bot = bot
    self.event_name = event_name
    self.selected_date_str = selected_date_str
    self.channel = channel

    options = []
    for hour in range(13, 24):
      for minute in [0, 30]:
        time_str = f"{hour:02d}:{minute:02d}"
        options.append(
            discord.SelectOption(
                label=f"{time_str} から開始",
                value=f"{hour}:{minute}",
                description=f"{time_str}〜のイベント",
            )
        )
    options.append(
        discord.SelectOption(
            label="24:00 (深夜0:00) から開始",
            value="24:0",
            description="深夜0:00〜のイベント",
        )
    )

    self.select = discord.ui.Select(
        placeholder="🕒 開始時間を選んでください（13時〜・30分刻み）",
        min_values=1,
        max_values=1,
        options=options,
    )
    self.select.callback = self.time_select_callback
    self.add_item(self.select)

  async def time_select_callback(self, interaction: discord.Interaction):
    time_val = self.select.values[0]
    hour_str, minute_str = time_val.split(":")
    hour = int(hour_str)
    minute = int(minute_str)

    target_date = datetime.strptime(self.selected_date_str, "%Y-%m-%d")
    now_local = datetime.now().astimezone()

    if hour == 24:
      target_date += timedelta(days=1)
      hour = 0

    start_time = target_date.replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ).astimezone(now_local.tzinfo)
    end_time = start_time + timedelta(hours=2)

    guild = interaction.guild

    try:
      event = await guild.create_scheduled_event(
          name=self.event_name,
          description=(
              f"主催: {interaction.user.display_name}"
              " によって作成されたイベントです。"
          ),
          start_time=start_time,
          end_time=end_time,
          entity_type=discord.EntityType.external,
          location="ボイスチャンネル / 指定場所",
          privacy_level=discord.PrivacyLevel.guild_only,
      )

      cog = self.bot.get_cog("DiscordEventCog")
      if cog:
        cog.register_event_task(event.id, guild.id, self.channel.id)

      wd_str = WEEKDAYS[start_time.weekday()]
      await interaction.response.edit_message(
          content=(
              f"✅ **{self.event_name}** の公式イベントを作成しました！\n"
              f"📅 開催日時: **{start_time.strftime('%m月%d日')} ({wd_str})"
              f" {start_time.strftime('%H:%M')}〜**\n"
              "🔔 開始10分前にチャンネル＆参加者へのDMでリマインダーが飛び、"
              "時間になると自動でペア分けが投稿されます！"
          ),
          view=None,
      )
    except Exception as e:
      await interaction.response.edit_message(
          content=f"イベントの作成に失敗しました: {e}", view=None
      )


# ステップ1：日付を選ぶビュー
class EventDateSelectView(discord.ui.View):

  def __init__(self, bot, event_name, channel):
    super().__init__(timeout=180)
    self.bot = bot
    self.event_name = event_name
    self.channel = channel

    options = []
    now = datetime.now().astimezone()

    for i in range(1, 8):
      target_day = now + timedelta(days=i)
      wd_str = WEEKDAYS[target_day.weekday()]
      label = f"{target_day.month}月{target_day.day}日 ({wd_str})"
      value = target_day.strftime("%Y-%m-%d")
      options.append(discord.SelectOption(label=label, value=value))

    self.select = discord.ui.Select(
        placeholder="📅 開催する日付（7日間）を選んでください",
        min_values=1,
        max_values=1,
        options=options,
    )
    self.select.callback = self.date_select_callback
    self.add_item(self.select)

  async def date_select_callback(self, interaction: discord.Interaction):
    selected_date_str = self.select.values[0]
    target_date = datetime.strptime(selected_date_str, "%Y-%m-%d")
    wd_str = WEEKDAYS[target_date.weekday()]

    next_view = EventTimeSelectView(
        self.bot, self.event_name, selected_date_str, self.channel
    )
    await interaction.response.edit_message(
        content=(
            f"📅 選択日: **{target_date.month}月{target_date.day}日"
            f" ({wd_str})**\n続いて、下のメニューから**開始時間（30分刻み）**を選んでください👇"
        ),
        view=next_view,
    )


class DiscordEventCog(commands.Cog):

  def __init__(self, bot):
    self.bot = bot
    self.active_events = {}
    self.check_events_task.start()

  def cog_unload(self):
    self.check_events_task.cancel()

  def register_event_task(self, event_id, guild_id, channel_id):
    self.active_events[event_id] = {
        "guild_id": guild_id,
        "channel_id": channel_id,
        "reminder_sent": False,
    }

  @tasks.loop(minutes=1.0)
  async def check_events_task(self):
    now = datetime.now().astimezone()

    for event_id, info in list(self.active_events.items()):
      guild = self.bot.get_guild(info["guild_id"])
      if not guild:
        continue

      try:
        event = await guild.fetch_scheduled_event(event_id)
      except discord.NotFound:
        del self.active_events[event_id]
        continue
      except Exception:
        continue

      channel = guild.get_channel(info["channel_id"])
      time_until_start = event.start_time - now

      # --- ① 開始10分前のリマインダー処理（チャンネル ＆ DM） ---
      if (
          not info["reminder_sent"]
          and timedelta(minutes=0) < time_until_start <= timedelta(minutes=10)
      ):
        participants = []
        async for user in event.users():
          member = guild.get_member(user.id)
          if member and not member.bot:
            participants.append(member)

        if participants:
          mentions = " ".join([p.mention for p in participants])

          # 1. チャンネルへ通知
          if channel:
            await channel.send(
                f"🔔 **【リマインダー】**\n"
                f"**{event.name}** の開始10分前になりました！\n"
                f"参加予定の皆さん、準備をお願いします！ 👉 {mentions}"
            )

          # 2. 参加者全員にDM（ダイレクトメッセージ）を送信してスマホに通知を飛ばす
          start_time_str = event.start_time.strftime("%H:%M")
          for member in participants:
            try:
              await member.send(
                  f"🔔 **【リマインダー通知】**\n"
                  f"あなたが参加予定のイベント **「{event.name}」**"
                  f" が【10分後（{start_time_str}〜）】に開始します！\n"
                  "準備をお願いします！"
              )
            except discord.Forbidden:
              # ユーザーがボットからのDMを拒否している場合はエラーで止まらないようにスルー
              pass
        else:
          if channel:
            await channel.send(
                f"🔔 **【リマインダー】**\n"
                f"**{event.name}** の開始10分前ですが、"
                "現在参加表明している人がいません！"
            )

        info["reminder_sent"] = True

      # --- ② 開始時間のペア分け処理 ---
      if now >= event.start_time:
        if channel:
          participants = []
          async for user in event.users():
            member = guild.get_member(user.id)
            if member and not member.bot:
              participants.append(member)

          if len(participants) >= 2:
            random.shuffle(participants)
            pairs = []
            leftover = None

            for i in range(0, len(participants), 2):
              if i + 1 < len(participants):
                pairs.append((participants[i], participants[i + 1]))
              else:
                leftover = participants[i]

            result_text = f"⏰ **【{event.name}】が開始時間になりました！**\n参加予定のメンバーでペアを決定しました🎉\n\n"
            for idx, pair in enumerate(pairs, 1):
              result_text += (
                  f"**グループ {idx}**: {pair[0].mention} &"
                  f" {pair[1].mention}\n"
              )
            if leftover:
              result_text += f"\n👤 **余った人**: {leftover.mention}"

            await channel.send(result_text)
          else:
            await channel.send(
                f"⏰ **【{event.name}】** の時間になりましたが、参加者が2人未満のためペア分けをスキップしました。"
            )

        del self.active_events[event_id]

  @check_events_task.before_loop
  async def before_check_events(self):
    await self.bot.wait_until_ready()

  @app_commands.command(
      name="create_game_event",
      description=(
          "【固定】みんなでゲーム会のイベント作成＆自動リマインダー設定"
      ),
  )
  async def create_game_event(self, interaction: discord.Interaction):
    event_name = "🎮 みんなでゲーム会"

    view = EventDateSelectView(self.bot, event_name, interaction.channel)
    await interaction.response.send_message(
        f"**{event_name}** のスケジュール調整を行います。\n下のメニューから開催したい日付を選んでください👇",
        view=view,
        ephemeral=True,
    )

  # テスト用コマンド（必要に応じて使用）
  @app_commands.command(
      name="test_event",
      description=(
          "【テスト用】今から約11分後に始まるテスト用イベントを即座に作成します"
      ),
  )
  async def test_event(self, interaction: discord.Interaction):
    guild = interaction.guild
    now = datetime.now().astimezone()

    start_time = now + timedelta(minutes=11)
    end_time = start_time + timedelta(hours=1)
    event_name = "🧪 【テスト】ゲーム会"

    try:
      event = await guild.create_scheduled_event(
          name=event_name,
          description="動作テスト用のイベントです。",
          start_time=start_time,
          end_time=end_time,
          entity_type=discord.EntityType.external,
          location="ボイスチャンネル",
          privacy_level=discord.PrivacyLevel.guild_only,
      )

      self.register_event_task(event.id, guild.id, interaction.channel.id)

      await interaction.response.send_message(
          f"🧪 テスト用イベントを作成しました！\n"
          f"開始時間: **{start_time.strftime('%H:%M:%S')}**\n"
          "（約1分以内に「10分前リマインダー」がチャンネル＆DMに飛び、"
          "その約11分後に「ペア分け」がこのチャンネルに投稿されます）",
          ephemeral=True,
      )
    except Exception as e:
      await interaction.response.send_message(
          f"テストイベントの作成に失敗しました: {e}", ephemeral=True
      )


async def setup(bot):
  await bot.add_cog(DiscordEventCog(bot))