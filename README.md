# Vacation Rental Thermostat Automation

Automatically control your ecobee thermostat based on your OwnerRez bookings. Save on heating costs when your rental is vacant, and make sure it's warm when guests arrive.

**No ecobee developer API key required** — this works around ecobee's discontinued developer program (March 2024) by using their Auth0 login directly.

## What It Does

- Checks your OwnerRez bookings every 30 minutes
- **Guest arriving today** — preheats to your guest temp (default 72°F) 3 hours before check-in
- **Guest checked out** — drops to away temp (default 60°F) at checkout time
- **Guest staying** — leaves the thermostat alone so guests can adjust it however they want
- **Vacant** — maintains away temp until the next booking
- **Telegram notifications** (optional) — get a message when the thermostat changes, plus control it remotely

## Requirements

- An **OwnerRez** account with API access
- An **ecobee** thermostat (any model — Smart, Enhanced, Premium, Lite)
- A **Linux server** (any cheap VPS works — $5/month DigitalOcean, Hetzner, etc.) or a Raspberry Pi
- **Python 3.8+** (no extra packages needed — uses only standard library)
- (Optional) **Telegram** for notifications and remote control

## Quick Start

### 1. Get your OwnerRez API key

1. Log into [OwnerRez](https://www.ownerrez.com)
2. Go to **Settings > API Keys**
3. Create a new API key
4. Note your email and the API key (starts with `pt_`)
5. Find your **Property ID** — go to your property page, the ID is in the URL

### 2. Find your ecobee thermostat ID

Run this command (replace with your ecobee email and password):

```bash
curl -s -X POST "https://auth.ecobee.com/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "password",
    "client_id": "183eORFPlXyz9BbDZwqexHPBQoVjgadh",
    "username": "YOUR_ECOBEE_EMAIL",
    "password": "YOUR_ECOBEE_PASSWORD",
    "audience": "https://prod.ecobee.com/api/v1",
    "scope": "openid smartWrite smartRead"
  }' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
```

Then use that token to list your thermostats:

```bash
TOKEN="paste_token_here"
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.ecobee.com/1/thermostat?format=json&body=%7B%22selection%22%3A%7B%22selectionType%22%3A%22registered%22%2C%22selectionMatch%22%3A%22%22%7D%7D" \
  | python3 -c "
import json,sys
data = json.load(sys.stdin)
for t in data.get('thermostatList', []):
    print(f\"Name: {t['name']} | ID: {t['identifier']}\")
"
```

Note the **ID** of the thermostat you want to control.

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```
OWNERREZ_EMAIL=your@email.com
OWNERREZ_API_KEY=pt_your_key_here
OWNERREZ_PROPERTY_ID=123456
ECOBEE_EMAIL=your@email.com
ECOBEE_PASSWORD=your_password
ECOBEE_THERMOSTAT_ID=your_thermostat_id
GUEST_TEMP=72
AWAY_TEMP=60
PREHEAT_HOURS=3
```

### 4. Test it

```bash
# Check current status
python3 thermostat.py status

# Force guest mode
python3 thermostat.py guest

# Force away mode
python3 thermostat.py away
```

### 5. Set up the cron job

```bash
# Run every 30 minutes
crontab -e
```

Add this line:

```
*/30 * * * * cd /path/to/rental-thermostat-automation && python3 thermostat.py >> data/cron.log 2>&1
```

That's it! The automation will now run every 30 minutes automatically.

---

## Telegram Bot (Optional)

Get notifications and control the thermostat from your phone via Telegram.

### Set up a Telegram bot

1. Install **Telegram** on your phone (free — [iOS](https://apps.apple.com/app/telegram-messenger/id686449807) / [Android](https://play.google.com/store/apps/details?id=org.telegram.messenger))
2. Open Telegram and search for **@BotFather**
3. Send `/newbot`
4. Choose a name (e.g., "My Rental Thermostat")
5. Choose a username (e.g., `my_rental_thermostat_bot`)
6. BotFather will give you a **token** — copy it

### Get your chat ID

1. Send any message to your new bot in Telegram
2. Run this in your terminal (replace YOUR_BOT_TOKEN):

```bash
curl -s "https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates" \
  | python3 -c "import json,sys; [print('Chat ID:', m['message']['chat']['id']) for m in json.load(sys.stdin).get('result',[])]"
```

### Add to .env

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Run the bot

```bash
# Test it
python3 bot.py

# Or run as a systemd service (recommended)
sudo cp thermostat-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable thermostat-bot
sudo systemctl start thermostat-bot
```

### Telegram commands

| Command | What it does |
|---------|-------------|
| `temp status` | Current temp + booking info |
| `temp guest` | Set to guest mode (72°F) |
| `temp away` | Set to away mode (60°F) |
| `temp set 68` | Set specific temperature |
| `early checkin` | Heat up now for early arrival |
| `bookings` | Show upcoming bookings |
| `help` | Show all commands |

---

## Systemd Service Template

Save as `/etc/systemd/system/thermostat-bot.service`:

```ini
[Unit]
Description=Rental Thermostat Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/rental-thermostat-automation
ExecStart=/usr/bin/python3 /path/to/rental-thermostat-automation/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `GUEST_TEMP` | 72 | Temperature when guests are staying (°F) |
| `AWAY_TEMP` | 60 | Temperature when vacant (°F) |
| `PREHEAT_HOURS` | 3 | Hours before check-in to start heating |
| `ECOBEE_CLIENT_ID` | (built-in) | ecobee Auth0 client ID — you shouldn't need to change this |

## How It Works

1. Every 30 minutes, the script calls the OwnerRez API to get your bookings
2. It determines today's status: guest arriving, guest here, guest departing, or vacant
3. Based on the status and time of day, it calls the ecobee API to set the thermostat
4. It tracks what it's already done in `data/state.json` to avoid repeating actions
5. During a guest's stay, it sets the temperature once and then **does not override** — guests can adjust the thermostat freely

## Notes

- **No AC?** The cool setpoint is set to 90°F by default, which effectively disables cooling. If you have AC, change the cool setpoint in the script.
- **Multiple properties?** Run a separate instance for each property with its own `.env` file.
- **ecobee MFA?** If you have multi-factor auth on your ecobee account, you may need to disable it or use an app-specific password.
- **Logs** are stored in `data/thermostat.log` and `data/cron.log`.

## License

MIT — use it however you want.

## Credits

Built by [SWELL Wakesurf](https://swellwakesurf.com) for managing our vacation rental on the North Shore of Lake Superior.
