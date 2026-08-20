import os
import sqlite3
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
REPORT_CHANNEL_ID = int(os.getenv("REPORT_CHANNEL_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Riyadh")

TZ = ZoneInfo(TIMEZONE)
DB_FILE = "stats.db"

CATEGORIES = {
    "reports": "الريبورت",
    "pulls": "السحبات",
    "patrol": "المراقبة الدورية",
}


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            category TEXT PRIMARY KEY,
            daily INTEGER NOT NULL DEFAULT 0,
            weekly INTEGER NOT NULL DEFAULT 0
        )
    """)
    for key in CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO counters(category, daily, weekly) VALUES (?, 0, 0)",
            (key,),
        )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def add_count(category: str, amount: int):
    if category not in CATEGORIES:
        raise ValueError("Unknown category")
    conn = db()
    conn.execute(
        "UPDATE counters SET daily = daily + ?, weekly = weekly + ? WHERE category = ?",
        (amount, amount, category),
    )
    conn.commit()
    conn.close()


def get_counts():
    conn = db()
    rows = conn.execute("SELECT * FROM counters").fetchall()
    conn.close()
    return {row["category"]: {"daily": row["daily"], "weekly": row["weekly"]} for row in rows}


def reset_daily():
    conn = db()
    conn.execute("UPDATE counters SET daily = 0")
    conn.commit()
    conn.close()


def reset_weekly():
    conn = db()
    conn.execute("UPDATE counters SET weekly = 0, daily = 0")
    conn.commit()
    conn.close()


def report_text(title: str, field: str):
    counts = get_counts()
    lines = [
        f"**{title}**",
        "",
        f"📋 **الريبورت:** `{counts['reports'][field]}`",
        f"🎟️ **السحبات:** `{counts['pulls'][field]}`",
        f"👮 **المراقبة الدورية:** `{counts['patrol'][field]}`",
    ]
    total = sum(counts[k][field] for k in CATEGORIES)
    lines += ["", f"📊 **الإجمالي:** `{total}`"]
    return "\n".join(lines)


class AddNumberModal(discord.ui.Modal, title="إضافة رقم"):
    amount = discord.ui.TextInput(
        label="العدد",
        placeholder="مثال: 5",
        min_length=1,
        max_length=6,
        required=True,
    )

    category = discord.ui.TextInput(
        label="القائمة",
        placeholder="اكتب: ريبورت أو سحبات أو مراقبة",
        required=True,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.category.value.strip().lower()
        mapping = {
            "ريبورت": "reports",
            "الريبورت": "reports",
            "report": "reports",
            "reports": "reports",
            "سحبات": "pulls",
            "السحبات": "pulls",
            "سحبة": "pulls",
            "pulls": "pulls",
            "مراقبة": "patrol",
            "المراقبة": "patrol",
            "المراقبة الدورية": "patrol",
            "دورية": "patrol",
            "patrol": "patrol",
        }

        if raw not in mapping:
            await interaction.response.send_message(
                "❌ القائمة غير صحيحة. اختر: **ريبورت / سحبات / مراقبة**.",
                ephemeral=True,
            )
            return

        try:
            amount = int(self.amount.value)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ اكتب رقمًا صحيحًا أكبر من صفر.",
                ephemeral=True,
            )
            return

        key = mapping[raw]
        add_count(key, amount)

        await interaction.response.send_message(
            f"✅ تمت إضافة **{amount}** إلى **{CATEGORIES[key]}**.",
            ephemeral=True,
        )


class StatsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="حسب الريبورت",
        emoji="📋",
        style=discord.ButtonStyle.primary,
        custom_id="stats:reports",
    )
    async def reports(self, interaction: discord.Interaction, button: discord.ui.Button):
        add_count("reports", 1)
        counts = get_counts()
        await interaction.response.send_message(
            f"✅ تمت إضافة **1** للريبورت.\nالعدد اليومي: `{counts['reports']['daily']}`",
            ephemeral=True,
        )

    @discord.ui.button(
        label="حسب السحبات",
        emoji="🎟️",
        style=discord.ButtonStyle.success,
        custom_id="stats:pulls",
    )
    async def pulls(self, interaction: discord.Interaction, button: discord.ui.Button):
        add_count("pulls", 1)
        counts = get_counts()
        await interaction.response.send_message(
            f"✅ تمت إضافة **1** للسحبات.\nالعدد اليومي: `{counts['pulls']['daily']}`",
            ephemeral=True,
        )

    @discord.ui.button(
        label="حسب المراقبة الدورية",
        emoji="👮",
        style=discord.ButtonStyle.secondary,
        custom_id="stats:patrol",
    )
    async def patrol(self, interaction: discord.Interaction, button: discord.ui.Button):
        add_count("patrol", 1)
        counts = get_counts()
        await interaction.response.send_message(
            f"✅ تمت إضافة **1** للمراقبة الدورية.\nالعدد اليومي: `{counts['patrol']['daily']}`",
            ephemeral=True,
        )

    @discord.ui.button(
        label="إضافة رقم",
        emoji="➕",
        style=discord.ButtonStyle.danger,
        custom_id="stats:add_number",
    )
    async def add_number(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddNumberModal())


class StatsBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        init_db()
        self.add_view(StatsView())
        await self.tree.sync()
        daily_reports.start()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")


bot = StatsBot()


@bot.tree.command(name="setup", description="إرسال لوحة الإحصائيات في القناة الحالية")
async def setup(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📊 لوحة الإحصائيات",
        description=(
            "اضغط على الزر المناسب لإضافة **1** مباشرة.\n"
            "أما **إضافة رقم** فتسمح لك بإضافة عدد تختاره للقائمة التي تحددها."
        ),
    )
    embed.add_field(name="📋 الريبورت", value="زر واحد = +1", inline=True)
    embed.add_field(name="🎟️ السحبات", value="زر واحد = +1", inline=True)
    embed.add_field(name="👮 المراقبة الدورية", value="زر واحد = +1", inline=True)
    embed.add_field(name="➕ إضافة رقم", value="حدد القائمة والعدد", inline=False)
    await interaction.channel.send(embed=embed, view=StatsView())
    await interaction.response.send_message("✅ تم إرسال اللوحة.", ephemeral=True)


async def send_daily_report():
    if not REPORT_CHANNEL_ID:
        print("REPORT_CHANNEL_ID غير مضبوط.")
        return

    channel = bot.get_channel(REPORT_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(REPORT_CHANNEL_ID)
        except Exception as e:
            print("تعذر الوصول لقناة التقرير:", e)
            return

    await channel.send(report_text("📅 التقرير اليومي", "daily"))


async def send_weekly_report():
    if not REPORT_CHANNEL_ID:
        print("REPORT_CHANNEL_ID غير مضبوط.")
        return

    channel = bot.get_channel(REPORT_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(REPORT_CHANNEL_ID)
        except Exception as e:
            print("تعذر الوصول لقناة التقرير:", e)
            return

    await channel.send(report_text("📆 التقرير الأسبوعي", "weekly"))


last_daily_date = None
last_weekly_date = None


@tasks.loop(seconds=30)
async def daily_reports():
    global last_daily_date, last_weekly_date

    now = datetime.now(TZ)
    today = now.date()

    # الأربعاء الساعة 11:00: أرسل الأسبوعي أولًا، ثم اليومي.
    if now.hour == 23 and now.minute == 0:
        if now.weekday() == 2 and last_weekly_date != today:
            await send_weekly_report()
            reset_weekly()
            last_weekly_date = today

        if last_daily_date != today:
            await send_daily_report()
            reset_daily()
            last_daily_date = today


@daily_reports.before_loop
async def before_daily_reports():
    await bot.wait_until_ready()


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("ضع DISCORD_TOKEN داخل ملف .env")
    bot.run(TOKEN)
