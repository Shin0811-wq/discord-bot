import random
import discord
from discord import app_commands
from discord.ext import commands


# ペア選択用のUIビュー
class PairSelectView(discord.ui.View):

  def __init__(self, members):
    super().__init__(timeout=180)

    options = []
    for member in members[:25]:
      options.append(
          discord.SelectOption(
              label=member.display_name, value=str(member.id)
          )
      )

    self.select = discord.ui.Select(
        placeholder="ペアを作りたいメンバーを選んでください（複数選択可）",
        min_values=1,
        max_values=len(options),
        options=options,
    )
    self.select.callback = self.select_callback
    self.add_item(self.select)

  async def select_callback(self, interaction: discord.Interaction):
    selected_members = []
    for member_id in self.select.values:
      member = interaction.guild.get_member(int(member_id))
      if member:
        selected_members.append(member)

    random.shuffle(selected_members)

    pairs = []
    leftover = None

    for i in range(0, len(selected_members), 2):
      if i + 1 < len(selected_members):
        pairs.append((selected_members[i], selected_members[i + 1]))
      else:
        leftover = selected_members[i]

    result_text = "🎲 **ランダムペア発表！**\n\n"
    for idx, pair in enumerate(pairs, 1):
      result_text += (
          f"**グループ {idx}**: {pair[0].mention} & {pair[1].mention}\n"
      )

    if leftover:
      result_text += f"\n👤 **余った人**: {leftover.mention}"

    await interaction.response.send_message(result_text)


# ペア分け機能をまとめたCogクラス
class PairCog(commands.Cog):

  def __init__(self, bot):
    self.bot = bot

  @app_commands.command(
      name="make_pairs", description="メンバーを選んでランダムに2人組を作ります"
  )
  async def make_pairs(self, interaction: discord.Interaction):
    # テスト用に全員を対象にする場合は list(interaction.guild.members) に、
    # 本番でBotを除外したい場合は [m for m in interaction.guild.members if not m.bot] に変更してください
    members = list(interaction.guild.members)

    if not members:
      await interaction.response.send_message(
          "メンバーが見つかりませんでした。", ephemeral=True
      )
      return

    view = PairSelectView(members)
    await interaction.response.send_message(
        "下のメニューからペアを作りたいメンバーを選択してください👇",
        view=view,
        ephemeral=True,
    )


async def setup(bot):
  await bot.add_cog(PairCog(bot))