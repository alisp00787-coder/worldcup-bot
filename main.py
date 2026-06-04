import os
import sqlite3
import aiohttp
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== تنظیمات =====================
BOT_TOKEN     = os.getenv("BOT_TOKEN", "TOKEN_خودت_رو_اینجا_بذار")
FOOTBALL_TOKEN = os.getenv("FOOTBALL_TOKEN", "TOKEN_فوتبال_اینجا")

WC_CODE = "WC"   # کد جام جهانی در football-data.org

# ===================== دیتابیس =====================
DB = "bot.db"

def init_db():
    with sqlite3.connect(DB) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                points      INTEGER DEFAULT 0,
                total_preds INTEGER DEFAULT 0,
                correct     INTEGER DEFAULT 0,
                joined      TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS predictions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                fixture_id    TEXT,
                home_team     TEXT,
                away_team     TEXT,
                pred_home     INTEGER,
                pred_away     INTEGER,
                actual_home   INTEGER DEFAULT NULL,
                actual_away   INTEGER DEFAULT NULL,
                points_earned INTEGER DEFAULT 0,
                status        TEXT DEFAULT 'pending',
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

def db_register(uid, username, first_name):
    with sqlite3.connect(DB) as c:
        c.execute(
            "INSERT OR IGNORE INTO users(user_id,username,first_name) VALUES(?,?,?)",
            (uid, username, first_name)
        )

def db_get_user(uid):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()

def db_save_pred(uid, fid, home, away, ph, pa):
    with sqlite3.connect(DB) as c:
        ex = c.execute(
            "SELECT id FROM predictions WHERE user_id=? AND fixture_id=?",
            (uid, fid)
        ).fetchone()
        if ex:
            c.execute(
                "UPDATE predictions SET pred_home=?,pred_away=? WHERE user_id=? AND fixture_id=?",
                (ph, pa, uid, fid)
            )
            return False
        else:
            c.execute(
                "INSERT INTO predictions(user_id,fixture_id,home_team,away_team,pred_home,pred_away) VALUES(?,?,?,?,?,?)",
                (uid, fid, home, away, ph, pa)
            )
            c.execute("UPDATE users SET total_preds=total_preds+1 WHERE user_id=?", (uid,))
            return True

def db_leaderboard():
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return c.execute(
            "SELECT first_name,username,points,total_preds,correct FROM users ORDER BY points DESC LIMIT 10"
        ).fetchall()

def db_my_preds(uid):
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return c.execute(
            "SELECT * FROM predictions WHERE user_id=? ORDER BY created_at DESC LIMIT 8",
            (uid,)
        ).fetchall()

# ===================== API فوتبال =====================
class FootballAPI:
    BASE = "https://api.football-data.org/v4"

    def __init__(self, token):
        self.headers = {"X-Auth-Token": token}

    async def _get(self, path, params=None):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{self.BASE}{path}",
                    headers=self.headers,
                    params=params or {},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    return await r.json()
        except Exception as e:
            logger.error(f"API Error: {e}")
            return {}

    async def live(self):
        data = await self._get(f"/competitions/{WC_CODE}/matches", {"status": "LIVE"})
        return data.get("matches", [])

    async def upcoming(self):
        data = await self._get(f"/competitions/{WC_CODE}/matches", {"status": "SCHEDULED"})
        matches = data.get("matches", [])
        return matches[:8]

    async def finished(self):
        data = await self._get(f"/competitions/{WC_CODE}/matches", {"status": "FINISHED"})
        matches = data.get("matches", [])
        return matches[-6:]

    async def standings(self):
        data = await self._get(f"/competitions/{WC_CODE}/standings")
        return data.get("standings", [])

api = FootballAPI(FOOTBALL_TOKEN)

# ===================== کیبوردها =====================
def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 نتایج زنده",     callback_data="live"),
         InlineKeyboardButton("📅 بازی‌های بعدی",  callback_data="upcoming")],
        [InlineKeyboardButton("🏆 پیش‌بینی کن",    callback_data="predict")],
        [InlineKeyboardButton("📊 جدول گروه‌ها",   callback_data="standings"),
         InlineKeyboardButton("🏅 امتیازات من",    callback_data="leaderboard")],
        [InlineKeyboardButton("👤 پروفایل من",      callback_data="profile")],
    ])

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منوی اصلی", callback_data="menu")]])

def fmt_date(dt_str):
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m  %H:%M")
    except:
        return dt_str[:10]

# ===================== هندلرها =====================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db_register(u.id, u.username, u.first_name)
    await update.message.reply_text(
        f"👋 سلام {u.first_name} عزیز!\n\n"
        "⚽ به ربات *جام جهانی ۲۰۲۶* خوش اومدی!\n\n"
        "🌍 اینجا می‌تونی:\n"
        "• نتایج *زنده* بازیا رو ببینی\n"
        "• *پیش‌بینی* کنی و امتیاز بگیری\n"
        "• با بقیه *رقابت* کنی\n"
        "• جدول *گروه‌ها* رو ببینی\n\n"
        "یه گزینه انتخاب کن 👇",
        reply_markup=kb_main(),
        parse_mode="Markdown"
    )

async def btn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if   d == "menu":       await q.edit_message_text("یه گزینه انتخاب کن 👇", reply_markup=kb_main())
    elif d == "live":       await _live(q)
    elif d == "upcoming":   await _upcoming(q)
    elif d == "standings":  await _standings(q)
    elif d == "predict":    await _predict_menu(q, ctx)
    elif d == "leaderboard":await _leaderboard(q)
    elif d == "profile":    await _profile(q)
    elif d.startswith("fix_"):  await _pick_home(q, ctx, d)
    elif d.startswith("ph_"):   await _pick_away(q, ctx, d)
    elif d.startswith("pa_"):   await _save_pred(q, ctx, d)

async def _live(q):
    await q.edit_message_text("⏳ در حال دریافت...")
    matches = await api.live()

    if not matches:
        finished = await api.finished()
        if not finished:
            txt = "⚽ بازی زنده‌ای نداریم.\nبازی‌های بعدی رو چک کن!"
        else:
            txt = "📊 *آخرین نتایج*\n\n"
            for m in finished:
                h = m["homeTeam"]["shortName"]
                a = m["awayTeam"]["shortName"]
                gh = m["score"]["fullTime"]["home"] or 0
                ga = m["score"]["fullTime"]["away"] or 0
                txt += f"✅ {h} *{gh}* \\- *{ga}* {a}\n"
    else:
        txt = "🔴 *بازی‌های زنده*\n\n"
        for m in matches:
            h = m["homeTeam"]["shortName"]
            a = m["awayTeam"]["shortName"]
            gh = m["score"]["fullTime"]["home"] or 0
            ga = m["score"]["fullTime"]["away"] or 0
            txt += f"🔴 {h} *{gh}* \\- *{ga}* {a}\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="live")],
        [InlineKeyboardButton("🔙 منوی اصلی", callback_data="menu")]
    ])
    await q.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")

async def _upcoming(q):
    await q.edit_message_text("⏳ در حال دریافت...")
    matches = await api.upcoming()

    if not matches:
        txt = "📅 بازی برنامه‌ریزی‌شده‌ای پیدا نشد."
    else:
        txt = "📅 *بازی‌های پیش‌رو*\n\n"
        for m in matches:
            h = m["homeTeam"]["name"]
            a = m["awayTeam"]["name"]
            dt = fmt_date(m["utcDate"])
            txt += f"⚽ *{h}* vs *{a}*\n🕐 {dt}\n\n"

    await q.edit_message_text(txt, reply_markup=kb_back(), parse_mode="Markdown")

async def _standings(q):
    await q.edit_message_text("⏳ در حال دریافت...")
    groups = await api.standings()

    if not groups:
        txt = "📊 جدول هنوز در دسترس نیست."
    else:
        txt = "📊 *جدول گروه‌ها*\n\n"
        for g in groups[:4]:
            gname = g.get("group", "گروه")
            txt += f"*{gname}*\n"
            for t in g.get("table", [])[:4]:
                pos = t["position"]
                name = t["team"]["shortName"]
                pts = t["points"]
                txt += f"{pos}\\. {name} — {pts} امتیاز\n"
            txt += "\n"

    await q.edit_message_text(txt, reply_markup=kb_back(), parse_mode="Markdown")

async def _predict_menu(q, ctx):
    await q.edit_message_text("⏳ در حال دریافت بازیا...")
    matches = await api.upcoming()

    if not matches:
        await q.edit_message_text(
            "⚽ در حال حاضر بازی قابل پیش‌بینی وجود نداره.",
            reply_markup=kb_back()
        )
        return

    ctx.user_data["fx"] = {}
    btns = []
    for m in matches[:6]:
        fid = str(m["id"])
        h = m["homeTeam"]["name"]
        a = m["awayTeam"]["name"]
        ctx.user_data["fx"][fid] = {"h": h, "a": a}
        btns.append([InlineKeyboardButton(f"⚽ {h} vs {a}", callback_data=f"fix_{fid}")])

    btns.append([InlineKeyboardButton("🔙 منوی اصلی", callback_data="menu")])
    await q.edit_message_text(
        "🏆 *پیش‌بینی بازی‌ها*\nیه بازی انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(btns),
        parse_mode="Markdown"
    )

async def _pick_home(q, ctx, d):
    fid = d.replace("fix_", "")
    fx = ctx.user_data.get("fx", {}).get(fid)
    if not fx:
        await q.edit_message_text("❌ بازی پیدا نشد.", reply_markup=kb_back())
        return
    ctx.user_data["cur"] = fid
    btns = [[InlineKeyboardButton(str(i), callback_data=f"ph_{i}_{fid}") for i in range(7)]]
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data="predict")])
    await q.edit_message_text(
        f"🎯 *پیش‌بینی*\n\n⚽ *{fx['h']}* vs *{fx['a']}*\n\nگل تیم *{fx['h']}* چقدر می‌شه؟",
        reply_markup=InlineKeyboardMarkup(btns),
        parse_mode="Markdown"
    )

async def _pick_away(q, ctx, d):
    _, ph_s, fid = d.split("_", 2)
    ph = int(ph_s)
    fx = ctx.user_data.get("fx", {}).get(fid)
    if not fx:
        await q.edit_message_text("❌ بازی پیدا نشد.", reply_markup=kb_back())
        return
    ctx.user_data["ph"] = ph
    btns = [[InlineKeyboardButton(str(i), callback_data=f"pa_{i}_{fid}") for i in range(7)]]
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"fix_{fid}")])
    await q.edit_message_text(
        f"🎯 *پیش‌بینی*\n\n⚽ *{fx['h']}* vs *{fx['a']}*\n\n"
        f"گل *{fx['h']}*: {ph} ✅\n\nحالا گل تیم *{fx['a']}* چقدر می‌شه؟",
        reply_markup=InlineKeyboardMarkup(btns),
        parse_mode="Markdown"
    )

async def _save_pred(q, ctx, d):
    _, pa_s, fid = d.split("_", 2)
    pa = int(pa_s)
    ph = ctx.user_data.get("ph", 0)
    fx = ctx.user_data.get("fx", {}).get(fid, {})
    h = fx.get("h", "تیم خانه")
    a = fx.get("a", "تیم مهمان")
    uid = q.from_user.id
    is_new = db_save_pred(uid, fid, h, a, ph, pa)
    status = "✅ ثبت شد" if is_new else "🔄 بروزرسانی شد"
    await q.edit_message_text(
        f"🎯 پیش‌بینیت {status}!\n\n"
        f"⚽ *{h}* {ph} \\- {pa} *{a}*\n\n"
        f"💡 بعد از بازی امتیازت حساب می‌شه!\n\n"
        f"🥇 نتیجه دقیق = *۳ امتیاز*\n"
        f"🥈 برنده درست = *۱ امتیاز*",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 پیش‌بینی بعدی",  callback_data="predict")],
            [InlineKeyboardButton("🏅 جدول امتیازات",  callback_data="leaderboard")],
            [InlineKeyboardButton("🔙 منوی اصلی",      callback_data="menu")],
        ]),
        parse_mode="Markdown"
    )

async def _leaderboard(q):
    rows = db_leaderboard()
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    if not rows:
        txt = "🏅 *جدول امتیازات*\n\nهنوز کسی پیش‌بینی نکرده!\nاول باش 🚀"
    else:
        txt = "🏅 *جدول امتیازات*\n\n"
        for i, r in enumerate(rows):
            m = medals[i] if i < len(medals) else f"{i+1}."
            txt += f"{m} *{r['first_name']}* — {r['points']} امتیاز\n"
    await q.edit_message_text(txt, reply_markup=kb_back(), parse_mode="Markdown")

async def _profile(q):
    uid = q.from_user.id
    u = db_get_user(uid)
    ps = db_my_preds(uid)
    if not u:
        await q.edit_message_text("❌ پروفایل پیدا نشد.", reply_markup=kb_back())
        return
    icons = {"pending":"⏳","correct":"✅","wrong":"❌","partial":"🟡"}
    txt = (
        f"👤 *پروفایل من*\n\n"
        f"👋 {u['first_name']}\n"
        f"⭐ امتیاز: *{u['points']}*\n"
        f"🎯 پیش‌بینی: *{u['total_preds']}*\n"
        f"✅ درست: *{u['correct']}*\n\n"
    )
    if ps:
        txt += "📋 *آخرین پیش‌بینی‌ها:*\n"
        for p in ps:
            ic = icons.get(p["status"], "⏳")
            txt += f"{ic} {p['home_team']} {p['pred_home']}–{p['pred_away']} {p['away_team']}\n"
    await q.edit_message_text(txt, reply_markup=kb_back(), parse_mode="Markdown")

# ===================== اجرا =====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(btn))
    logger.info("✅ ربات شروع به کار کرد!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
