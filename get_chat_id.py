#!/usr/bin/env python3
"""Helper script to find your Telegram chat ID.
Usage: python3 get_chat_id.py YOUR_BOT_TOKEN

Make sure you've sent a message to your bot first!
"""
import sys
import json
import ssl
from urllib.request import Request, urlopen

if len(sys.argv) < 2:
    print("Usage: python3 get_chat_id.py YOUR_BOT_TOKEN")
    print("Example: python3 get_chat_id.py 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
    print("\nMake sure you've sent a message to your bot in Telegram first!")
    sys.exit(1)

token = sys.argv[1]
ctx = ssl.create_default_context()

print("Checking for messages to your bot...\n")

try:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    req = Request(url)
    result = json.loads(urlopen(req, context=ctx).read())
except Exception as e:
    print(f"Error: Could not connect to Telegram. Check your bot token.")
    print(f"Detail: {e}")
    sys.exit(1)

updates = result.get("result", [])
if not updates:
    print("No messages found!")
    print("\nMake sure you:")
    print("1. Search for your bot in Telegram (by the username you gave it)")
    print("2. Open a chat with it")
    print("3. Send it any message (just type 'hi')")
    print("4. Then run this script again")
    sys.exit(1)

chat_id = updates[0]["message"]["chat"]["id"]
name = updates[0]["message"]["chat"].get("first_name", "Unknown")
print(f"Found you! Hi {name}!")
print(f"\nYour Chat ID is: {chat_id}")
print(f"\nAdd this to your .env file:")
print(f"TELEGRAM_CHAT_ID={chat_id}")
