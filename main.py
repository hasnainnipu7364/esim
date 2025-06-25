import telebot import gspread import os import re from flask import Flask, request from oauth2client.service_account import ServiceAccountCredentials from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN") GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

Save GOOGLE_CREDS to file

with open("google_creds.json", "w") as f: f.write(GOOGLE_CREDS)

bot = telebot.TeleBot(BOT_TOKEN) app = Flask(name)

Google Sheet Auth

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"] creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope) client = gspread.authorize(creds) sheet = client.open('eSIM Bot Database - Afiliate Plans').worksheet('Bot-data') log_sheet = client.open('eSIM Bot Database - Afiliate Plans').worksheet('Click-Logs') data = sheet.get_all_records()

@app.route("/" + BOT_TOKEN, methods=['POST']) def webhook(): update = telebot.types.Update.de_json(request.stream.read().decode("utf-8")) bot.process_new_updates([update]) return "OK", 200

@app.route("/") def index(): return "Bot is running!", 200

@bot.message_handler(commands=['start']) def send_welcome(message): markup = InlineKeyboardMarkup() continents = sorted(set(row['Continent'].strip().title() for row in data if row['Continent'])) for cont in continents: markup.add(InlineKeyboardButton(cont, callback_data=f"continent_{cont}")) bot.send_message(message.chat.id, "🌍 Choose a continent:", reply_markup=markup)

@bot.message_handler(commands=['help']) def send_help(message): help_text = """\ud83d\udcd6 How to use the bot:

1. Use /start to browse by continent & country.


2. Type a country name (e.g. usa) to search directly.


3. Use filters like: price < 10 data > 5GB validity > 7 days


4. Try: cheapest usa to get the cheapest plans.



#AffiliateBot """ bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("continent_")) def show_countries(call): selected_continent = call.data.replace("continent_", "") countries = sorted(set(row['Country'].strip().title() for row in data if row['Continent'].strip().title() == selected_continent)) markup = InlineKeyboardMarkup() for country in countries: markup.add(InlineKeyboardButton(country, callback_data=f"country_{country}_page_0")) markup.add(InlineKeyboardButton("🔙 Back to Continents", callback_data="back_to_continents"))

