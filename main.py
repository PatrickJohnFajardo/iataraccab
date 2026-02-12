import tkinter as tk
import sys
import json
from gui_app import BaccaratGUI
from bot_logic import Bot
from utils import logger

def main():
    if "--headless" in sys.argv:
        logger.log("Starting in HEADLESS mode...", "INFO")
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            
            # Initialize bot with default settings (or loaded from config if you prefer)
            # Headless mode will rely heavily on Supabase remote commands to change patterns/bets
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

