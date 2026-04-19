#!/usr/bin/env python3
"""
Vacation Rental Thermostat Automation
OwnerRez + Ecobee integration

Automatically adjusts your ecobee thermostat based on OwnerRez bookings:
  - Guest arriving today: preheats to GUEST_TEMP before check-in
  - Guest departing today: sets to AWAY_TEMP at checkout
  - Guest staying: leaves thermostat alone (won't override guest adjustments)
  - Vacant: maintains AWAY_TEMP
  - Sends Telegram notifications on changes (optional)

Works with heat-only properties (no AC required).
Ecobee developer API keys are no longer available (discontinued March 2024).
This script uses ecobee's Auth0 login instead — no developer key needed.

Usage:
  python3 thermostat.py           # Run the check (use with cron)
  python3 thermostat.py status    # Show current thermostat + booking status
  python3 thermostat.py guest     # Force guest mode
  python3 thermostat.py away      # Force away mode

License: MIT
"""

import os
import sys
import json
import ssl
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from urllib.error import HTTPError

# Load env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k, v)

SSL_CTX = ssl.create_default_context()

# Config
OWNERREZ_EMAIL = os.environ["OWNERREZ_EMAIL"]
OWNERREZ_API_KEY = os.environ["OWNERREZ_API_KEY"]
OWNERREZ_PROPERTY_ID = os.environ["OWNERREZ_PROPERTY_ID"]
ECOBEE_EMAIL = os.environ["ECOBEE_EMAIL"]
ECOBEE_PASSWORD = os.environ["ECOBEE_PASSWORD"]
ECOBEE_CLIENT_ID = os.environ.get("ECOBEE_CLIENT_ID", "183eORFPlXyz9BbDZwqexHPBQoVjgadh")
ECOBEE_THERMOSTAT_ID = os.environ["ECOBEE_THERMOSTAT_ID"]
GUEST_TEMP = int(os.environ.get("GUEST_TEMP", "72"))
AWAY_TEMP = int(os.environ.get("AWAY_TEMP", "60"))
PREHEAT_HOURS = int(os.environ.get("PREHEAT_HOURS", "3"))
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "thermostat.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("thermostat")


def api_request(url, data=None, headers=None, method=None):
    if data and isinstance(data, dict):
        data = json.dumps(data).encode()
    req = Request(url, data=data, headers=headers or {}, method=method)
    if data and "Content-Type" not in (headers or {}):
        req.add_header("Content-Type", "application/json")
    return json.loads(urlopen(req, context=SSL_CTX, timeout=30).read().decode())


def send_telegram(message):
    """Send a Telegram notification (optional — skips if not configured)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        api_request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
        )
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")


# ============================================================
# OwnerRez
# ============================================================

def get_bookings():
    """Get active bookings for the property from OwnerRez."""
    import base64
    auth = base64.b64encode(f"{OWNERREZ_EMAIL}:{OWNERREZ_API_KEY}".encode()).decode()
    url = f"https://api.ownerrez.com/v2/bookings?property_ids={OWNERREZ_PROPERTY_ID}"
    result = api_request(url, headers={"Authorization": f"Basic {auth}"})
    return [b for b in result.get("items", []) if b.get("status") == "active" and b.get("type") == "booking"]


def get_today_status(bookings):
    """Determine today's booking status.
    Returns: (status, info_dict)
      status: 'guest_here' | 'checkin_today' | 'checkout_today' | 'vacant'
    """
    today = datetime.now().strftime("%Y-%m-%d")

    for b in bookings:
        arrival = b.get("arrival", "")
        departure = b.get("departure", "")
        checkin_time = b.get("check_in", "16:00")
        checkout_time = b.get("check_out", "11:00")

        if arrival == today:
            return "checkin_today", {
                "checkin_time": checkin_time,
                "checkout_time": checkout_time,
                "departure": departure,
                "guests": b.get("adults", 0) + b.get("children", 0),
                "booking_id": b.get("id"),
                "platform": b.get("listing_site", "Direct"),
            }

        if departure == today:
            return "checkout_today", {
                "checkout_time": checkout_time,
                "booking_id": b.get("id"),
            }

        if arrival < today < departure:
            return "guest_here", {
                "departure": departure,
                "guests": b.get("adults", 0) + b.get("children", 0),
            }

    future = [b for b in bookings if b.get("arrival", "") > today]
    if future:
        next_booking = min(future, key=lambda x: x["arrival"])
        return "vacant", {"next_arrival": next_booking["arrival"]}

    return "vacant", {}


# ============================================================
# Ecobee (Auth0 — no developer API key needed)
# ============================================================

def get_ecobee_token():
    """Get a fresh ecobee access token via Auth0 password grant."""
    result = api_request(
        "https://auth.ecobee.com/oauth/token",
        {
            "grant_type": "password",
            "client_id": ECOBEE_CLIENT_ID,
            "username": ECOBEE_EMAIL,
            "password": ECOBEE_PASSWORD,
            "audience": "https://prod.ecobee.com/api/v1",
            "scope": "openid smartWrite smartRead",
        }
    )
    return result["access_token"]


def get_thermostat_status(token):
    """Get current thermostat readings and settings."""
    body = json.dumps({
        "selection": {
            "selectionType": "thermostats",
            "selectionMatch": ECOBEE_THERMOSTAT_ID,
            "includeRuntime": True,
            "includeSettings": True,
        }
    })
    url = f"https://api.ecobee.com/1/thermostat?format=json&body={quote(body)}"
    result = api_request(url, headers={"Authorization": f"Bearer {token}"})
    thermostats = result.get("thermostatList", [])
    if not thermostats:
        return None
    t = thermostats[0]
    rt = t.get("runtime", {})
    return {
        "name": t["name"],
        "temp": rt.get("actualTemperature", 0) / 10.0,
        "heat_setpoint": rt.get("desiredHeat", 0) / 10.0,
        "cool_setpoint": rt.get("desiredCool", 0) / 10.0,
        "hvac_mode": t.get("settings", {}).get("hvacMode", ""),
    }


def set_thermostat_hold(token, heat_temp, cool_temp, hold_type="indefinite"):
    """Set a temperature hold on the thermostat."""
    body = {
        "selection": {
            "selectionType": "thermostats",
            "selectionMatch": ECOBEE_THERMOSTAT_ID,
        },
        "functions": [
            {
                "type": "setHold",
                "params": {
                    "holdType": hold_type,
                    "heatHoldTemp": int(heat_temp * 10),
                    "coolHoldTemp": int(cool_temp * 10),
                }
            }
        ]
    }
    result = api_request(
        "https://api.ecobee.com/1/thermostat?format=json",
        body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    status = result.get("status", {})
    if status.get("code") == 0:
        log.info(f"  Thermostat set: heat={heat_temp}F, cool={cool_temp}F")
        return True
    else:
        log.error(f"  Thermostat set failed: {status}")
        return False


# ============================================================
# State management
# ============================================================

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ============================================================
# Main logic
# ============================================================

def run():
    log.info("=" * 50)
    log.info("Thermostat Check")
    log.info("=" * 50)

    state = load_state()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    # Get bookings
    log.info("Checking OwnerRez bookings...")
    bookings = get_bookings()
    log.info(f"  Found {len(bookings)} active bookings")

    status, info = get_today_status(bookings)
    log.info(f"  Today's status: {status}")

    # Get ecobee status
    log.info("Checking ecobee thermostat...")
    token = get_ecobee_token()
    thermo = get_thermostat_status(token)
    if not thermo:
        log.error("  Could not get thermostat status")
        return
    log.info(f"  Current temp: {thermo['temp']}F | Heat: {thermo['heat_setpoint']}F | Mode: {thermo['hvac_mode']}")

    last_action = state.get("last_action", "")
    last_action_date = state.get("last_action_date", "")

    if status == "checkin_today":
        checkin_hour = int(info["checkin_time"].split(":")[0])
        preheat_hour = checkin_hour - PREHEAT_HOURS

        if current_hour >= preheat_hour and last_action_date != today + "_guest":
            log.info(f"  Guest arriving at {info['checkin_time']} — setting to {GUEST_TEMP}F")
            if set_thermostat_hold(token, GUEST_TEMP, 90):
                save_state({
                    "last_action": "guest_mode",
                    "last_action_date": today + "_guest",
                    "temp_set": GUEST_TEMP,
                })
                send_telegram(
                    f"\U0001f3e0 <b>Guest Mode</b>\n\n"
                    f"Guests arriving today at {info['checkin_time']}\n"
                    f"Thermostat set to <b>{GUEST_TEMP}\u00b0F</b>\n"
                    f"Platform: {info.get('platform', '?')}\n"
                    f"Guests: {info.get('guests', '?')}"
                )
        else:
            log.info(f"  Waiting for preheat time ({preheat_hour}:00) or already set")

    elif status == "checkout_today":
        checkout_hour = int(info["checkout_time"].split(":")[0])

        if current_hour >= checkout_hour and last_action_date != today + "_away":
            log.info(f"  Checkout at {info['checkout_time']} — setting to {AWAY_TEMP}F")
            if set_thermostat_hold(token, AWAY_TEMP, 90):
                save_state({
                    "last_action": "away_mode",
                    "last_action_date": today + "_away",
                    "temp_set": AWAY_TEMP,
                })
                send_telegram(
                    f"\U0001f512 <b>Away Mode</b>\n\n"
                    f"Guests checked out at {info['checkout_time']}\n"
                    f"Thermostat set to <b>{AWAY_TEMP}\u00b0F</b>"
                )
        else:
            log.info(f"  Waiting for checkout time ({checkout_hour}:00) or already set")

    elif status == "guest_here":
        if last_action != "guest_mode":
            log.info(f"  Guests here, first check — setting to {GUEST_TEMP}F")
            set_thermostat_hold(token, GUEST_TEMP, 90)
            save_state({
                "last_action": "guest_mode",
                "last_action_date": today + "_guest",
                "temp_set": GUEST_TEMP,
            })
        else:
            log.info(f"  Guests here, thermostat at {thermo['heat_setpoint']}F — not overriding guest adjustments")

    elif status == "vacant":
        if thermo["heat_setpoint"] > AWAY_TEMP + 2 and last_action != "away_mode":
            log.info(f"  Vacant — setting to {AWAY_TEMP}F")
            if set_thermostat_hold(token, AWAY_TEMP, 90):
                save_state({
                    "last_action": "away_mode",
                    "last_action_date": today + "_away",
                    "temp_set": AWAY_TEMP,
                })
                msg = f"\U0001f512 <b>Away Mode</b>\n\nNo guests — thermostat set to <b>{AWAY_TEMP}\u00b0F</b>"
                if info.get("next_arrival"):
                    msg += f"\nNext booking: {info['next_arrival']}"
                send_telegram(msg)
        else:
            log.info(f"  Vacant, thermostat OK at {thermo['heat_setpoint']}F")

    log.info("Done")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        token = get_ecobee_token()
        thermo = get_thermostat_status(token)
        bookings = get_bookings()
        status, info = get_today_status(bookings)
        print(f"Thermostat: {thermo['temp']}F (heat: {thermo['heat_setpoint']}F, mode: {thermo['hvac_mode']})")
        print(f"Booking status: {status}")
        if info:
            print(f"Details: {json.dumps(info, indent=2)}")
    elif len(sys.argv) > 1 and sys.argv[1] == "guest":
        token = get_ecobee_token()
        set_thermostat_hold(token, GUEST_TEMP, 90)
        print(f"Set to guest mode: {GUEST_TEMP}F")
    elif len(sys.argv) > 1 and sys.argv[1] == "away":
        token = get_ecobee_token()
        set_thermostat_hold(token, AWAY_TEMP, 90)
        print(f"Set to away mode: {AWAY_TEMP}F")
    else:
        run()
