# Vacation Rental Thermostat Automation

Automatically control your ecobee thermostat based on your OwnerRez bookings. Save on heating costs when your rental is vacant, and make sure it's warm when guests arrive.

**No ecobee developer API key required** — ecobee stopped issuing developer keys in March 2024. This works without one.

## What It Does

- Checks your OwnerRez bookings every 30 minutes
- **Guest arriving today** — heats to 72°F before check-in so it's warm when they walk in
- **Guest checked out** — drops to 60°F to save energy
- **Guest staying** — leaves the thermostat alone so guests can adjust it however they want
- **No guests** — keeps it at 60°F until the next booking
- **Phone notifications** (optional) — get a text via Telegram when the thermostat changes, plus control it from your phone

## What You Need

- An **OwnerRez** account
- An **ecobee** thermostat (any model)
- A **Hostinger VPS** (~$6/month) — this is a small cloud computer that runs the automation 24/7
- About **30 minutes** to set everything up

---

## Setup Guide

### Step 1: Get a Hostinger VPS

This is the computer that will run the automation for you in the cloud. Think of it like a tiny computer that's always on.

1. Go to [Hostinger VPS Hosting](https://www.hostinger.com/vps-hosting) and sign up
2. Choose the **KVM 1** plan (the cheapest one — it's more than enough)
3. When it asks for an operating system, choose **Ubuntu 24.04**
4. Set a **root password** — write it down, you'll need it
5. Wait for it to finish setting up (takes 1-2 minutes)
6. You'll see an **IP address** on your dashboard (looks like `123.456.78.90`) — write that down too

### Step 2: Open the Terminal on Your VPS

You need to type commands into your VPS. Hostinger makes this easy:

1. In your Hostinger dashboard, click on your VPS
2. Look for a button that says **Terminal** or **Browser Terminal** or **SSH Terminal**
3. Click it — a black window will open where you can type commands
4. Log in with username `root` and the password you set in Step 1

You should see something like `root@vps:~#` — that means you're in!

### Step 3: Download the Automation

Copy and paste this entire block into the terminal and press Enter:

```bash
apt update -y && apt install -y python3 git
git clone https://github.com/SWELLWakesurf/rental-thermostat-automation.git
cd rental-thermostat-automation
cp .env.example .env
```

### Step 4: Get Your OwnerRez API Key

1. Log into [OwnerRez](https://www.ownerrez.com)
2. Click **Settings** (gear icon) in the top right
3. Click **API Keys** in the left menu
4. Click **Create API Key**
5. Write down:
   - Your **OwnerRez email address**
   - The **API key** (starts with `pt_`)
6. Go to your **property page** in OwnerRez — look at the URL in your browser. You'll see a number in the URL — that's your **Property ID**

### Step 5: Find Your Ecobee Thermostat ID

Copy and paste this into the terminal (replace `YOUR_EMAIL` and `YOUR_PASSWORD` with your ecobee login):

```bash
python3 find_thermostat.py YOUR_EMAIL YOUR_PASSWORD
```

It will show you a list of your thermostats with their names and IDs. Write down the **ID** of the thermostat at your rental.

### Step 6: Set Up Your Configuration

Type this in the terminal:

```bash
nano .env
```

A text editor will open. Fill in your information (use arrow keys to move around):

```
OWNERREZ_EMAIL=your_ownerrez_email@example.com
OWNERREZ_API_KEY=pt_your_key_here
OWNERREZ_PROPERTY_ID=123456
ECOBEE_EMAIL=your_ecobee_email@example.com
ECOBEE_PASSWORD=your_ecobee_password
ECOBEE_THERMOSTAT_ID=123456789012
GUEST_TEMP=72
AWAY_TEMP=60
PREHEAT_HOURS=3
```

When you're done:
- Press **Ctrl+O** (the letter O, not zero) then **Enter** to save
- Press **Ctrl+X** to exit

### Step 7: Test It

```bash
python3 thermostat.py status
```

You should see your thermostat's current temperature and your next booking. If you see an error, double-check your email/password/API key in the `.env` file.

### Step 8: Turn It On

Copy and paste this entire block — it sets up the automation to run every 30 minutes automatically:

```bash
(crontab -l 2>/dev/null; echo "*/30 * * * * cd $(pwd) && python3 thermostat.py >> data/cron.log 2>&1") | crontab -
echo "Automation is now running every 30 minutes!"
```

**That's it! You're done.** The automation will now check your bookings and adjust the thermostat every 30 minutes, 24/7.

---

## Optional: Get Phone Notifications via Telegram

Want to get a message on your phone when the thermostat changes? Want to control it remotely (like heating up early for an early check-in)? Set up the Telegram bot.

### What is Telegram?

Telegram is a free messaging app (like iMessage or WhatsApp). We use it because it lets you create your own "bot" that can send you automated messages.

### Set Up Telegram (5 minutes)

1. **Download Telegram** on your phone
   - iPhone: [Download from App Store](https://apps.apple.com/app/telegram-messenger/id686449807)
   - Android: [Download from Google Play](https://play.google.com/store/apps/details?id=org.telegram.messenger)
2. **Create an account** (just needs your phone number)
3. **Create your bot:**
   - In Telegram, search for **@BotFather** and open a chat with it
   - Send the message: `/newbot`
   - It will ask for a name — type something like: `My Rental Thermostat`
   - It will ask for a username — type something like: `my_rental_thermo_bot` (must end in `bot`)
   - BotFather will reply with a **token** — it looks like `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`. **Copy this token.**
4. **Get your Chat ID:**
   - Search for your new bot's username in Telegram and open a chat with it
   - Send it any message (just type "hi")
   - Now go to your VPS terminal and type (replace YOUR_TOKEN with the token from step 3):

```bash
python3 get_chat_id.py YOUR_TOKEN
```

   - It will show your **Chat ID** (a number). Write it down.

5. **Add to your configuration:**

```bash
nano .env
```

Add these two lines at the bottom (replace with your actual token and chat ID):

```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Save with **Ctrl+O**, **Enter**, **Ctrl+X**.

6. **Start the bot:**

Copy and paste this entire block:

```bash
cat > /etc/systemd/system/thermostat-bot.service << EOF
[Unit]
Description=Rental Thermostat Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python3 $(pwd)/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable thermostat-bot
systemctl start thermostat-bot
echo "Telegram bot is now running!"
```

7. **Test it** — open Telegram and send `help` to your bot. It should reply with a list of commands!

### Telegram Commands

| What to type | What it does |
|---------|-------------|
| `temp status` | Shows current temperature + booking info |
| `temp guest` | Sets thermostat to guest mode (72°F) |
| `temp away` | Sets thermostat to away mode (60°F) |
| `temp set 68` | Sets thermostat to a specific temperature |
| `early checkin` | Guest arriving early? Heats up right now |
| `bookings` | Shows your upcoming bookings |
| `help` | Shows all available commands |

---

## Settings You Can Change

Edit these in your `.env` file:

| Setting | Default | What it means |
|---------|---------|-------------|
| `GUEST_TEMP` | 72 | Temperature when guests are staying (°F) |
| `AWAY_TEMP` | 60 | Temperature when no one is there (°F) |
| `PREHEAT_HOURS` | 3 | How many hours before check-in to start heating |

---

## How It Works (Behind the Scenes)

1. Every 30 minutes, the script checks OwnerRez for today's bookings
2. If a guest is arriving today, it heats up 3 hours before their check-in time
3. If a guest checked out today, it drops the temp to save energy
4. If guests are staying, it leaves the thermostat alone — they can adjust it freely
5. If the rental is empty, it keeps the temp low
6. The cool setpoint is set to 90°F (effectively off) — this is designed for heat-only properties. If you have AC, you can adjust this in the script.

## Troubleshooting

**"Invalid username or token" error** — Double-check your OwnerRez email and API key in the `.env` file.

**"Authentication error" from ecobee** — Make sure your ecobee email and password are correct. If you use Google/Apple sign-in for ecobee, you'll need to set a regular password on your ecobee account first.

**Thermostat not changing** — Run `python3 thermostat.py status` to see what the script thinks is happening. Check `data/thermostat.log` for error messages.

**Multiple properties** — You can run a separate copy for each property. Just clone the repo again into a different folder and set up a separate `.env` file.

---

## Don't Want to Set It Up Yourself?

We offer a **fully managed version** — we set everything up and host it for you. You just enter your OwnerRez and ecobee info and we handle the rest. Includes Telegram notifications and remote control.

DM me for details and pricing:
- **Facebook:** [Adam Moore](https://www.facebook.com/MacPres)
- **Instagram:** [@mooreswells](https://www.instagram.com/mooreswells)
- **Email:** adam@blackbeachvacations.com

## Using Claude Code

If you have [Claude Code](https://claude.ai/code), you can clone this repo and ask Claude to walk you through the entire setup. It will help you configure everything step by step.

## License

MIT — use it however you want.

## Credits

Built by [Adam Moore](https://www.facebook.com/MacPres) for managing a vacation rental on the North Shore of Lake Superior.
