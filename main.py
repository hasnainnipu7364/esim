import telebot
import gspread
import os
import re
from flask import Flask, request
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime
from geopy.geocoders import Nominatim
from difflib import get_close_matches

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

with open("google_creds.json", "w") as f:
    f.write(GOOGLE_CREDS)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open('eSIM Bot Database - Afiliate Plans').worksheet('Bot-data')
log_sheet = client.open('eSIM Bot Database - Afiliate Plans').worksheet('Click-Logs')
data = sheet.get_all_records()

alias_map = {
    "usa": "United States of America",
    "us": "United States of America",
    "uk": "United Kingdom",
    "uae": "United Arab Emirates",
    "korea": "South Korea",
    "vietnam": "Viet Nam",
    "russia": "Russian Federation",
    "iran": "Islamic Republic Of Iran",
    "egypt": "Egypt",
    "saudi": "Saudi Arabia",
    "bangla": "Bangladesh"
}

def get_best_match_country(user_input):
    countries = [row['Country'].strip().title() for row in data]
    matches = get_close_matches(user_input.title(), countries, n=1, cutoff=0.6)
    return matches[0] if matches else None

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
    continents = sorted(set(row['Continent'].strip().title() for row in data if row['Continent']))
    for cont in continents:
        markup.add(InlineKeyboardButton(cont, callback_data=f"continent_{cont}"))
    bot.send_message(message.chat.id, "🌍 Select your region to see available eSIM plans, or type your country name:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("continent_"))
def show_countries(call):
    selected_continent = call.data.replace("continent_", "")
    countries = sorted(set(
        row['Country'].strip().title()
        for row in data
        if row['Continent'] and row['Continent'].strip().title() == selected_continent
    ))

    if not countries:
        bot.answer_callback_query(call.id, "❌ No countries found.")
        return

    markup = InlineKeyboardMarkup()
    for country in countries:
        markup.add(InlineKeyboardButton(country, callback_data=f"country_{country}_page_0_{selected_continent}"))

    markup.add(InlineKeyboardButton("🔙 Back to Continents", callback_data="back_to_continents"))

    bot.edit_message_text(
        f"🌍 Showing eSIM plans for {selected_continent}:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_continents")
def go_back_to_continents(call):
    markup = InlineKeyboardMarkup()
    continents = sorted(set(row['Continent'].strip().title() for row in data if row['Continent']))
    for cont in continents:
        markup.add(InlineKeyboardButton(cont, callback_data=f"continent_{cont}"))
    bot.edit_message_text("🌍 Select your region to see available eSIM plans:", chat_id=call.message.chat.id,
                          message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("country_"))
def show_plans_paginated(call):
    parts = call.data.split("_")
    country = parts[1]
    page = int(parts[3]) if len(parts) > 3 else 0
    continent = parts[4] if len(parts) > 4 else None
    per_page = 10

    plans = [row for row in data if row['Country'].strip().title() == country.title()]
    if not plans:
        bot.send_message(call.message.chat.id, "❌ No plans found.")
        return

    start = page * per_page
    end = start + per_page
    current_plans = plans[start:end]

    for row in current_plans:
        send_plan(call.message, row)

    if end < len(plans):
        more_markup = InlineKeyboardMarkup()
        more_markup.add(InlineKeyboardButton("🔁 More", callback_data=f"country_{country}_page_{page + 1}_{continent}"))
        bot.send_message(call.message.chat.id, "👇 More plans available:", reply_markup=more_markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """📖 *How to use the bot:*

1. Type your country name (e.g. `usa`) to search directly.
2. Use /start to browse by region (continent).
3. Use filters like:
   `price < 10`
   `data > 5GB`
   `validity > 7 days`
4. Try: `cheapest usa` to get the cheapest plans.
5. Use /location to get local plans automatically.

Happy travels! ✈️
"""
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['location'])
def ask_for_location(message):
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    button = KeyboardButton(text="📍 Share My Location", request_location=True)
    markup.add(button)
    bot.send_message(message.chat.id, "Click below to share your location:", reply_markup=markup)

@bot.message_handler(content_types=['location'])
def handle_location(message):
    lat = message.location.latitude
    lon = message.location.longitude
    geolocator = Nominatim(user_agent="esim-bot")
    location = geolocator.reverse((lat, lon), language='en')
    country_name = location.raw['address'].get('country')

    if not country_name:
        bot.reply_to(message, "⚠️ Sorry, we couldn't detect your country.")
        return

    country = country_name.strip().title()
    plans = [row for row in data if row['Country'].strip().title() == country]

    if not plans:
        bot.reply_to(message, f"❌ No plans found for {country}.")
    else:
        bot.send_message(message.chat.id, f"🌐 eSIM plans available in {country}:")
        for row in plans[:5]:
            send_plan(message, row)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip().lower()

    if text.startswith("cheapest"):
        user_input = text.replace("cheapest", "").strip()
        country_full = alias_map.get(user_input, get_best_match_country(user_input) or user_input.title())
        plans = [row for row in data if row['Country'].strip().title() == country_full]
        if not plans:
            bot.reply_to(message, f"❌ Sorry! No plans found for '{user_input}'.")
            return
        sorted_plans = sorted(plans, key=lambda x: float(x['Price'].replace('$','')))
        for row in sorted_plans[:5]:
            send_plan(message, row)
        return

    match = re.match(r"(price|data|validity)\s*([<>])\s*(.+)", text)
    if match:
        field, operator, value = match.groups()
        try:
            value = float(value.replace("gb", "").replace("days", "").strip())
            filtered = []
            for row in data:
                raw = str(row[field.title()]).lower()
                raw = re.sub(r"[^\d.]", "", raw)
                try:
                    number = float(raw)
                    if (operator == ">" and number > value) or (operator == "<" and number < value):
                        filtered.append(row)
                except:
                    continue
            if not filtered:
                bot.reply_to(message, "❌ No plans matched your filter. Try something else.")
                return
            for row in filtered[:5]:
                send_plan(message, row)
            return
        except:
            bot.reply_to(message, "⚠️ Invalid filter. Try examples like: price < 10, data > 5")
            return

    user_input = text
    country_full = alias_map.get(user_input, get_best_match_country(user_input) or user_input.title())
    plans = [row for row in data if row['Country'].strip().title() == country_full]
    if not plans:
        bot.reply_to(message, f"❌ Sorry! No plans found for '{user_input}'.\nTry again or type /start")
        return
    for row in plans[:5]:
        send_plan(message, row)

def send_plan(message, row):
    user_id = message.chat.id
    country = row['Country']
    plan = row['Plan']
    price = row['Price']
    link = row['Link']
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    try:
        log_sheet.append_row([timestamp, str(user_id), country, plan, price, link])
    except Exception as e:
        print(f"Logging failed: {e}")

    text = f"🌐 *{country}*\n📱 Plan: {plan}\n📦 Data: {row['Data']}\n⏳ Validity: {row['Validity']}\n💰 Price: {price}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🛒 View & Buy Plan", url=link))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
