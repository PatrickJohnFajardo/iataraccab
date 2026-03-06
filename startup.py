# startup.py - Baccarat Bot Startup & Registration
# Handles: Machine GUID detection, ngrok tunnel, Supabase bot registration

import subprocess
import time
import requests
import winreg
import os
import json

CONFIG_FILE = "config.json"
ngrok_process = None


def get_machine_guid():
    """Get unique Machine GUID from the Windows registry."""
    try:
        registry = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        key = winreg.OpenKey(registry, r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return guid
    except Exception as e:
        print(f"[startup] Failed to get Machine GUID: {e}")
        return ""


def start_ngrok(port=8000):
    """Start ngrok tunnel and return the public HTTPS URL."""
    global ngrok_process

    print("[startup] Starting ngrok...")
    try:
        ngrok_process = subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("[startup] ngrok not found. Skipping tunnel setup.")
        print("[startup] Install ngrok from https://ngrok.com/download")
        return ""

    time.sleep(3)

    try:
        response = requests.get("http://localhost:4040/api/tunnels")
        if response.status_code == 200:
            for tunnel in response.json().get("tunnels", []):
                if tunnel.get("proto") == "https":
                    return tunnel.get("public_url")
    except Exception as e:
        print(f"[startup] ngrok tunnel error: {e}")

    return ""


def stop_ngrok():
    """Terminate the ngrok process."""
    global ngrok_process
    if ngrok_process:
        ngrok_process.terminate()
        print("[startup] ngrok stopped.")


def load_config():
    """Load config.json."""
    if not os.path.exists(CONFIG_FILE):
        print(f"[startup] {CONFIG_FILE} not found!")
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(config):
    """Save config.json."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def register_bot(pc_name, guid, ngrok_url=""):
    """Register or update this bot in the Supabase `bot_monitoring` table."""
    config = load_config()
    sb = config.get("supabase", {})
    supabase_url = sb.get("url")
    supabase_key = sb.get("key")

    if not supabase_url or not supabase_key:
        print("[startup] Supabase credentials not set — skipping registration.")
        return

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }

    payload = {
        "pc_name": pc_name,
        "status": "Starting",
    }

    # Add ngrok URL if available
    if ngrok_url:
        payload["ngrok_url"] = ngrok_url

    try:
        url = f"{supabase_url}/rest/v1/bot_monitoring?on_conflict=pc_name"
        response = requests.post(url, headers=headers, json=payload, timeout=5)

        if response.status_code in (200, 201):
            print(f"[startup] Bot registered in Supabase (pc_name={pc_name}).")
        else:
            print(f"[startup] Supabase registration failed [{response.status_code}]: {response.text}")
    except Exception as e:
        print(f"[startup] Error registering bot: {e}")


def initialize_environment():
    """
    Main startup routine:
    1. Detect machine GUID and store it in config.json
    2. Start ngrok tunnel (if available)
    3. Register this bot in Supabase
    """
    config = load_config()
    sb = config.get("supabase", {})

    # 1. Detect and store Machine GUID
    guid = get_machine_guid()
    if guid:
        print(f"[startup] Machine GUID: {guid}")
        if sb.get("hardware_id") != guid:
            sb["hardware_id"] = guid
            config["supabase"] = sb
            save_config(config)
            print("[startup] Updated hardware_id in config.json")

    # 2. Start ngrok (optional - won't block if ngrok isn't installed)
    ngrok_url = start_ngrok()
    if ngrok_url:
        print(f"[startup] ngrok URL: {ngrok_url}")

    # 3. Register the bot in Supabase
    pc_name = sb.get("pc_name", "Unknown-PC")
    register_bot(pc_name, guid, ngrok_url)

    return ngrok_url


if __name__ == "__main__":
    print("=" * 50)
    print("  Baccarat Bot - Startup & Registration")
    print("=" * 50)
    url = initialize_environment()
    if url:
        print(f"\nBot is accessible at: {url}")
    else:
        print("\nBot registered (no ngrok tunnel).")
    print("=" * 50)
