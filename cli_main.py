from bot_logic import Bot
from utils import logger
import time
import sys

def main():
    print("========================================")
    print("   BACCARAT BOT - CLI AUTO-START UNIT   ")
    print("========================================")
    
    try:
        # Initialize Bot with default settings
        # It will load from config.json automatically
        bot = Bot()
        
        logger.log("CLI Bot Started. Entering IDLE mode...", "INFO")
        
        # Initial status push to ensure it shows as 'Idle' on the dashboard
        bot.push_monitoring_update(status="Idle (Ready)")
        
        while True:
            # Sync with Supabase (this pulls remote commands like 'RUN' or 'STOP')
            bot.push_monitoring_update()
            
            if bot.running:
                logger.log("REMOTE START DETECTED! Running bot cycle...", "SUCCESS")
                bot.run_cycle()
            else:
                # Still Idle
                time.sleep(5)
                
    except KeyboardInterrupt:
        logger.log("Bot stopped by user.", "INFO")
    except Exception as e:
        logger.log(f"Fatal CLI Error: {e}", "ERROR")
        time.sleep(10) # Keep window open to see error

if __name__ == "__main__":
    main()
