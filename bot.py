#!/usr/bin/env python3
"""
Telegram Bot for Thermostat Control
Optional — lets you control the thermostat via Telegram messages.

Commands:
  temp status     — Current temp + booking info
  temp guest      — Force guest mode
  temp away       — Force away mode
  temp set 68     — Set specific temperature
  early checkin   — Heat up now for early arrival
  bookings        — Show upcoming bookings
  help            — Show commands

Run as a systemd service for 24/7 availability.
"""

import os
import sys
import json
import time
import ssl
import logging
from pathlib import Path
from urllib.request import Request, urlopen
from datetime import datetime

# Load env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

SSL_CTX = ssl.create_default_context()
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent / "data")))
OFFSET_FILE = DATA_DIR / "telegram_offset.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(DATA_DIR / "bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bot")

sys.path.insert(0, str(Path(__file__).parent))
import thermostat as thermo


def telegram_api(method, data=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    if data:
        req = Request(url, data=json.dumps(data).encode(),
                      headers={"Content-Type": "application/json"})
    else:
        req = Request(url)
    return json.loads(urlopen(req, context=SSL_CTX).read())


def send(text):
    telegram_api("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    })


def get_offset():
    if OFFSET_FILE.exists():
        return json.loads(OFFSET_FILE.read_text()).get("offset", 0)
    return 0


def save_offset(offset):
    OFFSET_FILE.write_text(json.dumps({"offset": offset}))


def handle_status():
    try:
        token = thermo.get_ecobee_token()
        t = thermo.get_thermostat_status(token)
        bookings = thermo.get_bookings()
        status, info = thermo.get_today_status(bookings)

        msg = f"<b>Thermostat Status</b>\n\n"
        msg += f"Current temp: <b>{t['temp']}\u00b0F</b>\n"
        msg += f"Heat set to: <b>{t['heat_setpoint']}\u00b0F</b>\n"
        msg += f"Mode: {t['hvac_mode']}\n\n"

        if status == "guest_here":
            msg += f"Guests here (departs {info.get('departure', '?')})\nGuests: {info.get('guests', '?')}"
        elif status == "checkin_today":
            msg += f"Check-in today at {info.get('checkin_time', '?')}\nPlatform: {info.get('platform', '?')}\nGuests: {info.get('guests', '?')}"
        elif status == "checkout_today":
            msg += f"Check-out today at {info.get('checkout_time', '?')}"
        elif status == "vacant":
            msg += f"Vacant" + (f" \u2014 next booking: {info['next_arrival']}" if info.get("next_arrival") else "")

        send(msg)
    except Exception as e:
        send(f"Error: {str(e)[:200]}")


def handle_guest():
    try:
        token = thermo.get_ecobee_token()
        thermo.set_thermostat_hold(token, thermo.GUEST_TEMP, 90)
        thermo.save_state({
            "last_action": "guest_mode",
            "last_action_date": datetime.now().strftime("%Y-%m-%d") + "_guest",
            "temp_set": thermo.GUEST_TEMP,
        })
        send(f"\U0001f3e0 Set to <b>guest mode \u2014 {thermo.GUEST_TEMP}\u00b0F</b>")
    except Exception as e:
        send(f"Error: {str(e)[:200]}")


def handle_away():
    try:
        token = thermo.get_ecobee_token()
        thermo.set_thermostat_hold(token, thermo.AWAY_TEMP, 90)
        thermo.save_state({
            "last_action": "away_mode",
            "last_action_date": datetime.now().strftime("%Y-%m-%d") + "_away",
            "temp_set": thermo.AWAY_TEMP,
        })
        send(f"\U0001f512 Set to <b>away mode \u2014 {thermo.AWAY_TEMP}\u00b0F</b>")
    except Exception as e:
        send(f"Error: {str(e)[:200]}")


def handle_set_temp(temp_str):
    try:
        temp = int(temp_str)
        if temp < 45 or temp > 90:
            send("Temperature must be between 45-90\u00b0F")
            return
        token = thermo.get_ecobee_token()
        thermo.set_thermostat_hold(token, temp, 90)
        thermo.save_state({
            "last_action": "manual",
            "last_action_date": datetime.now().strftime("%Y-%m-%d") + "_manual",
            "temp_set": temp,
        })
        send(f"\U0001f321 Thermostat set to <b>{temp}\u00b0F</b>")
    except ValueError:
        send("Invalid temperature. Use: <b>temp set 68</b>")
    except Exception as e:
        send(f"Error: {str(e)[:200]}")


def handle_bookings():
    try:
        bookings = thermo.get_bookings()
        today = datetime.now().strftime("%Y-%m-%d")
        upcoming = [b for b in bookings if b.get("departure", "") >= today]
        upcoming.sort(key=lambda x: x.get("arrival", ""))

        if not upcoming:
            send("No upcoming bookings")
            return

        msg = f"<b>Upcoming Bookings</b>\n\n"
        for b in upcoming[:10]:
            platform = b.get("listing_site", "Direct")
            guests = b.get("adults", 0) + b.get("children", 0)
            msg += f"\U0001f4c5 {b['arrival']} \u2192 {b['departure']}\n"
            msg += f"    {platform} | {guests} guests | ${b.get('total_amount', 0):,.0f}\n\n"

        send(msg)
    except Exception as e:
        send(f"Error: {str(e)[:200]}")


def handle_early():
    try:
        token = thermo.get_ecobee_token()
        thermo.set_thermostat_hold(token, thermo.GUEST_TEMP, 90)
        thermo.save_state({
            "last_action": "guest_mode",
            "last_action_date": datetime.now().strftime("%Y-%m-%d") + "_guest",
            "temp_set": thermo.GUEST_TEMP,
        })
        send(f"\U0001f3e0 <b>Early check-in \u2014 thermostat set to {thermo.GUEST_TEMP}\u00b0F now</b>")
    except Exception as e:
        send(f"Error: {str(e)[:200]}")


def poll():
    log.info("Telegram bot started...")
    offset = get_offset()

    while True:
        try:
            result = telegram_api("getUpdates", {"offset": offset, "timeout": 30})

            for update in result.get("result", []):
                offset = update["update_id"] + 1
                save_offset(offset)

                msg = update.get("message", {})
                chat_id = msg.get("chat", {}).get("id")
                text = (msg.get("text") or "").strip().lower()

                if str(chat_id) != str(CHAT_ID):
                    continue

                log.info(f"Received: {text}")

                if text in ("temp status", "/temp status", "thermostat", "/thermostat"):
                    handle_status()
                elif text in ("temp guest", "/temp guest"):
                    handle_guest()
                elif text in ("temp away", "/temp away"):
                    handle_away()
                elif text.startswith("temp set ") or text.startswith("/temp set "):
                    temp = text.replace("/temp set", "").replace("temp set", "").strip()
                    handle_set_temp(temp)
                elif text in ("bookings", "/bookings"):
                    handle_bookings()
                elif text in ("early checkin", "/early checkin", "early check-in", "/early check-in"):
                    handle_early()
                elif text in ("help", "/help", "/start"):
                    send(
                        "<b>Thermostat Bot</b>\n\n"
                        "<b>Thermostat:</b>\n"
                        "  <b>temp status</b> \u2014 Current temp + booking info\n"
                        "  <b>temp guest</b> \u2014 Set to guest mode\n"
                        "  <b>temp away</b> \u2014 Set to away mode\n"
                        "  <b>temp set 68</b> \u2014 Set specific temperature\n"
                        "  <b>early checkin</b> \u2014 Heat up now for early arrival\n\n"
                        "<b>Bookings:</b>\n"
                        "  <b>bookings</b> \u2014 Show upcoming bookings"
                    )

        except KeyboardInterrupt:
            log.info("Bot stopped")
            break
        except Exception as e:
            log.error(f"Poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    poll()
