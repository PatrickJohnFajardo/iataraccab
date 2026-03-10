# startup.py - Baccarat Bot Startup & Registration
# Handles: Machine GUID detection, Supabase unit registration

import time
import requests
import winreg
import os
import json

CONFIG_FILE = "config.json"


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


def register_unit(guid):
    """Register or update this machine in the Supabase 'units' table."""
    config = load_config()
    sb = config.get("supabase", {})
    supabase_url = sb.get("url")
    supabase_key = sb.get("key")

    if not supabase_url or not supabase_key:
        print("[startup] Supabase credentials not set — skipping unit registration.")
        return

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    # 1. Check if a unit with this GUID already exists
    try:
        resp = requests.get(
            f"{supabase_url}/rest/v1/units",
            params={"guid": f"eq.{guid}", "select": "id,unit_name"},
            headers=headers,
            timeout=5,
        )
        existing = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print(f"[startup] Error checking existing unit: {e}")
        return

    payload = {"status": "connected"}

    # 2a. PATCH if existing row found
    if existing:
        unit_id = existing[0]["id"]
        unit_name = existing[0].get("unit_name", "Unknown")
        try:
            resp = requests.patch(
                f"{supabase_url}/rest/v1/units",
                params={"id": f"eq.{unit_id}"},
                json=payload,
                headers={**headers, "Prefer": "return=representation"},
                timeout=5,
            )
            if resp.status_code in (200, 204):
                print(f"[startup] Unit updated: {unit_name} (id={unit_id})")
            elif resp.status_code == 404:
                print("[startup] Units table not found — skipping unit registration (non-critical).")
            else:
                print(f"[startup] Unit update failed [{resp.status_code}]: {resp.text}")
        except Exception as e:
            print(f"[startup] Error updating unit: {e}")

    # 2b. POST if no existing row
    else:
        try:
            resp = requests.post(
                f"{supabase_url}/rest/v1/units",
                json={**payload, "guid": guid},
                headers={**headers, "Prefer": "return=representation"},
                timeout=5,
            )
            if resp.status_code in (200, 201):
                new_unit = resp.json()[0] if resp.json() else {}
                print(f"[startup] New unit registered (id={new_unit.get('id', '?')})")
            elif resp.status_code == 404:
                print("[startup] Units table not found — skipping unit registration (non-critical).")
            else:
                print(f"[startup] Unit registration failed [{resp.status_code}]: {resp.text}")
        except Exception as e:
            print(f"[startup] Error registering unit: {e}")


def initialize_environment():
    """
    Main startup routine:
    1. Detect machine GUID and store in config.json
    2. Register this machine in Supabase 'units' table
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

    # 2. Register the unit in Supabase
    if guid:
        register_unit(guid)

    return True


if __name__ == "__main__":
    print("=" * 50)
    print("  Baccarat Bot - Startup & Registration")
    print("=" * 50)
    initialize_environment()
    print("\nBot registered.")
    print("=" * 50)
