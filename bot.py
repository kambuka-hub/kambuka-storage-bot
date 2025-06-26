import os
import logging
import gspread
import threading
from flask import Flask
from google.oauth2.service_account import Credentials
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from together import Together

# === НАСТРОЙКИ ===
TOKEN = os.environ.get("BOT_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")
together_client = Together(api_key=TOGETHER_API_KEY)

# === GOOGLE SHEETS ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("/etc/secrets/service_account.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).sheet1

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ЭТАПЫ ДИАЛОГА ===
WHAT, CONFIRM_NAME, PLACE, NOTE, CONFIRM_ADD = range(5)

# === GPT ОТВЕТ ===
async def get_funny_reply(prompt: str, chat_id: str = None) -> str:
    try:
        response = together_client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3",
            messages=[
                {"role": "system", "content": "Ты весёлый, креативный помощник склада KAMBUKA. Отвечай смешно, но понятно, немного с сарказмом"},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("Ошибка GPT:")
        return f"🤖 GPT не сработал: {e}"

# === СТАРТ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Напиши название или часть названия товара — и я постараюсь его найти.")

# === ПОИСК ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    rows = sheet.get_all_records()
    results = []

    for row in rows:
        row = {k.strip(): str(v).strip() for k, v in row.items()}
        if any(text.lower() in str(value).lower() for value in row.values()):
            results.append(f"📦 {row.get('Что', '—')}\n📍 {row.get('Место', '—')}\n📜 {row.get('Описание', '—')}")

    if results:
        await update.message.reply_text("\n\n".join(results))
        return ConversationHandler.END
    else:
        context.user_data['what'] = text
        funny = await get_funny_reply(
            f"Придумай весёлую фразу про то, что товара с названием '{text}' не существует на складе Камбука.",
            chat_id=update.effective_chat.id if update.effective_chat else None
        )
        keyboard = ReplyKeyboardMarkup([["Да", "Нет"]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"{funny}\nХочешь добавить его на склад?", reply_markup=keyboard)
        return CONFIRM_ADD

# === ПОДТВЕРЖДЕНИЕ ДОБАВЛЕНИЯ ===
async def confirm_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()
    if answer == "да":
        what = context.user_data.get('what', '')
        keyboard = ReplyKeyboardMarkup([["Да", "Нет"]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"Я правильно понял, что товар будет с названием /{what}/?", reply_markup=keyboard)
        return CONFIRM_NAME
    else:
        await update.message.reply_text("Хорошо. Если что — просто напиши другой запрос.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

# === ПОДТВЕРЖДЕНИЕ ИМЕНИ ===
async def confirm_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()
    if answer == "да":
        await update.message.reply_text("На какой полке он лежит? 📍", reply_markup=ReplyKeyboardRemove())
        return PLACE
    else:
        await update.message.reply_text("Хорошо. Напиши правильное название товара: 📦", reply_markup=ReplyKeyboardRemove())
        return WHAT

# === ЗАДАТЬ НАЗВАНИЕ ПОВТОРНО ===
async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['what'] = update.message.text.strip()
    await update.message.reply_text("На какой полке он лежит? 📍")
    return PLACE

# === ДОБАВЛЕНИЕ ПОЛКИ ===
async def add_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['place'] = update.message.text.strip()
    await update.message.reply_text("Добавь описание или комментарий 📜")
    return NOTE

# === ДОБАВЛЕНИЕ ОПИСАНИЯ ===
async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    what = context.user_data.get('what', '')
    place = context.user_data.get('place', '')
    note = update.message.text.strip()
    try:
        sheet.append_row([place, what, note])
        await update.message.reply_text("✅ Товар добавлен!", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        logger.exception("Ошибка при добавлении товара:")
        await update.message.reply_text("❌ Не удалось добавить товар.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# === ОТМЕНА ===
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# === FAKE WEB SERVER FOR RENDER ===
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return 'Kambuka bot is alive!'

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)

# === ЗАПУСК ===
def main():
    threading.Thread(target=run_flask).start()

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        states={
            CONFIRM_ADD: [
                MessageHandler(filters.Regex("^(Да|Нет)$"), confirm_add),
                CommandHandler("cancel", cancel)
            ],
            CONFIRM_NAME: [
                MessageHandler(filters.Regex("^(Да|Нет)$"), confirm_name),
                CommandHandler("cancel", cancel)
            ],
            WHAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name),
                CommandHandler("cancel", cancel)
            ],
            PLACE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_place),
                CommandHandler("cancel", cancel)
            ],
            NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_note),
                CommandHandler("cancel", cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
