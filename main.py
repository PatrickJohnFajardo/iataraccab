import tkinter as tk
import sys
import json
import atexit
from gui_app import BaccaratGUI
from bot_logic import Bot
from utils import logger
from startup import initialize_environment, stop_ngrok

def main():
    # ── Run Startup & Registration ──
    logger.log("Running startup registration...", "INFO")
    ngrok_url = initialize_environment()
    if ngrok_url:
        logger.log(f"ngrok tunnel active: {ngrok_url}", "SUCCESS")
    else:
        logger.log("No ngrok tunnel (bot registered without it).", "INFO")

    # Ensure ngrok is cleaned up on exit
    atexit.register(stop_ngrok)

    if "--headless" in sys.argv:
        logger.log("Starting in HEADLESS mode...", "INFO")
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            
            bot = Bot(
                base_bet=10, 
                pattern_string="B", 
                reset_on_cycle=True
            )
            bot.start()
        except Exception as e:
            logger.log(f"Headless Mode Error: {e}", "ERROR")
            sys.exit(1)
    else:
        root = tk.Tk()
        app = BaccaratGUI(root)
        root.mainloop()

if __name__ == "__main__":
    main()

