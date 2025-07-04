
import gspread
import os
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
import telebot
from collections import Counter
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDS")
ADMIN_ID = "7042239504"  # Your Telegram User ID

# Save GOOGLE_CREDS to file
with open("google_creds.json", "w") as f:
    f.write(GOOGLE_CREDS)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Google Sheets auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open("eSIM Bot Database - Afiliate Plans").worksheet("Click-Logs")

def generate_report():
    today = datetime.utcnow() + timedelta(hours=6)  # BD Time
    today_str = today.strftime("%Y-%m-%d")
    rows = sheet.get_all_records()

    today_clicks = [row for row in rows if row['Timestamp'].startswith(today_str)]

    total_clicks = len(today_clicks)
    countries = [row['Country'] for row in today_clicks]
    plans = [row['Plan'] for row in today_clicks]

    top_country = Counter(countries).most_common(1)
    top_plan = Counter(plans).most_common(1)

    msg = f"📊 Daily Summary ({today_str}):\n----------------------------\n"
    msg += f"🔢 Total Clicks: {total_clicks}\n"
    msg += f"🌍 Unique Countries: {len(set(countries))}\n"
    msg += f"🔝 Top Country: {top_country[0][0]} ({top_country[0][1]} clicks)\n" if top_country else ""
    msg += f"💳 Top Plan: {top_plan[0][0]}\n" if top_plan else ""
    msg += f"🕒 Date Range: {today_str}"

    bot.send_message(ADMIN_ID, msg)
    return msg

@app.route("/")
def home():
    return "Daily Report Endpoint is running!", 200

@app.route("/daily", methods=["GET"])
def run_daily_report():
    try:
        message = generate_report()
        return "✅ Daily report sent.\n" + message, 200
    except Exception as e:
        return "❌ Failed to send report: " + str(e), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
