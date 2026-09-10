import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


# ボットのクラスを拡張して、起動時に自動でcogを読み込ませる
class MyBot(commands.Bot):

  async def setup_hook(self):
    await self.load_extension("cogs.schedule")
    # 【追加】ペア分け機能のCogを読み込む
    await self.load_extension("cogs.pair")
    print("すべてのCogを読み込みました。")


bot = MyBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
  print(f"ログイン完了: {bot.user}")
  try:
    synced = await bot.tree.sync()
    print(f"{len(synced)}個のスラッシュコマンドを同期しました。")
  except Exception as e:
    print(e)


# 通常通り bot.run で起動する
bot.run("MTU0NjUyODA0MjEzNzAyNjYwMA.GYPaAA.-uUcY3lnuDi3xmrfTto4KQqXvDmhuugQd8fnRQ")