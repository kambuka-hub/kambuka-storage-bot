import os
import logging
import gspread
import threading
from flask import Flask
from google.oauth2.service_account import Credentials
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# === НАСТРОЙКИ ===
TOKEN = os.environ.get("BOT_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")

# === GOOGLE SHEETS ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("/etc/secrets/service_account.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).sheet1

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ЭТАПЫ ДИАЛОГА ===
WHAT, PLACE, NOTE, CONFIRM_ADD = range(4)

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
    else:
        context.user_data['what'] = text
        keyboard = ReplyKeyboardMarkup([["Да", "Нет"]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"❌ Товар /{text}/ не найден. Хотите добавить его на склад?", reply_markup=keyboard)
        return CONFIRM_ADD

# === ПОДТВЕРЖДЕНИЕ ДОБАВЛЕНИЯ ===
async def confirm_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()
    if answer == "да":
        keyboard = ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)
        await update.message.reply_text("На какой полке он лежит? 📍", reply_markup=keyboard)
        return PLACE
    else:
        await update.message.reply_text("Хорошо. Если что — просто напиши другой запрос.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

# === ДОБАВЛЕНИЕ ТОВАРА ===
async def add_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['place'] = update.message.text.strip()
    keyboard = ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)
    await update.message.reply_text("Добавь описание или комментарий 📜", reply_markup=keyboard)
    return NOTE

async def add_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    what = context.user_data.get('what', '')
    place = context.user_data.get('place', '')
    note = update.message.text.strip()
    try:
        sheet.append_row([place, what, note])  # правильный порядок: Место, Что, Описание
        await update.message.reply_text("✅ Товар добавлен!", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        logging.exception("Ошибка при добавлении товара:")
        await update.message.reply_text("❌ Не удалось добавить товар.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

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

# === ЗАПУСК ВСЕГО ===
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
