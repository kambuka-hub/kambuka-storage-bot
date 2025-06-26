from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import gspread
from google.oauth2.service_account import Credentials
import os
import logging

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

# === КОМАНДЫ ===
MENU_KEYBOARD = ReplyKeyboardMarkup([
    ["🔍 Найти товар"],
    ["➕ Добавить товар"]
], resize_keyboard=True)

user_states = {}  # user_id -> "adding" or None
temp_data = {}     # user_id -> dict

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать в Kambuka Storage Bot!\nВыберите действие:",
        reply_markup=MENU_KEYBOARD
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if text == "🔍 Найти товар":
        await update.message.reply_text("Введите название товара для поиска:")
        user_states[user_id] = "search"

    elif text == "➕ Добавить товар":
        temp_data[user_id] = {}
        user_states[user_id] = "adding_1"
        await update.message.reply_text("Введите Место (например, A1_001):")

    elif user_states.get(user_id) == "search":
        data = sheet.get_all_records()
        results = []
        for row in data:
            row = {k.strip(): v for k, v in row.items()}
            if text.lower() in row.get("Что", "").lower():
                results.append(f"📦 {row.get('Что')}\n📍 {row.get('Место')}\n📝 {row.get('Описание')}")
        if results:
            await update.message.reply_text("\n\n".join(results))
        else:
            await update.message.reply_text("Ничего не найдено.")
        user_states[user_id] = None

    elif user_states.get(user_id) == "adding_1":
        temp_data[user_id]["Место"] = text
        user_states[user_id] = "adding_2"
        await update.message.reply_text("Введите Что (название товара):")

    elif user_states.get(user_id) == "adding_2":
        temp_data[user_id]["Что"] = text
        user_states[user_id] = "adding_3"
        await update.message.reply_text("Введите Описание:")

    elif user_states.get(user_id) == "adding_3":
        temp_data[user_id]["Описание"] = text
        sheet.append_row([
            temp_data[user_id].get("Место"),
            temp_data[user_id].get("Что"),
            temp_data[user_id].get("Описание"),
            ""
        ])
        await update.message.reply_text("✅ Товар добавлен!", reply_markup=MENU_KEYBOARD)
        user_states[user_id] = None
        temp_data.pop(user_id, None)

    else:
        await update.message.reply_text("Выберите действие из меню.", reply_markup=MENU_KEYBOARD)

# === ЗАПУСК ===
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == "__main__":
    app.run_polling()
