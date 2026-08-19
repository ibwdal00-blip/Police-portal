import os
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from storage import Storage

# ============================================================
#  إعدادات عامة
# ============================================================
load_dotenv()
TOKEN = os.getenv("MTUwNTY4NTY0MjQ5ODI4MTU5Mg.G3lMfR.Ys9Ur7Pz-FZ3csh1k5UR5bMZuBA1oY7zzJGnTc")
GUILD_ID = os.getenv("1505691946155245590")  # اختياري: لمزامنة سريعة أثناء التجربة
TZ = ZoneInfo("Asia/Riyadh")
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

store = Storage(DATA_FILE)

# تعريف العدادات المستقلة المتوفرة في البوت.
# كل عداد له مفتاح فريد (يُستخدم في custom_id وفي التخزين)
COUNTERS = {
    "سحب": {"emoji": "📊", "name": "عداد السحبات", "color": discord.Color.blurple()},
    "مراقبة": {"emoji": "🛡️", "name": "عداد المراقبة الدورية", "color": discord.Color.teal()},
}

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ============================================================
#  أدوات مساعدة
# ============================================================
def is_allowed(interaction: discord.Interaction) -> bool:
    """التحقق أن المستخدم مدير أو يملك رتبة الدعم المحددة."""
    if interaction.user.guild_permissions.administrator:
        return True
    data = store.get_guild(interaction.guild_id)
    role_id = data.get("support_role_id")
    if not role_id:
        return False
    return any(r.id == role_id for r in interaction.user.roles)


def build_embed(guild_id: int, counter_key: str) -> discord.Embed:
    cfg = COUNTERS[counter_key]
    data = store.get_counter(guild_id, counter_key)
    daily = data.get("daily", 0)
    embed = discord.Embed(
        title=f"{cfg['emoji']} {cfg['name']}",
        description=f"**العدد الحالي:** `{daily}`",
        color=cfg["color"],
    )
    embed.set_footer(text=f"آخر تحديث • {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')}")
    return embed


async def update_panel_message(guild_id: int, counter_key: str):
    data = store.get_counter(guild_id, counter_key)
    channel_id = data.get("panel_channel_id")
    message_id = data.get("panel_message_id")
    if not channel_id or not message_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        return
    try:
        message = await channel.fetch_message(message_id)
        await message.edit(embed=build_embed(guild_id, counter_key), view=CounterView(counter_key))
    except (discord.NotFound, discord.Forbidden):
        pass


async def send_report(guild_id: int, counter_key: str, title: str, count: int, color: discord.Color):
    guild_data = store.get_guild(guild_id)
    counter_data = store.get_counter(guild_id, counter_key)
    channel_id = guild_data.get("report_channel_id") or counter_data.get("panel_channel_id")
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        return
    embed = discord.Embed(
        title=title,
        description=f"**الإجمالي:** `{count}`",
        color=color,
        timestamp=datetime.now(TZ),
    )
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


async def send_log(
    guild_id: int,
    counter_key: str,
    user: discord.abc.User,
    action: str,
    before: int,
    after: int,
    emoji: str,
    color: discord.Color,
):
    """يسجل كل عملية إضافة/حذف/تحديد رقم كسطر تقرير فوري في قناة السجل."""
    guild_data = store.get_guild(guild_id)
    channel_id = guild_data.get("log_channel_id")
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        return
    cfg = COUNTERS[counter_key]
    embed = discord.Embed(
        title=f"{emoji} {action} — {cfg['name']}",
        color=color,
        timestamp=datetime.now(TZ),
    )
    embed.add_field(name="بواسطة", value=user.mention, inline=True)
    embed.add_field(name="قبل", value=f"`{before}`", inline=True)
    embed.add_field(name="بعد", value=f"`{after}`", inline=True)
    embed.set_footer(text=f"ID: {user.id}")
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


async def do_daily_reset(guild_id: int, counter_key: str, now: datetime):
    cfg = COUNTERS[counter_key]
    data = store.get_counter(guild_id, counter_key)

    # التقرير اليومي + تصفير عداد اليوم لهذا العداد
    await send_report(guild_id, counter_key, f"🕚 التقرير اليومي - {cfg['name']}", data.get("daily", 0), discord.Color.green())
    data["daily"] = 0
    store.save()
    await update_panel_message(guild_id, counter_key)

    # إذا كان اليوم الأربعاء، أرسل التقرير الأسبوعي وصفّر عداد الأسبوع أيضًا
    if now.weekday() == 2:  # 0=الاثنين ... 2=الأربعاء
        await send_report(guild_id, counter_key, f"🗓️ التقرير الأسبوعي - {cfg['name']}", data.get("weekly", 0), discord.Color.gold())
        data["weekly"] = 0
        store.save()


# ============================================================
#  الأزرار (View ثابتة تبقى شغالة حتى بعد إعادة تشغيل البوت)
#  نفس الـ View تُستخدم لأي عداد، ويُحدَّد العداد عبر counter_key
# ============================================================
class SetNumberModal(discord.ui.Modal):
    def __init__(self, counter_key: str):
        cfg = COUNTERS[counter_key]
        super().__init__(title=f"تحديد رقم - {cfg['name']}")
        self.counter_key = counter_key
        self.number = discord.ui.TextInput(
            label="اكتب الرقم الجديد",
            placeholder="مثال: 50",
            required=True,
            max_length=10,
        )
        self.add_item(self.number)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = int(self.number.value.strip())
            if value < 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ الرجاء إدخال رقم صحيح موجب.", ephemeral=True)
            return

        guild_id = interaction.guild_id
        data = store.get_counter(guild_id, self.counter_key)
        old = data.get("daily", 0)
        delta = value - old
        data["daily"] = value
        data["weekly"] = max(0, data.get("weekly", 0) + delta)
        store.save()

        await interaction.response.edit_message(embed=build_embed(guild_id, self.counter_key))
        await send_log(guild_id, self.counter_key, interaction.user, "تحديد رقم", old, value, "✏️", discord.Color.blue())


class CounterView(discord.ui.View):
    """View ديناميكية تصلح لأي عداد بناءً على counter_key.
    custom_id لكل زر يتضمن مفتاح العداد حتى تبقى الأزرار ثابتة ومميزة بعد إعادة التشغيل."""

    def __init__(self, counter_key: str):
        super().__init__(timeout=None)
        self.counter_key = counter_key

        add_btn = discord.ui.Button(
            label="إضافة", emoji="➕", style=discord.ButtonStyle.success,
            custom_id=f"panel_{counter_key}_add",
        )
        add_btn.callback = self.add_callback
        self.add_item(add_btn)

        remove_btn = discord.ui.Button(
            label="حذف", emoji="➖", style=discord.ButtonStyle.danger,
            custom_id=f"panel_{counter_key}_remove",
        )
        remove_btn.callback = self.remove_callback
        self.add_item(remove_btn)

        set_btn = discord.ui.Button(
            label="تحديد رقم", emoji="✏️", style=discord.ButtonStyle.secondary,
            custom_id=f"panel_{counter_key}_set",
        )
        set_btn.callback = self.set_callback
        self.add_item(set_btn)

    async def add_callback(self, interaction: discord.Interaction):
        if not is_allowed(interaction):
            await interaction.response.send_message("🔒 ما تملك صلاحية استخدام هذا الزر.", ephemeral=True)
            return
        data = store.get_counter(interaction.guild_id, self.counter_key)
        old = data.get("daily", 0)
        data["daily"] = old + 1
        data["weekly"] = data.get("weekly", 0) + 1
        store.save()
        await interaction.response.edit_message(embed=build_embed(interaction.guild_id, self.counter_key))
        await send_log(interaction.guild_id, self.counter_key, interaction.user, "إضافة", old, old + 1, "➕", discord.Color.green())

    async def remove_callback(self, interaction: discord.Interaction):
        if not is_allowed(interaction):
            await interaction.response.send_message("🔒 ما تملك صلاحية استخدام هذا الزر.", ephemeral=True)
            return
        data = store.get_counter(interaction.guild_id, self.counter_key)
        old = data.get("daily", 0)
        data["daily"] = max(0, old - 1)
        data["weekly"] = max(0, data.get("weekly", 0) - 1)
        store.save()
        await interaction.response.edit_message(embed=build_embed(interaction.guild_id, self.counter_key))
        await send_log(interaction.guild_id, self.counter_key, interaction.user, "حذف", old, data["daily"], "➖", discord.Color.red())

    async def set_callback(self, interaction: discord.Interaction):
        if not is_allowed(interaction):
            await interaction.response.send_message("🔒 ما تملك صلاحية استخدام هذا الزر.", ephemeral=True)
            return
        await interaction.response.send_modal(SetNumberModal(self.counter_key))


# ============================================================
#  الأوامر (Slash Commands)
# ============================================================
@bot.tree.command(name="لوحة", description="إرسال لوحة عداد (سحب أو مراقبة) في هذه القناة")
@app_commands.describe(النوع="اختر نوع اللوحة اللي تبي ترسلها")
@app_commands.choices(النوع=[
    app_commands.Choice(name="عداد السحب", value="سحب"),
    app_commands.Choice(name="عداد المراقبة الدورية", value="مراقبة"),
])
@app_commands.checks.has_permissions(administrator=True)
async def panel_command(interaction: discord.Interaction, النوع: app_commands.Choice[str]):
    counter_key = النوع.value
    embed = build_embed(interaction.guild_id, counter_key)
    await interaction.response.send_message(embed=embed, view=CounterView(counter_key))
    msg = await interaction.original_response()

    data = store.get_counter(interaction.guild_id, counter_key)
    data["panel_channel_id"] = interaction.channel_id
    data["panel_message_id"] = msg.id
    store.save()


@bot.tree.command(name="تحديد_الرتبة", description="تحديد رتبة الدعم المسموح لها استخدام كل أزرار اللوحات")
@app_commands.describe(role="الرتبة المسموح لها استخدام الأزرار")
@app_commands.checks.has_permissions(administrator=True)
async def set_role_command(interaction: discord.Interaction, role: discord.Role):
    data = store.get_guild(interaction.guild_id)
    data["support_role_id"] = role.id
    store.save()
    await interaction.response.send_message(
        f"✅ تم تحديد رتبة {role.mention} كرتبة مسموح لها استخدام الأزرار.", ephemeral=True
    )


@bot.tree.command(name="تحديد_قناة_التقارير", description="تحديد القناة التي ترسل فيها التقارير اليومية/الأسبوعية لكل العدادات")
@app_commands.describe(channel="القناة المخصصة للتقارير")
@app_commands.checks.has_permissions(administrator=True)
async def set_report_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = store.get_guild(interaction.guild_id)
    data["report_channel_id"] = channel.id
    store.save()
    await interaction.response.send_message(f"✅ سيتم إرسال كل التقارير في {channel.mention}.", ephemeral=True)


@bot.tree.command(name="تحديد_قناة_السجل", description="تحديد قناة سجل العمليات (يسجل كل ضغطة زر فورًا: إضافة/حذف/تحديد رقم)")
@app_commands.describe(channel="القناة المخصصة لسجل العمليات")
@app_commands.checks.has_permissions(administrator=True)
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = store.get_guild(interaction.guild_id)
    data["log_channel_id"] = channel.id
    store.save()
    await interaction.response.send_message(f"✅ سيتم تسجيل كل عملية (إضافة/حذف/تحديد رقم) في {channel.mention}.", ephemeral=True)


@panel_command.error
@set_role_command.error
@set_report_channel.error
@set_log_channel.error
async def admin_only_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("🔒 هذا الأمر متاح فقط لمدراء السيرفر.", ephemeral=True)
    else:
        raise error


# ============================================================
#  المهمة الدورية: تقرير اليوم الساعة 11 مساءً لكل عداد + تقرير الأربعاء
# ============================================================
@tasks.loop(seconds=30)
async def reset_loop():
    now = datetime.now(TZ)
    if now.hour == 23 and now.minute == 0:
        today_str = now.strftime("%Y-%m-%d")
        for key in list(store.data.keys()):
            guild_id = int(key)
            guild_data = store.get_guild(guild_id)
            if guild_data.get("last_daily_reset") == today_str:
                continue  # تم التصفير مسبقًا لهذا اليوم (تجنّب التكرار)
            guild_data["last_daily_reset"] = today_str
            store.save()

            # صفّر وأرسل تقرير كل عداد على حدة (سحب + مراقبة)
            for counter_key in COUNTERS:
                await do_daily_reset(guild_id, counter_key, now)


@reset_loop.before_loop
async def before_reset_loop():
    await bot.wait_until_ready()


# ============================================================
#  عند تشغيل البوت
# ============================================================
@bot.event
async def on_ready():
    # تفعيل أزرار كل عداد من جديد حتى بعد إعادة التشغيل
    for counter_key in COUNTERS:
        bot.add_view(CounterView(counter_key))

    try:
        if GUILD_ID:
            guild_obj = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild_obj)
            synced = await bot.tree.sync(guild=guild_obj)
        else:
            synced = await bot.tree.sync()
        print(f"تم مزامنة {len(synced)} أمر.")
    except Exception as e:
        print(f"خطأ أثناء مزامنة الأوامر: {e}")

    if not reset_loop.is_running():
        reset_loop.start()

    print(f"✅ البوت جاهز ويعمل باسم: {bot.user}")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("❌ لم يتم العثور على DISCORD_TOKEN في ملف .env")
    bot.run(TOKEN)
