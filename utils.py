import logging
import time
import os
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

class Logger:
    def __init__(self, log_file='automation_log.txt'):
        self.log_file = log_file
        # Create log file if it doesn't exist
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w') as f:
                f.write(f"Log started at {time.ctime()}\n")
    
    def log(self, message, level="INFO"):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [{level}] {message}"
        
        # Print to console with color
        if level == "INFO":
            print(f"{Fore.CYAN}{formatted_message}{Style.RESET_ALL}")
        elif level == "WARNING":
            print(f"{Fore.YELLOW}{formatted_message}{Style.RESET_ALL}")
        elif level == "ERROR":
            print(f"{Fore.RED}{formatted_message}{Style.RESET_ALL}")
        elif level == "SUCCESS":
            print(f"{Fore.GREEN}{formatted_message}{Style.RESET_ALL}")
        else:
            print(formatted_message)
            
        # Write to file
        with open(self.log_file, 'a') as f:
            f.write(formatted_message + "\n")

# Global logger instance
logger = Logger()
