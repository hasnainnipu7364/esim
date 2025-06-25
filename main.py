import telebot
import gspread
import os
import re
from flask import Flask, request
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime
from geopy.geocoders import Nominatim

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")

# Save GOOGLE_CREDS to file
with open("google_creds.json", "w") as f:
    f.write(GOOGLE_CREDS)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Google Sheet Auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open('eSIM Bot Database - Afiliate Plans').worksheet('Bot-data')
log_sheet = client.open('eSIM Bot Database - Afiliate Plans').worksheet('Click-Logs')
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
    continents = sorted(set(row['Continent'].strip().title() for row in data if row['Continent']))
    for cont in continents:
        markup.add(InlineKeyboardButton(cont, callback_data=f"continent_{cont}"))
    bot.send_message(message.chat.id, "Select your region or type your country to see eSIM plans", reply_markup=markup)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """\ud83d\udcd6 *How to use the bot:*

1. Use /start to browse by continent & country.
2. Type a country name (e.g. `usa`) to search directly.
3. Use filters like:
   `price < 10`
   `data > 5GB`
   `validity > 7 days`
4. Try: `cheapest usa` to get the cheapest plans.
5. Or use /location to get plans based on your current location.

#AffiliateBot
"""
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['location'])
def ask_for_location(message):
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    button = KeyboardButton(text="\U0001F4CD Share Location", request_location=True)
    markup.add(button)
    bot.send_message(message.chat.id, "Please share your location to get local plans:", reply_markup=markup)

@bot.message_handler(content_types=['location'])
def handle_location(message):
    lat = message.location.latitude
    lon = message.location.longitude
    geolocator = Nominatim(user_agent="esim-bot")
    location = geolocator.reverse((lat, lon), language='en')
    country_name = location.raw['address'].get('country')

    if not country_name:
        bot.reply_to(message, "Sorry, couldn't detect your country.")
        return

    country = country_name.strip().title()
    plans = [row for row in data if row['Country'].strip().title() == country]

    if not plans:
        bot.reply_to(message, f"\u274c No plans found for {country}")
    else:
        bot.send_message(message.chat.id, f"\U0001F4F0 Plans for your country: {country}")
        for row in plans[:5]:
            send_plan(message, row)

@bot.callback_query_handler(func=lambda call: call.data.startswith("continent_"))
def show_countries(call):
    selected_continent = call.data.replace("continent_", "")
    countries = sorted(set(row['Country'].strip().title() for row in data if row['Continent'].strip().title() == selected_continent))
    markup = InlineKeyboardMarkup()
    for country in countries:
        markup.add(InlineKeyboardButton(country, callback_data=f"country_{country}_page_0"))
    markup.add(InlineKeyboardButton("\U0001F519 Back to Continents", callback_data="back_to_continents"))
    bot.edit_message_text(f"📍 Explore eSIM plans available in {selected_continent}:", chat_id=call.message.chat.id,
                      message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_continents")
def back_to_continents(call):
    markup = InlineKeyboardMarkup()
    continents = sorted(set(row['Continent'].strip().title() for row in data if row['Continent']))
    for cont in continents:
        markup.add(InlineKeyboardButton(cont, callback_data=f"continent_{cont}"))
    bot.edit_message_text("\U0001F30D Choose a continent:", chat_id=call.message.chat.id,
                          message_id=call.message.message_id, reply_markup=markup)

def get_continent_by_country(country_name):
    for row in data:
        if row['Country'].strip().title() == country_name:
            return row['Continent'].strip().title()
    return ""

@bot.callback_query_handler(func=lambda call: call.data.startswith("country_"))
def show_plans_paginated(call):
    parts = call.data.split("_")
    country = parts[1]
    page = int(parts[3]) if len(parts) > 3 else 0
    per_page = 10

    plans = [row for row in data if row['Country'].strip().title() == country]
    if not plans:
        bot.send_message(call.message.chat.id, "\u274c No plans found.")
        return

    start = page * per_page
    end = start + per_page
    current_plans = plans[start:end]

    for row in current_plans:
        send_plan(call.message, row)

    if end < len(plans):
        more_markup = InlineKeyboardMarkup()
        more_markup.add(InlineKeyboardButton("\U0001F501 More", callback_data=f"country_{country}_page_{page + 1}"))
        bot.send_message(call.message.chat.id, "\U0001F447 More plans available:", reply_markup=more_markup)

    back_markup = InlineKeyboardMarkup()
    back_markup.add(InlineKeyboardButton("\U0001F519 Back to Countries", callback_data=f"continent_{get_continent_by_country(country)}"))
    bot.send_message(call.message.chat.id, "\u2B05\uFE0F Go back to country list:", reply_markup=back_markup)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    text = message.text.strip().lower()

    if text.startswith("cheapest"):
        country = text.replace("cheapest", "").strip().title()
        plans = [row for row in data if row['Country'].strip().title() == country]
        if not plans:
            bot.reply_to(message, "\u274c No plans found for that country.")
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
                bot.reply_to(message, "\u274c No matching plans found.")
                return
            for row in filtered[:5]:
                send_plan(message, row)
            return
        except:
            bot.reply_to(message, "\u26A0\uFE0F Invalid filter. Try: price < 10, data > 5, validity > 7")
            return

    country = message.text.strip().title()
    plans = [row for row in data if row['Country'].strip().title() == country]
    if not plans:
        bot.reply_to(message, "\u274c No plans found for this country.")
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

    text = (
        f"\U0001F539 Provider: {row['Provider']}\n"
        f"\U0001F4F1 Plan: {plan}\n"
        f"\U0001F4E6 Data: {row['Data']}\n"
        f"\u23F3 Validity: {row['Validity']}\n"
        f"\U0001F4B0 Price: {price}"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("\U0001F517 Buy Now", url=link))
    bot.send_message(message.chat.id, text, reply_markup=markup)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
