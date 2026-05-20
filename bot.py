import logging
import os
import json
import re
from datetime import datetime, date
from telegram import (
    Update,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from openai import OpenAI
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import numpy as np
from database import Database

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()

client = OpenAI(
    api_key=os.environ.get("PROXYAPI_KEY"),
    base_url="https://api.proxyapi.ru/openai/v1"
)

DAILY_GOAL_DEFAULT = 2000

# ════════════════════════════════════════════════════════════
#  МЕНЮ КЛАВИАТУРА (внизу экрана)
# ════════════════════════════════════════════════════════════

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📋 Сегодня"),    KeyboardButton("📈 Неделя")],
        [KeyboardButton("🥗 Макросы"),    KeyboardButton("📜 История")],
        [KeyboardButton("📊 Статистика"), KeyboardButton("🎯 Цель")],
        [KeyboardButton("🗑 Удалить последнее"), KeyboardButton("ℹ️ Помощь")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Отправь фото еды 📸 или выбери раздел"
)

# ════════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════════════════════

def encode_image(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


async def analyze_food_image(image_bytes: bytes) -> dict:
    b64 = encode_image(image_bytes)
    prompt = (
        "Ты — эксперт-диетолог. Посмотри на фото еды и верни ТОЛЬКО JSON (без markdown, без ```). "
        "Формат: "
        '{"name":"название блюда","calories":число,"protein":число,"fat":число,"carbs":число,'
        '"weight":число,"items":[{"name":"...","calories":число}]} '
        "Все числа целые, вес в граммах. Если еды нет — верни {\"error\":\"no_food\"}."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()
        try:
            return json.loads(raw)
        except Exception:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                return json.loads(m.group())
            return {"error": "parse_error"}
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return {"error": "api_error"}


def progress_bar(current: int, goal: int, length: int = 12) -> str:
    ratio = min(current / goal, 1.0)
    filled = int(ratio * length)
    bar = '█' * filled + '░' * (length - filled)
    pct = int(ratio * 100)
    emoji = '🔥' if pct >= 100 else ('⚠️' if pct >= 85 else '✅')
    return f"{emoji} [{bar}] {pct}%"


# ════════════════════════════════════════════════════════════
#  ГРАФИКИ
# ════════════════════════════════════════════════════════════

def make_daily_chart(user_id: int) -> BytesIO | None:
    meals = db.get_today_meals(user_id)
    if not meals:
        return None
    goal = db.get_goal(user_id) or DAILY_GOAL_DEFAULT
    names = [m["name"][:16] for m in meals]
    cals  = [m["calories"] for m in meals]
    colors = plt.cm.Set3(np.linspace(0, 1, len(names)))

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(names, cals, color=colors, edgecolor='white', linewidth=1.2)
    ax.axhline(goal, color='tomato', linestyle='--', linewidth=1.5, label=f'Цель {goal} ккал')
    ax.set_title("🍽 Приёмы пищи сегодня", fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel("Калории (ккал)")
    ax.legend(fontsize=9)
    for bar, val in zip(bars, cals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                str(val), ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax.set_ylim(0, max(max(cals) * 1.3, goal * 1.15))
    plt.xticks(rotation=20, ha='right', fontsize=8)
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=130)
    plt.close()
    buf.seek(0)
    return buf


def make_week_chart(user_id: int) -> BytesIO | None:
    data = db.get_week_summary(user_id)
    if not data:
        return None
    goal   = db.get_goal(user_id) or DAILY_GOAL_DEFAULT
    dates  = [datetime.strptime(d["date"], "%Y-%m-%d") for d in data]
    totals = [d["total_calories"] for d in data]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.fill_between(dates, totals, alpha=0.18, color='steelblue')
    ax.plot(dates, totals, marker='o', color='steelblue', linewidth=2.2, markersize=8)
    ax.axhline(goal, color='tomato', linestyle='--', linewidth=1.5, label=f'Цель {goal} ккал')
    for d, v in zip(dates, totals):
        ax.annotate(str(v), (d, v), textcoords="offset points",
                    xytext=(0, 9), ha='center', fontsize=8, fontweight='bold')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    ax.set_title("📈 Калории за 7 дней", fontsize=14, fontweight='bold', pad=12)
    ax.set_ylabel("Ккал / день")
    ax.legend(fontsize=9)
    ax.set_ylim(0, max(max(totals) * 1.25, goal * 1.15))
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=130)
    plt.close()
    buf.seek(0)
    return buf


def make_macros_chart(user_id: int) -> BytesIO | None:
    totals = db.get_today_macros(user_id)
    if not totals or sum(totals.values()) == 0:
        return None
    labels = ['Белки', 'Жиры', 'Углеводы']
    values = [totals['protein'], totals['fat'], totals['carbs']]
    colors = ['#66b3ff', '#ff9999', '#99ff99']
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.pie(values, labels=labels, colors=colors, explode=(0.05,)*3,
           autopct='%1.1f%%', startangle=140, textprops={'fontsize': 11})
    ax.set_title("🥗 Макронутриенты сегодня", fontsize=13, fontweight='bold', pad=14)
    ax.legend([f"{l}: {v}г" for l, v in zip(labels, values)],
              loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=9)
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=130)
    plt.close()
    buf.seek(0)
    return buf


# ════════════════════════════════════════════════════════════
#  ИНЛАЙН-КЛАВИАТУРЫ
# ════════════════════════════════════════════════════════════

def meal_keyboard(meal_id: int) -> InlineKeyboardMarkup:
    """Кнопки под каждым приёмом пищи."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Изменить калории", callback_data=f"edit:{meal_id}"),
            InlineKeyboardButton("🗑 Удалить",          callback_data=f"del:{meal_id}"),
        ],
    ])


def after_photo_keyboard(meal_id: int) -> InlineKeyboardMarkup:
    """Кнопки сразу после распознавания фото."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Изменить калории", callback_data=f"edit:{meal_id}"),
            InlineKeyboardButton("🗑 Удалить",          callback_data=f"del:{meal_id}"),
        ],
        [
            InlineKeyboardButton("📋 Итоги дня",   callback_data="cb:today"),
            InlineKeyboardButton("🥗 Макросы",     callback_data="cb:macros"),
            InlineKeyboardButton("📈 Неделя",      callback_data="cb:week"),
        ],
    ])


def goal_keyboard() -> InlineKeyboardMarkup:
    """Быстрый выбор цели калорий."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1200", callback_data="goal:1200"),
            InlineKeyboardButton("1500", callback_data="goal:1500"),
            InlineKeyboardButton("1800", callback_data="goal:1800"),
        ],
        [
            InlineKeyboardButton("2000", callback_data="goal:2000"),
            InlineKeyboardButton("2200", callback_data="goal:2200"),
            InlineKeyboardButton("2500", callback_data="goal:2500"),
        ],
        [InlineKeyboardButton("✏️ Своё значение", callback_data="goal:custom")],
    ])


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ КОМАНД
# ════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.first_name)
    await update.message.reply_text(
        f"👋 Привет, *{user.first_name}*!\n\n"
        "Я твой дневник питания 🥗\n\n"
        "📸 *Отправь фото еды* — я распознаю блюдо, подсчитаю калории и запишу в дневник.\n\n"
        "Все функции доступны через кнопки меню внизу 👇",
        parse_mode='Markdown',
        reply_markup=MAIN_MENU
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Как пользоваться ботом:*\n\n"
        "📸 Отправь фото еды — получишь калории и КБЖУ\n\n"
        "*Кнопки меню:*\n"
        "📋 Сегодня — список приёмов + столбчатый график\n"
        "📈 Неделя — динамика калорий за 7 дней\n"
        "🥗 Макросы — белки / жиры / углеводы (пирог)\n"
        "📜 История — последние 10 приёмов с кнопками\n"
        "📊 Статистика — средние, максимум, минимум\n"
        "🎯 Цель — установить норму калорий\n"
        "🗑 Удалить последнее — убрать последний приём\n\n"
        "*Под каждым приёмом пищи:*\n"
        "✏️ Изменить калории — скорректировать цифру\n"
        "🗑 Удалить — удалить конкретный приём",
        parse_mode='Markdown',
        reply_markup=MAIN_MENU
    )


async def show_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    meals = db.get_today_meals(uid)
    goal  = db.get_goal(uid) or DAILY_GOAL_DEFAULT
    total = sum(m['calories'] for m in meals)

    if not meals:
        await update.message.reply_text(
            "📭 Сегодня ещё нет записей.\nОтправь фото еды, чтобы начать! 📸",
            reply_markup=MAIN_MENU
        )
        return

    # Шапка
    remaining = goal - total
    sign = "⬇️ Осталось" if remaining >= 0 else "⚠️ Превышение"
    header = (
        f"📋 *Сегодня съедено:*\n\n"
        f"🔢 Итого: *{total} / {goal} ккал*\n"
        f"{progress_bar(total, goal)}\n"
        f"{sign}: *{abs(remaining)} ккал*"
    )
    await update.message.reply_text(header, parse_mode='Markdown', reply_markup=MAIN_MENU)

    # Каждый приём — отдельным сообщением с кнопками
    for m in meals:
        t = datetime.fromisoformat(m['created_at']).strftime('%H:%M')
        await update.message.reply_text(
            f"🍽 *{m['name']}*\n"
            f"🕐 {t}  |  🔥 {m['calories']} ккал\n"
            f"💪 {m.get('protein',0)}г  🧈 {m.get('fat',0)}г  🍞 {m.get('carbs',0)}г",
            parse_mode='Markdown',
            reply_markup=meal_keyboard(m['id'])
        )

    # График
    chart = make_daily_chart(uid)
    if chart:
        await update.message.reply_photo(chart)


async def show_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("📊 Строю график...", reply_markup=MAIN_MENU)
    chart = make_week_chart(uid)
    if chart:
        await update.message.reply_photo(chart, caption="📈 Калории за последние 7 дней")
    else:
        await update.message.reply_text(
            "Пока нет данных за неделю. Добавь хотя бы один приём! 📸",
            reply_markup=MAIN_MENU
        )


async def show_macros(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid    = update.effective_user.id
    totals = db.get_today_macros(uid)
    if not totals or sum(totals.values()) == 0:
        await update.message.reply_text(
            "Нет данных о макронутриентах за сегодня.\nОтправь фото еды! 📸",
            reply_markup=MAIN_MENU
        )
        return
    chart   = make_macros_chart(uid)
    caption = (
        f"🥗 *Макронутриенты сегодня:*\n"
        f"💪 Белки: *{totals['protein']} г*\n"
        f"🧈 Жиры: *{totals['fat']} г*\n"
        f"🍞 Углеводы: *{totals['carbs']} г*"
    )
    if chart:
        await update.message.reply_photo(chart, caption=caption, parse_mode='Markdown')
    else:
        await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=MAIN_MENU)


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    meals = db.get_recent_meals(uid, limit=10)
    if not meals:
        await update.message.reply_text("История пуста.", reply_markup=MAIN_MENU)
        return
    await update.message.reply_text(
        "📜 *Последние 10 приёмов:*\n_(нажми на кнопки под каждым чтобы изменить или удалить)_",
        parse_mode='Markdown', reply_markup=MAIN_MENU
    )
    for m in meals:
        dt = datetime.fromisoformat(m['created_at']).strftime('%d.%m %H:%M')
        await update.message.reply_text(
            f"🍽 *{m['name']}*\n"
            f"📅 {dt}  |  🔥 {m['calories']} ккал\n"
            f"💪 {m.get('protein',0)}г  🧈 {m.get('fat',0)}г  🍞 {m.get('carbs',0)}г",
            parse_mode='Markdown',
            reply_markup=meal_keyboard(m['id'])
        )


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s   = db.get_stats(uid)
    if not s or s['total_meals'] == 0:
        await update.message.reply_text(
            "Статистика недоступна — добавь первый приём! 📸",
            reply_markup=MAIN_MENU
        )
        return
    await update.message.reply_text(
        f"📊 *Общая статистика:*\n\n"
        f"🍽 Всего приёмов: *{s['total_meals']}*\n"
        f"📅 Дней отслеживания: *{s['days_tracked']}*\n"
        f"🔥 Среднее в день: *{s['avg_daily']} ккал*\n"
        f"📈 Максимум за день: *{s['max_daily']} ккал*\n"
        f"📉 Минимум за день: *{s['min_daily']} ккал*\n"
        f"🏆 Самый сытый день: *{s['best_day']}*",
        parse_mode='Markdown', reply_markup=MAIN_MENU
    )


async def show_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    current = db.get_goal(uid) or DAILY_GOAL_DEFAULT
    await update.message.reply_text(
        f"🎯 Текущая цель: *{current} ккал/день*\n\nВыбери новую или введи своё значение:",
        parse_mode='Markdown',
        reply_markup=goal_keyboard()
    )


async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    meal = db.delete_last_meal(uid)
    if meal:
        await update.message.reply_text(
            f"🗑 Удалено: *{meal['name']}* ({meal['calories']} ккал)",
            parse_mode='Markdown', reply_markup=MAIN_MENU
        )
    else:
        await update.message.reply_text("Нет приёмов для удаления.", reply_markup=MAIN_MENU)


# ════════════════════════════════════════════════════════════
#  ОБРАБОТКА ТЕКСТА (кнопки меню + ввод данных)
# ════════════════════════════════════════════════════════════

MENU_MAP = {
    "📋 Сегодня":           show_today,
    "📈 Неделя":            show_week,
    "🥗 Макросы":           show_macros,
    "📜 История":           show_history,
    "📊 Статистика":        show_stats,
    "🎯 Цель":              show_goal,
    "🗑 Удалить последнее": delete_last,
    "ℹ️ Помощь":            cmd_help,
}

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid  = update.effective_user.id

    # Ожидаем ввод калорий для редактирования
    if context.user_data.get('awaiting_edit'):
        meal_id = context.user_data.pop('awaiting_edit')
        try:
            new_cal = int(text.strip())
            if new_cal <= 0 or new_cal > 9999:
                raise ValueError
            db.update_meal_calories(uid, meal_id, new_cal)
            await update.message.reply_text(
                f"✅ Калории обновлены: *{new_cal} ккал*",
                parse_mode='Markdown', reply_markup=MAIN_MENU
            )
        except ValueError:
            await update.message.reply_text(
                "Введи число от 1 до 9999, например: *350*",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_edit'] = meal_id
        return

    # Ожидаем ввод своей цели калорий
    if context.user_data.get('awaiting_goal'):
        context.user_data.pop('awaiting_goal')
        try:
            new_goal = int(text.strip())
            if new_goal < 500 or new_goal > 10000:
                raise ValueError
            db.set_goal(uid, new_goal)
            await update.message.reply_text(
                f"✅ Цель установлена: *{new_goal} ккал/день*",
                parse_mode='Markdown', reply_markup=MAIN_MENU
            )
        except ValueError:
            await update.message.reply_text(
                "Введи число от 500 до 10000.", reply_markup=MAIN_MENU
            )
        return

    # Кнопки главного меню
    handler = MENU_MAP.get(text)
    if handler:
        await handler(update, context)
    else:
        await update.message.reply_text(
            "📸 Отправь фото еды или выбери раздел в меню 👇",
            reply_markup=MAIN_MENU
        )


# ════════════════════════════════════════════════════════════
#  ОБРАБОТКА ФОТО
# ════════════════════════════════════════════════════════════

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    db.ensure_user(uid, update.effective_user.first_name)

    msg = await update.message.reply_text(
        "🔍 Анализирую фото...", reply_markup=MAIN_MENU
    )

    photo      = update.message.photo[-1]
    file       = await context.bot.get_file(photo.file_id)
    img_bytes  = await file.download_as_bytearray()
    result     = await analyze_food_image(bytes(img_bytes))

    # Очищаем спецсимволы Markdown из названия
    if "name" in result:
        result["name"] = result["name"].replace("*", "").replace("_", " ").replace("`", "")

    if "error" in result:
        err_map = {
            "no_food":    "🤷 На фото не видно еды. Попробуй другое фото!",
            "api_error":  "❌ Ошибка связи с AI. Попробуй через минуту.",
            "parse_error":"❌ Не смог распознать ответ AI. Попробуй ещё раз.",
        }
        await msg.edit_text(err_map.get(result["error"], "❌ Ошибка. Попробуй ещё раз."))
        return

    goal      = db.get_goal(uid) or DAILY_GOAL_DEFAULT
    meal_id   = db.add_meal(uid, result)
    today_sum = sum(m['calories'] for m in db.get_today_meals(uid))

    items_text = ""
    if result.get("items"):
        items_text = "\n" + "\n".join(
            f"  • {it['name']}: {it['calories']} ккал"
            for it in result["items"][:5]
        )

    weight_str = f"~{result['weight']} г" if result.get("weight") else ""

    text = (
        f"✅ *{result['name']}*"
        + (f"  {weight_str}" if weight_str else "")
        + f"\n\n🔥 Калории: *{result['calories']} ккал*{items_text}\n\n"
        f"💪 Белки: {result.get('protein', 0)} г  "
        f"🧈 Жиры: {result.get('fat', 0)} г  "
        f"🍞 Углеводы: {result.get('carbs', 0)} г\n\n"
        f"📊 Сегодня: *{today_sum} / {goal} ккал*\n"
        f"{progress_bar(today_sum, goal)}"
    )

    await msg.edit_text(
        text, parse_mode='Markdown',
        reply_markup=after_photo_keyboard(meal_id)
    )


# ════════════════════════════════════════════════════════════
#  ОБРАБОТКА ИНЛАЙН-КНОПОК
# ════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()
    data = q.data

    # ── Удалить конкретный приём ──────────────────────────
    if data.startswith("del:"):
        meal_id = int(data.split(":")[1])
        meal    = db.delete_meal_by_id(uid, meal_id)
        if meal:
            await q.edit_message_text(
                f"🗑 *{meal['name']}* удалено ({meal['calories']} ккал)",
                parse_mode='Markdown'
            )
        else:
            await q.edit_message_text("Приём уже был удалён.")

    # ── Изменить калории приёма ───────────────────────────
    elif data.startswith("edit:"):
        meal_id = int(data.split(":")[1])
        meal    = db.get_meal_by_id(uid, meal_id)
        if meal:
            context.user_data['awaiting_edit'] = meal_id
            await q.message.reply_text(
                f"✏️ *{meal['name']}* — сейчас *{meal['calories']} ккал*\n\n"
                f"Введи новое значение калорий:",
                parse_mode='Markdown'
            )
        else:
            await q.answer("Приём не найден.", show_alert=True)

    # ── Установить цель (готовые варианты) ────────────────
    elif data.startswith("goal:"):
        val = data.split(":")[1]
        if val == "custom":
            context.user_data['awaiting_goal'] = True
            await q.message.reply_text(
                "Введи свою цель (число калорий в день), например *1800*:",
                parse_mode='Markdown'
            )
        else:
            new_goal = int(val)
            db.set_goal(uid, new_goal)
            await q.edit_message_text(
                f"✅ Цель установлена: *{new_goal} ккал/день*",
                parse_mode='Markdown'
            )

    # ── Общие callback из кнопок под фото ─────────────────
    elif data == "cb:today":
        meals = db.get_today_meals(uid)
        goal  = db.get_goal(uid) or DAILY_GOAL_DEFAULT
        total = sum(m['calories'] for m in meals)
        if not meals:
            await q.message.reply_text("Сегодня приёмов нет. Отправь фото еды 📸")
            return
        remaining = goal - total
        sign = "⬇️ Осталось" if remaining >= 0 else "⚠️ Превышение"
        lines = [
            f"📋 *Сегодня съедено:*\n",
            f"🔢 Итого: *{total} / {goal} ккал*",
            progress_bar(total, goal),
            f"{sign}: *{abs(remaining)} ккал*\n",
        ]
        for i, m in enumerate(meals, 1):
            t = datetime.fromisoformat(m['created_at']).strftime('%H:%M')
            lines.append(f"{i}. {m['name']} — *{m['calories']} ккал* ({t})")
        await q.message.reply_text('\n'.join(lines), parse_mode='Markdown')
        chart = make_daily_chart(uid)
        if chart:
            await q.message.reply_photo(chart)

    elif data == "cb:macros":
        totals = db.get_today_macros(uid)
        if not totals or sum(totals.values()) == 0:
            await q.message.reply_text("Нет данных о макросах за сегодня.")
            return
        chart   = make_macros_chart(uid)
        caption = (
            f"🥗 *Макросы сегодня:*\n"
            f"💪 Белки: *{totals['protein']} г*\n"
            f"🧈 Жиры: *{totals['fat']} г*\n"
            f"🍞 Углеводы: *{totals['carbs']} г*"
        )
        if chart:
            await q.message.reply_photo(chart, caption=caption, parse_mode='Markdown')
        else:
            await q.message.reply_text(caption, parse_mode='Markdown')

    elif data == "cb:week":
        chart = make_week_chart(uid)
        if chart:
            await q.message.reply_photo(chart, caption="📈 Калории за последние 7 дней")
        else:
            await q.message.reply_text("Нет данных за неделю.")


# ════════════════════════════════════════════════════════════
#  ЗАПУСК
# ════════════════════════════════════════════════════════════

def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    app   = Application.builder().token(token).build()

    # Команды
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("today",   show_today))
    app.add_handler(CommandHandler("week",    show_week))
    app.add_handler(CommandHandler("macros",  show_macros))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("stats",   show_stats))
    app.add_handler(CommandHandler("goal",    show_goal))
    app.add_handler(CommandHandler("delete",  delete_last))

    # Фото → анализ
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Инлайн-кнопки
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Текст (кнопки меню + ввод данных)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("✅ Bot started!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
