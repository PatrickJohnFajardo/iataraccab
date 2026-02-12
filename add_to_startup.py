import os
import sys
import winreg as reg

def add_to_startup():
    # Path to the batch file
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "start_headless.bat")
    
    # Name of the entry in the registry
    app_name = "BaccaratBotHeadless"
    
    # Open the registry key for current user startup
    key = reg.HKEY_CURRENT_USER
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    try:
        registry_key = reg.OpenKey(key, key_path, 0, reg.KEY_WRITE)
        reg.SetValueEx(registry_key, app_name, 0, reg.REG_SZ, f'"{file_path}"')
        reg.CloseKey(registry_key)
        print(f"Successfully added {app_name} to startup!")
        print(f"Path: {file_path}")
    except Exception as e:
        print(f"Error adding to startup: {e}")

if __name__ == "__main__":
    add_to_startup()
