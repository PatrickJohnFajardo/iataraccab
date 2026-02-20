import os
import time
from datetime import datetime, timedelta

def clean_logs(log_file='automation_log.txt', days_to_keep=3):
    if not os.path.exists(log_file):
        print(f"Log file {log_file} not found.")
        return

    print(f"Cleaning logs older than {days_to_keep} days from {log_file}...")
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    # Read and filter lines
    new_lines = []
    deleted_count = 0
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Try to extract the timestamp [YYYY-MM-DD HH:MM:SS]
                # Example: [2026-02-20 18:03:21] [INFO] message
                if line.startswith('[') and len(line) > 20:
                    try:
                        timestamp_str = line[1:20]
                        log_date = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                        
                        if log_date >= cutoff_date:
                            new_lines.append(line)
                        else:
                            deleted_count += 1
                    except ValueError:
                        # If we can't parse the timestamp, keep the line (it might be a continuation or start line)
                        new_lines.append(line)
                else:
                    new_lines.append(line)
                    
        # Write back the kept lines
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
        print(f"Cleanup complete. Removed {deleted_count} old log entries.")
        
    except Exception as e:
        print(f"Error during log cleanup: {e}")

if __name__ == "__main__":
    clean_logs()
