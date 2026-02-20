import logging
import time
import os
import subprocess
import uuid
from datetime import datetime, timedelta
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
        else:
            # Clean old logs on startup
            self.cleanup_old_logs(days_to_keep=3)
    
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

    def cleanup_old_logs(self, days_to_keep=3):
        """Removes log entries older than the specified number of days."""
        if not os.path.exists(self.log_file):
            return

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        new_lines = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('[') and len(line) > 20:
                        try:
                            timestamp_str = line[1:20]
                            log_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            if log_date >= cutoff_date:
                                new_lines.append(line)
                        except ValueError:
                            new_lines.append(line)
                    else:
                        new_lines.append(line)
            
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
        except Exception as e:
            # We don't want to fail the main app if cleanup fails
            print(f"Log cleanup failed: {e}")

def get_hwid():
    """Generates a unique hardware ID for the current machine."""
    try:
        # Try to get motherboard UUID on Windows
        if os.name == 'nt':
            cmd = 'wmic csproduct get uuid'
            output = subprocess.check_output(cmd, shell=True).decode().split('\n')
            if len(output) > 1:
                uuid_out = output[1].strip()
                if uuid_out and uuid_out != "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF":
                    return uuid_out
    except Exception:
        pass
    
    # Fallback to MAC address
    return str(uuid.getnode())

# Global logger instance
logger = Logger()
