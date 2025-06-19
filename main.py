
import telebot
import gspread
import os
from flask import Flask, request
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

# Save JSON string to temp file
with open("google_creds.json", "w") as f:
    f.write(GOOGLE_CREDS)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Google Sheet Auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open('eSIM Bot Database - Afiliate Plans').worksheet('Bot-data')
data = sheet.get_all_records()

@app.route("/" + BOT_TOKEN, methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def index():
    return "Bot is running!", 200

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = InlineKeyboardMarkup()
    continents = sorted(set(row['Continent'] for row in data if row['Continent']))
    for cont in continents:
        markup.add(InlineKeyboardButton(cont, callback_data=f"continent_{cont}"))
    bot.send_message(message.chat.id, "🌍 Choose a continent:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("continent_"))
def show_countries(call):
    selected_continent = call.data.replace("continent_", "")
    countries = sorted(set(row['Country'] for row in data if row['Continent'] == selected_continent))
    markup = InlineKeyboardMarkup()
    for country in countries:
        markup.add(InlineKeyboardButton(country, callback_data=f"country_{country}_page_0"))
    bot.edit_message_text(f"📍 Countries in {selected_continent}:", chat_id=call.message.chat.id,
                          message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("country_"))
def show_plans_paginated(call):
    parts = call.data.split("_")
    country = parts[1]
    page = int(parts[3]) if len(parts) > 3 else 0
    per_page = 10

    plans = [row for row in data if row['Country'] == country]
    if not plans:
        bot.send_message(call.message.chat.id, "❌ No plans found.")
        return

    start = page * per_page
    end = start + per_page
    current_plans = plans[start:end]

    for row in current_plans:
        text = (
            f"🔹 Provider: {row['Provider']}\n"
            f"📱 Plan: {row['Plan']}\n"
            f"📦 Data: {row['Data']}\n"
            f"⏳ Validity: {row['Validity']}\n"
            f"💰 Price: {row['Price']}"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔗 Buy Now", url=row['Link']))
        bot.send_message(call.message.chat.id, text, reply_markup=markup)

    if end < len(plans):
        more_markup = InlineKeyboardMarkup()
        more_markup.add(InlineKeyboardButton("🔁 More", callback_data=f"country_{country}_page_{page + 1}"))
        bot.send_message(call.message.chat.id, "👇 More plans available:", reply_markup=more_markup)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
