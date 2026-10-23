import os
import logging
import sqlite3
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DB_PATH", "fitness_bot.db")
DEFAULT_TZ = os.getenv("BOT_TIMEZONE", "Europe/Madrid")
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🏋️ تمرین امروز"), KeyboardButton("📅 برنامه هفتگی")],
        [KeyboardButton("🥗 راهنمای تغذیه"), KeyboardButton("⚖️ ثبت وزن")],
        [KeyboardButton("📏 ثبت دور شکم"), KeyboardButton("📊 گزارش پیشرفت")],
        [KeyboardButton("⏰ تنظیم یادآوری"), KeyboardButton("⚙️ راهنما")],
    ],
    resize_keyboard=True,
)

WEEK = {
    0: ("شنبه", "قدرتی کل بدن + شکم", "۴۰ تا ۴۵ دقیقه",
        ["اسکوات وزن بدن: 3 ست × 12–15 تکرار",
         "شنا: 3 ست × 8–15 تکرار (در صورت نیاز روی سطح بلند)",
         "لانج معکوس: 3 ست × 10 تکرار هر پا",
         "پل باسن: 3 ست × 15 تکرار",
         "پلانک: 3 ست × 30–45 ثانیه",
         "ددباگ: 3 ست × 10 تکرار هر سمت"]),
    1: ("یکشنبه", "هوازی تناوبی در پارک", "۳۰ تا ۳۵ دقیقه",
        ["۵–۸ دقیقه گرم‌کردن با راه‌رفتن تند و نرم‌دویدن",
         "۶ تا ۸ دور: ۱ دقیقه دویدن تندِ کنترل‌شده + ۲ دقیقه آرام",
         "۵ دقیقه سردکردن و راه‌رفتن آرام"]),
    2: ("دوشنبه", "قدرتی و عضلات مرکزی", "۳۵ تا ۴۰ دقیقه",
        ["اسپلیت اسکوات: 3 ست × 10 تکرار هر پا",
         "پایک پوش‌آپ یا پرس سرشانه با کش: 3 ست × 8–12",
         "هیپ‌هینج/ددلیفت تک‌پا بدون وزنه: 3 ست × 10 هر پا",
         "سوپرمن کنترل‌شده: 3 ست × 10",
         "ساید پلانک: 3 ست × 20–40 ثانیه هر سمت",
         "برد داگ: 3 ست × 10 هر سمت"]),
    3: ("سه‌شنبه", "هوازی با شدت متوسط", "۳۵ تا ۴۵ دقیقه",
        ["پیاده‌روی تند، دوچرخه یا دویدن آرام با شدت قابل‌گفت‌وگو",
         "شدت را طوری نگه دار که بتوانی جمله کامل بگویی",
         "در پایان ۵ دقیقه آرام‌کردن"]),
    4: ("چهارشنبه", "تمرین دایره‌ای کل بدن", "۳۰ تا ۳۵ دقیقه",
        ["۳ تا ۴ دور، با ۶۰–۹۰ ثانیه استراحت بین دورها:",
         "اسکوات: 12 تکرار",
         "شنا: 8–12 تکرار",
         "استپ‌بک لانج: 10 تکرار هر پا",
         "مانتین کلایمبر کنترل‌شده: 30 ثانیه (یا مارچ درجا)",
         "پلانک: 30 ثانیه"]),
    5: ("پنجشنبه", "قدرتی + شکم", "۳۵ تا ۴۰ دقیقه",
        ["اسکوات مکث‌دار: 3 ست × 10–12",
         "شنا با تنوع مناسب سطح: 3 ست × 8–15",
         "لانج جانبی: 3 ست × 8–10 هر سمت",
         "بالا آوردن زانو در حالت خوابیده: 3 ست × 10–12",
         "پلانک ساید: 3 ست × 20–40 ثانیه هر سمت",
         "راه‌رفتن تند: 10 دقیقه"]),
    6: ("جمعه", "ریکاوری فعال", "۲۰ تا ۳۰ دقیقه",
        ["پیاده‌روی آرام تا متوسط",
         "حرکات نرمشی ملایم برای لگن، پشت و مچ پا",
         "بدون تمرین پرفشار؛ خواب و ریکاوری را در اولویت بگذار"]),
}

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, weight REAL, waist REAL,
        reminder TEXT, timezone TEXT, created_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS measurements (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
        weight REAL, waist REAL, recorded_at TEXT
    )""")
    conn.commit()
    return conn

def ensure_user(user_id):
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users(user_id, timezone, created_at) VALUES (?, ?, ?)",
            (user_id, DEFAULT_TZ, datetime.now().isoformat(timespec="seconds")),
        )

def get_user(user_id):
    ensure_user(user_id)
    with connect() as conn:
        row = conn.execute(
            "SELECT weight, waist, reminder, timezone FROM users WHERE user_id=?",
            (user_id,),
        ).fetchone()
    return row

def get_day_index():
    # برنامه با فرض شروع هفته از شنبه؛ Python Monday=0, Saturday=5
    return (datetime.now().weekday() + 2) % 7

def workout_text(index=None):
    if index is None:
        index = get_day_index()
    day, title, duration, items = WEEK[index]
    return (
        f"🏋️ برنامه {day}\n"
        f"🎯 {title}\n⏱ مدت: {duration}\n\n"
        + "\n".join(f"• {item}" for item in items)
        + "\n\nقبل از شروع ۵–۸ دقیقه گرم کن و بعد از تمرین آرام سرد کن."
    )

def weekly_text():
    lines = ["📅 برنامه هفتگی پیشنهادی\n"]
    for i in range(7):
        day, title, duration, _ = WEEK[i]
        lines.append(f"• {day}: {title} — {duration}")
    lines.append("\nروزهای پرفشار را با خواب و ریکاوری کافی همراه کن.")
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user.id)
    await update.message.reply_text(
        "سلام! 👋 به مربی تناسب اندام خوش آمدی.\n\n"
        "هدف اولیه ثبت‌شده برای این نسخه: کاهش تدریجی وزن از ۹۱ به ۸۵ کیلوگرم.\n"
        "از منو برای تمرین، تغذیه، ثبت اندازه‌ها و یادآوری استفاده کن.\n\n"
        "این برنامه عمومی است و جایگزین ارزیابی پزشک یا مربی حضوری نیست.",
        reply_markup=MENU,
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "راهنما:\n"
        "• برای ثبت وزن، عددی مثل 89.5 بفرست.\n"
        "• برای ثبت دور شکم، عدد سانتی‌متر مثل 98 را بفرست.\n"
        "• برای یادآوری، از دستور /remind 19:30 استفاده کن.\n"
        "• برای خاموش کردن یادآوری: /remind off\n"
        "• برای تنظیم منطقه زمانی: /timezone Europe/Madrid\n"
        "• برای حذف اطلاعات ثبت‌شده: /reset",
        reply_markup=MENU,
    )

async def remind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ensure_user(user_id)
    if not context.args or context.args[0].lower() == "off":
        context.job_queue.get_jobs_by_name(str(user_id))
        for job in context.job_queue.get_jobs_by_name(str(user_id)):
            job.schedule_removal()
        with connect() as conn:
            conn.execute("UPDATE users SET reminder=NULL WHERE user_id=?", (user_id,))
        await update.message.reply_text("یادآوری خاموش شد.", reply_markup=MENU)
        return
    try:
        hh, mm = map(int, context.args[0].split(":"))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError
        row = get_user(user_id)
        tz = ZoneInfo(row[3] or DEFAULT_TZ)
        for job in context.job_queue.get_jobs_by_name(str(user_id)):
            job.schedule_removal()
        context.job_queue.run_daily(
            reminder_job,
            time=time(hour=hh, minute=mm, tzinfo=tz),
            name=str(user_id),
            chat_id=update.effective_chat.id,
            data={"user_id": user_id},
        )
        with connect() as conn:
            conn.execute("UPDATE users SET reminder=? WHERE user_id=?", (f"{hh:02d}:{mm:02d}", user_id))
        await update.message.reply_text(
            f"یادآوری روزانه برای ساعت {hh:02d}:{mm:02d} تنظیم شد.\n"
            "برای خاموش کردن: /remind off",
            reply_markup=MENU,
        )
    except Exception:
        await update.message.reply_text(
            "فرمت ساعت درست نیست. نمونه: /remind 19:30\n"
            "برای خاموش کردن: /remind off"
        )

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=context.job.chat_id,
        text="⏰ وقت حرکت است! تمرین امروزت را ببین و قبل از شروع گرم کن.\n\n" + workout_text(),
    )

async def timezone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("نمونه: /timezone Europe/Madrid")
        return
    tzname = context.args[0]
    try:
        ZoneInfo(tzname)
        with connect() as conn:
            conn.execute("UPDATE users SET timezone=? WHERE user_id=?", (tzname, update.effective_user.id))
        await update.message.reply_text(
            f"منطقه زمانی روی {tzname} ثبت شد. اگر یادآوری فعال است، آن را دوباره تنظیم کن."
        )
    except Exception:
        await update.message.reply_text("نام منطقه زمانی معتبر نیست. نمونه: Europe/Madrid یا Asia/Tehran")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with connect() as conn:
        conn.execute("DELETE FROM measurements WHERE user_id=?", (user_id,))
        conn.execute("UPDATE users SET weight=NULL, waist=NULL, reminder=NULL WHERE user_id=?", (user_id,))
    for job in context.job_queue.get_jobs_by_name(str(user_id)):
        job.schedule_removal()
    await update.message.reply_text("اندازه‌ها و یادآوری‌های ذخیره‌شده پاک شدند.", reply_markup=MENU)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with connect() as conn:
        rows = conn.execute(
            "SELECT weight, waist, recorded_at FROM measurements WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()
    if not rows:
        await update.message.reply_text("هنوز اندازه‌ای ثبت نکرده‌ای. از «ثبت وزن» یا «ثبت دور شکم» شروع کن.")
        return
    lines = ["📊 آخرین ثبت‌ها (حداکثر ۱۰ مورد):"]
    for weight, waist, recorded in rows:
        parts = []
        if weight is not None: parts.append(f"وزن: {weight:g} کیلو")
        if waist is not None: parts.append(f"دور شکم: {waist:g} سانتی‌متر")
        lines.append(f"• {recorded[:16]} — " + " | ".join(parts))
    weight_rows = [r for r in rows if r[0] is not None]
    if len(weight_rows) >= 2:
        diff = weight_rows[0][0] - weight_rows[-1][0]
        lines.append(f"\nتغییر وزن بین جدیدترین و قدیمی‌ترین ثبت در این فهرست: {diff:+.1f} کیلوگرم")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user_id = update.effective_user.id
    ensure_user(user_id)

    if text == "🏋️ تمرین امروز":
        await update.message.reply_text(workout_text(), reply_markup=MENU)
    elif text == "📅 برنامه هفتگی":
        await update.message.reply_text(weekly_text(), reply_markup=MENU)
    elif text == "🥗 راهنمای تغذیه":
        await update.message.reply_text(
            "🥗 اصول تغذیه برای کاهش چربی\n\n"
            "• کاهش وزن معمولاً با کسری انرژی ملایم و پایدار ایجاد می‌شود.\n"
            "• در هر وعده منبع پروتئین بگنجان: تخم‌مرغ، ماست پرپروتئین، حبوبات، ماهی، مرغ یا توفو.\n"
            "• نصف بشقاب را سبزیجات، حدود یک‌چهارم را پروتئین و یک‌چهارم را غلات کامل/سیب‌زمینی در نظر بگیر.\n"
            "• نوشیدنی شیرین و ریزه‌خواری پرتکرار را محدود کن؛ آب بنوش.\n"
            "• وزن را در شرایط مشابه ثبت کن و به روند چند هفته‌ای توجه کن.\n\n"
            "کالری دقیق بدون دانستن میزان فعالیت روزانه و وضعیت سلامت قابل تعیین نیست. "
            "چربی‌سوزی موضعی شکم ممکن نیست؛ کاهش چربی کل بدن به کوچک‌شدن دور شکم کمک می‌کند.",
            reply_markup=MENU,
        )
    elif text == "⚖️ ثبت وزن":
        context.user_data["awaiting"] = "weight"
        await update.message.reply_text("وزن امروزت را به کیلوگرم بفرست؛ مثال: 90.4")
    elif text == "📏 ثبت دور شکم":
        context.user_data["awaiting"] = "waist"
        await update.message.reply_text("دور شکمت را به سانتی‌متر بفرست؛ متر را افقی و در شرایط مشابه نگه دار. مثال: 98")
    elif text == "📊 گزارش پیشرفت":
        await report(update, context)
    elif text == "⏰ تنظیم یادآوری":
        await update.message.reply_text(
            "برای یادآوری روزانه بنویس:\n/remind 19:30\n\n"
            "ساعت بر اساس منطقه زمانی ثبت‌شده است. خاموش کردن: /remind off\n"
            "منطقه زمانی: /timezone Europe/Madrid"
        )
    elif text == "⚙️ راهنما":
        await help_cmd(update, context)
    elif context.user_data.get("awaiting") in ("weight", "waist"):
        kind = context.user_data.pop("awaiting")
        try:
            value = float(text.replace(",", "."))
            if value <= 0 or value > 400:
                raise ValueError
            now = datetime.now().isoformat(timespec="minutes")
            with connect() as conn:
                if kind == "weight":
                    conn.execute("UPDATE users SET weight=? WHERE user_id=?", (value, user_id))
                    conn.execute(
                        "INSERT INTO measurements(user_id, weight, recorded_at) VALUES (?, ?, ?)",
                        (user_id, value, now),
                    )
                    msg = f"✅ وزن {value:g} کیلوگرم ثبت شد."
                else:
                    conn.execute("UPDATE users SET waist=? WHERE user_id=?", (value, user_id))
                    conn.execute(
                        "INSERT INTO measurements(user_id, waist, recorded_at) VALUES (?, ?, ?)",
                        (user_id, value, now),
                    )
                    msg = f"✅ دور شکم {value:g} سانتی‌متر ثبت شد."
            await update.message.reply_text(msg + "\nبرای دیدن روند، «گزارش پیشرفت» را انتخاب کن.", reply_markup=MENU)
        except ValueError:
            context.user_data["awaiting"] = kind
            await update.message.reply_text("لطفاً فقط یک عدد معتبر بفرست؛ مثال: 89.5")
    else:
        await update.message.reply_text("یکی از گزینه‌های منو را انتخاب کن یا /help را بزن.", reply_markup=MENU)

def main():
    if not TOKEN:
        raise SystemExit("خطا: متغیر BOT_TOKEN تنظیم نشده است. فایل .env.example را ببین.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("remind", remind_cmd))
    app.add_handler(CommandHandler("timezone", timezone_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    logger.info("Fitness bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
