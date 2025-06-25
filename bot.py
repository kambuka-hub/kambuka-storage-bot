import logging
from uuid import uuid4
from telegram import Update, ReplyKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    InlineQueryHandler,
)
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# === GOOGLE SHEETS ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("service_account.json", scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(SHEET_URL).sheet1


# === НАСТРОЙКИ ===
TOKEN = os.environ.get("BOT_TOKEN")
SHEET_URL = os.environ.get("SHEET_URL")


# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ЧТЕНИЕ ДАННЫХ ===
def get_data():
    return sheet.get_all_records()

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🔍 Найти товар", "📋 Показать всё"], ["ℹ️ Помощь"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Привет! Я бот склада KAMBUKA. Найду, где лежит любой товар 📦", reply_markup=reply_markup)

# === ОБРАБОТКА СООБЩЕНИЙ ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower()
    data = get_data()
    results = []

    if "помощь" in query:
        await update.message.reply_text("Напиши название товара, и я скажу, где он лежит.")
        return

    if "показать всё" in query:
        lines = [f"📦 {r['Что']} — 🗂 {r['Место']}" for r in data[:20]]
        await update.message.reply_text("\n".join(lines))
        return

    for row in data:
        if query in row['Что'].lower() or query in row['Описание'].lower():
            results.append(f"📦 {row['Что']}\n🗂 {row['Место']}\n📄 {row['Описание']}")

    if results:
        await update.message.reply_text("🔍 Найдено:\n" + "\n\n".join(results))
    else:
        await update.message.reply_text("❌ Ничего не найдено.")

# === INLINE ===
async def inlinequery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.lower()
    data = get_data()
    results = []

    for row in data:
        if query in row['Что'].lower():
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"{row['Что']}",
                    description=f"{row['Место']} — {row['Описание']}",
                    input_message_content=InputTextMessageContent(
                        message_text=f"📦 {row['Что']}\n🗂 {row['Место']}\n📄 {row['Описание']}"
                    )
                )
            )

    await update.inline_query.answer(results[:10], cache_time=0)

# === ЗАПУСК ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(InlineQueryHandler(inlinequery))
    app.run_polling()
