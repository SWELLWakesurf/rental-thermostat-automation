# Claude Code Setup Guide

This project automates an ecobee thermostat based on OwnerRez vacation rental bookings. When a user asks you to help set this up, walk them through these steps interactively.

## What this project does
- Checks OwnerRez for today's bookings every 30 minutes
- Preheats the rental before guest check-in (default: 3 hours before)
- Drops to away temp after checkout
- Doesn't override guest thermostat adjustments during their stay
- Optional Telegram bot for notifications and remote control

## Setup walkthrough

When helping a user set up this project, go through these steps one at a time:

### Step 1: OwnerRez API key
Ask the user to:
1. Log into OwnerRez
2. Go to Settings > API Keys
3. Create a new key
4. Give you the email and API key
5. Find the Property ID from their property page URL

### Step 2: Ecobee credentials
Ask for their ecobee email and password. Then run the auth command to get their thermostat IDs:

```bash
curl -s -X POST "https://auth.ecobee.com/oauth/token" \
  -H "Content-Type: application/json" \
  -d '{"grant_type":"password","client_id":"183eORFPlXyz9BbDZwqexHPBQoVjgadh","username":"EMAIL","password":"PASSWORD","audience":"https://prod.ecobee.com/api/v1","scope":"openid smartWrite smartRead"}'
```

Use the access_token to list thermostats and help them identify the right one.

Note: ecobee discontinued developer API keys in March 2024. This project uses Auth0 password grant with ecobee's own consumer portal client ID. No developer key needed.

### Step 3: Create .env
Copy .env.example to .env and fill in the values.

### Step 4: Test
Run `python3 thermostat.py status` to verify both APIs connect.

### Step 5: Temperature preferences
Ask the user:
- What guest temp? (default 72°F)
- What away temp? (default 60°F)  
- How many hours before check-in to start heating? (default 3)
- Do they have AC? If no, the cool setpoint stays at 90°F (disabled). If yes, adjust accordingly.

### Step 6: Cron job
Help them set up the cron: `*/30 * * * * cd /path && python3 thermostat.py >> data/cron.log 2>&1`

### Step 7: Telegram (optional)
If they want notifications:
1. Walk them through creating a bot via @BotFather on Telegram
2. Get the bot token
3. Have them message the bot, then fetch the chat ID
4. Add both to .env
5. Set up bot.py as a systemd service

## Key files
- `thermostat.py` — main automation script, runs via cron
- `bot.py` — optional Telegram bot for remote control
- `.env.example` — template for configuration
- `thermostat-bot.service` — systemd service template for the Telegram bot

## No external dependencies
This project uses only Python standard library. No pip install needed.
