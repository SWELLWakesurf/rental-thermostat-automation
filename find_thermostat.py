#!/usr/bin/env python3
"""Helper script to find your ecobee thermostat ID.
Usage: python3 find_thermostat.py YOUR_EMAIL YOUR_PASSWORD
"""
import sys
import json
import ssl
from urllib.request import Request, urlopen
from urllib.parse import quote

if len(sys.argv) < 3:
    print("Usage: python3 find_thermostat.py YOUR_ECOBEE_EMAIL YOUR_ECOBEE_PASSWORD")
    print("Example: python3 find_thermostat.py john@gmail.com mypassword123")
    sys.exit(1)

email = sys.argv[1]
password = sys.argv[2]
ctx = ssl.create_default_context()

print(f"Logging into ecobee as {email}...")

try:
    req = Request(
        "https://auth.ecobee.com/oauth/token",
        data=json.dumps({
            "grant_type": "password",
            "client_id": "183eORFPlXyz9BbDZwqexHPBQoVjgadh",
            "username": email,
            "password": password,
            "audience": "https://prod.ecobee.com/api/v1",
            "scope": "openid smartWrite smartRead",
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    token = json.loads(urlopen(req, context=ctx).read())["access_token"]
except Exception as e:
    print(f"\nError: Could not log in to ecobee. Check your email and password.")
    print(f"Detail: {e}")
    sys.exit(1)

print("Logged in! Finding your thermostats...\n")

body = json.dumps({
    "selection": {
        "selectionType": "registered",
        "selectionMatch": "",
        "includeRuntime": True,
    }
})
url = f"https://api.ecobee.com/1/thermostat?format=json&body={quote(body)}"
req = Request(url, headers={"Authorization": f"Bearer {token}"})
result = json.loads(urlopen(req, context=ctx).read())

thermostats = result.get("thermostatList", [])
if not thermostats:
    print("No thermostats found on this account.")
    sys.exit(1)

print(f"Found {len(thermostats)} thermostat(s):\n")
print(f"{'Name':<30} {'ID':<20} {'Current Temp':<15} {'Model'}")
print("-" * 80)
for t in thermostats:
    rt = t.get("runtime", {})
    temp = rt.get("actualTemperature", 0) / 10.0
    print(f"{t['name']:<30} {t['identifier']:<20} {temp:.1f}°F{'':<9} {t.get('modelNumber', '?')}")

print(f"\nCopy the ID of the thermostat at your rental and paste it into your .env file")
print(f"as ECOBEE_THERMOSTAT_ID=the_id_here")
