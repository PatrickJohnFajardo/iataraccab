import pyautogui
import pytesseract
import json
import time
import os
import random
import numpy as np
from PIL import Image, ImageOps
import requests
import math
from utils import logger, get_hwid

# Configuration for Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Global PyAutoGUI speed settings
pyautogui.PAUSE = 0.02 # Minimal delay between actions
pyautogui.FAILSAFE = True

class Bot:
    def __init__(self, config_file='config.json', pattern_string='B', base_bet=10, reset_on_cycle=True, target_percentage=None, max_level=10, strategy="Standard", on_settings_sync=None):
        self.config_file = config_file
        self.config = self.load_config()
        self.on_settings_sync = on_settings_sync
        self.running = False
        self.base_bet = base_bet
        self.current_bet = self.base_bet
        self.last_result = None 
        self.target_percentage = target_percentage
        self.starting_balance = None
        self.target_balance = None
        self.max_level = max_level
        self.strategy = strategy
        self.first_run = True 
        self.start_time = time.time()
        self.last_sync_time = 0
        
        # Strategy Multipliers (Transitions from Level 1 up to Level 10)
        self.strategies = {
            "Standard": [2] * 20,
            "Tank":    [2, 2, 2, 2, 2, 3, 2, 3, 2],
            "Sweeper": [3, 3, 3, 2, 2, 2, 2, 2, 2, 2],
            "Burst":   [1.6667, 1.8, 1.926]
        }
        self.strategy = strategy
        self.banker_density = self.calculate_banker_density(pattern_string)
        self.target_duration = 0 # Target seconds from DB
        
        self.pattern = pattern_string.upper().replace("-", "").replace(" ", "")
        if not self.pattern or any(c not in 'PBT' for c in self.pattern):
            logger.log(f"Invalid Pattern '{self.pattern}'! Defaulting to 'B'.", "WARNING")
            self.pattern = 'B'
            
        self.pattern_index = 0
        self.reset_on_cycle = reset_on_cycle
        self.last_end_balance = None  # Tracks balance for continuity
        self.current_bet_start_balance = None # Balance captured right before placing a bet
        
        logger.log(f"Bot Initialized. Pattern: {self.pattern} | Strategy: {self.strategy}", "INFO")

        # Monitoring Settings
        self.sb_config = self.config.get('supabase', {})
        self.martingale_level = 0
        
        # Handle Automatic PC Naming
        self.handle_pc_naming()
        
        if self.sb_url and self.sb_key:
            self.push_monitoring_update(status="Starting")
            
    def load_config(self):
        if not os.path.exists(self.config_file):
            logger.log("Config file not found!", "ERROR")
            raise FileNotFoundError("Config file not found.")
        with open(self.config_file, 'r') as f:
            return json.load(f)

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.log("Configuration saved.", "DEBUG")
        except Exception as e:
            logger.log(f"Failed to save config: {e}", "ERROR")

    def handle_pc_naming(self):
        """Automatically detects new computers and assigns a sequential name (PC-1, PC-2, etc.)"""
        self.sb_config = self.config.get('supabase', {})
        self.pc_name = self.sb_config.get('pc_name', 'Unknown-PC')
        self.sb_url = self.sb_config.get('url')
        self.sb_key = self.sb_config.get('key')
        
        current_hwid = get_hwid()
        stored_hwid = self.sb_config.get('hardware_id')
        
        # If hardware matches and we already have a assigned name, we are good
        if stored_hwid == current_hwid and self.pc_name not in ["Unknown-PC", "PC-NEW"]:
            logger.log(f"Hardware recognized: {self.pc_name}", "INFO")
            return

        # If we reach here, it's either a new computer, or the first time this logic runs
        logger.log("New computer or uninitialized PC detected. Checking available names...", "INFO")
        
        if not self.sb_url or not self.sb_key:
            logger.log("Supabase credentials missing, skipping auto-naming.", "DEBUG")
            return

        # Get existing PC names from Supabase to find the next available index
        try:
            url = f"{self.sb_url}/rest/v1/bot_monitoring?select=pc_name"
            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}"
            }
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                existing_names = [item['pc_name'] for item in response.json()]
                
                # Find the next available index for "PC-X" pattern
                max_idx = 0
                import re
                for name in existing_names:
                    match = re.match(r'PC-(\d+)', name)
                    if match:
                        idx = int(match.group(1))
                        if idx > max_idx:
                            max_idx = idx
                
                new_idx = max_idx + 1
                self.pc_name = f"PC-{new_idx}"
                logger.log(f"Detected new computer. Assigned name: {self.pc_name}", "SUCCESS")
                
                # Update config and save
                if 'supabase' not in self.config:
                    self.config['supabase'] = {}
                self.config['supabase']['pc_name'] = self.pc_name
                self.config['supabase']['hardware_id'] = current_hwid
                self.save_config()
            else:
                # Fallback if query fails
                if self.pc_name in ["Unknown-PC", "PC-NEW"]:
                    import random
                    self.pc_name = f"PC-{random.randint(100, 999)}"
                    logger.log(f"Could not reach Supabase. Assigned temporary name: {self.pc_name}", "WARNING")
        except Exception as e:
            logger.log(f"Auto-naming error: {e}", "DEBUG")
            if self.pc_name in ["Unknown-PC", "PC-NEW"]:
                import random
                self.pc_name = f"PC-{random.randint(100, 999)}"

    def push_monitoring_update(self, status=None):
        if not self.sb_url or not self.sb_key or "YOUR_SUPABASE_KEY" in self.sb_key:
            return

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation"
        }
        
        balance = self.get_current_balance()
        
        if balance is not None and balance < 10:
            effective_status = "Burned"
        elif status:
            effective_status = status
        else:
            effective_status = "Running" if self.running else "Stopped"
        
        elapsed_seconds = int(time.time() - self.start_time)
        
        # Mapping to your Supabase 'bot_monitoring' schema
        # We only push status information to avoid overwriting settings set via the website
        payload = {
            "pc_name": self.pc_name,
            "status": effective_status,
            "balance": balance if balance is not None else 0
        }

        try:
            # Use on_conflict query parameter for upsert
            url = f"{self.sb_url}/rest/v1/bot_monitoring?on_conflict=pc_name"
            
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            self.last_sync_time = time.time()
            
            if response.status_code in [200, 201]:
                data = response.json()
                if data and len(data) > 0:
                    self.sync_remote_settings(data[0])
            else:
                logger.log(f"Supabase Sync Failed: {response.status_code}", "DEBUG")
        except Exception as e:
            logger.log(f"Monitoring error: {e}", "DEBUG")

    def calculate_banker_density(self, pattern):
        if not pattern: return 0
        pattern = pattern.upper()
        return pattern.count('B') / len(pattern)

    def push_play_history(self, start_bal, end_bal, level, bet_size):
        """Logs the outcome to 'play_history' table."""
        if not self.sb_url or not self.sb_key:
            return

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "pc_name": self.pc_name,
            "start_balance": start_bal if start_bal is not None else 0,
            "end_balance": end_bal if end_bal is not None else 0, # Removed int() casting for decimal reporting
            "level": level,
            "bet_size": int(bet_size)
        }

        try:
            url = f"{self.sb_url}/rest/v1/play_history"
            requests.post(url, headers=headers, json=payload, timeout=5)
        except Exception as e:
            logger.log(f"History log error: {e}", "DEBUG")

    def apply_constraints(self):
        """Enforces safety rules defined by the system/UI."""
        # 1. Bet Size vs Max Level Mapping
        # 10 -> 14, 50 -> 12, 100 -> 11, 200 -> 10
        bet_limits = {200: 10, 100: 11, 50: 12, 10: 14}
        
        # Determine strict limit based on base_bet
        strict_limit = 14 # Default safe maximum
        for trigger_bet, limit in sorted(bet_limits.items(), reverse=True):
            if self.base_bet >= trigger_bet:
                strict_limit = limit
                break
        
        if self.max_level > strict_limit:
            logger.log(f"Max Level {self.max_level} exceeds safety limit for Bet {self.base_bet}. Clamping to {strict_limit}.", "WARNING")
            self.max_level = strict_limit

        # 2. Level vs Strategy Constraints
        # Sweeper/Burst only work on low levels (< 4)
        if self.max_level >= 4 and self.strategy in ["Sweeper", "Burst"]:
            logger.log(f"Strategy {self.strategy} is not allowed for Level {self.max_level}. Reverting to Standard.", "WARNING")
            self.strategy = "Standard"

    def sync_remote_settings(self, remote_data):
        # 1. Pattern Sync
        new_pattern = remote_data.get('pattern')
        if new_pattern and new_pattern.upper() != self.pattern:
            self.pattern = new_pattern.upper().replace("-", "").replace(" ", "")
            self.pattern_index = 0
            self.banker_density = self.calculate_banker_density(self.pattern)

        # 2. Bet (Base Bet) Sync
        new_bet = remote_data.get('bet')
        if new_bet is not None:
            new_bet = int(new_bet)
            if new_bet < 10: # Min Bet Guard
                new_bet = 10
            
            if new_bet != self.base_bet:
                self.base_bet = new_bet
                self.current_bet = self.base_bet
                self.martingale_level = 1

        # 3. Strategy Sync
        new_strategy = remote_data.get('strategy')
        if new_strategy and new_strategy in self.strategies and new_strategy != self.strategy:
            self.strategy = new_strategy

        # 4. Max Level Sync (Read from 'level' column)
        new_max_level = remote_data.get('level')
        if new_max_level is not None:
            try:
                new_max_level = int(new_max_level)
                if new_max_level != self.max_level:
                    self.max_level = new_max_level
                    logger.log(f"Synced Max Level: {self.max_level}", "INFO")
            except ValueError:
                pass

        # 5. Target Profit Sync
        new_profit_pct = remote_data.get('target_profit')
        if new_profit_pct is not None and float(new_profit_pct) != self.target_percentage:
            self.target_percentage = float(new_profit_pct)
            if self.starting_balance:
                self.target_balance = self.starting_balance + (self.target_percentage / 100 * self.starting_balance)

        # 5. Duration Limit Sync (Target minutes from DB)
        raw_duration = remote_data.get('duration')
        # Treat None, empty string, or 0 as "Unlimited"
        if raw_duration in [None, "", 0, "0"]:
            self.target_duration = 0
        else:
            try:
                self.target_duration = int(raw_duration) * 60
            except ValueError:
                self.target_duration = 0 # Safety fallback

        # 6. Command Sync
        remote_cmd = remote_data.get('command')
        if isinstance(remote_cmd, bool):
            should_run = remote_cmd
        else:
            should_run = str(remote_cmd).lower() in ['true', 'start', 'run', '1']
                
        if not should_run and self.running:
            self.running = False
            logger.log("Stopping bot (Remote Command)...", "INFO")
        elif should_run and not self.running:
            self.start_time = time.time() # Reset clock on session start
            self.running = True
            logger.log("Starting bot (Remote Command)...", "INFO")

        # 7. Final validation of synced cross-settings
        self.apply_constraints()

        # Notify UI if callback exists
        if self.on_settings_sync:
            self.on_settings_sync(remote_data)

    def capture_status_region(self, region_key):
        region_config = self.config.get(region_key)
        if not region_config: raise ValueError(f"Region {region_key} missing")
        region = (int(region_config['x']), int(region_config['y']), int(region_config['width']), int(region_config['height']))
        return pyautogui.screenshot(region=region)

    def check_tie_region(self):
        try:
            img = self.capture_status_region('status_region_tie')
            np_img = np.array(img)
            avg_color = np_img.mean(axis=(0, 1))
            r, g, b = avg_color
            
            # Robust Check: distinctly green OR OCR match
            is_green = (g > r + 15) and (g > b + 15) and (g > 70)
            
            text = pytesseract.image_to_string(img.convert('L').point(lambda p: p > 150 and 255)).strip().lower()
            if "tie" in text or "t1e" in text or is_green: 
                return True
        except: pass
        return False

    def analyze_state(self):
        if self.check_tie_region(): return "TIE"
        image = self.capture_status_region('status_region_main')
        text = pytesseract.image_to_string(image.convert('L')).strip().lower()
        if "banker" in text: return "BANKER"
        if "player" in text: return "PLAYER"
        if "win" in text or "nanalo" in text: return "GENERIC_WIN"
        return None

    def get_current_balance(self):
        if 'status_region_balance' not in self.config: return None
        try:
            image = self.capture_status_region('status_region_balance')
            text = pytesseract.image_to_string(image.convert('L')).strip()
            clean_text = "".join(c for c in text if c.isdigit() or c == '.')
            if clean_text: return float(clean_text)
        except: pass
        return None

    def wait_for_result_to_clear(self):
        # Human-like delay: Random 3-5 seconds to let the result settle
        delay = random.uniform(3.0, 5.0)
        time.sleep(delay)
        return True

    def drift_detection(self):
        target = self.config['target_a']
        current_color = pyautogui.pixel(int(target['x']), int(target['y']))
        baseline = target.get('color')
        if baseline:
            diff = sum(abs(c - b) for c, b in zip(current_color, baseline))
            return diff < 100
        return True

    def select_chips(self, amount):
        if not self.config.get('chips'): return {}
        available_chips = sorted([int(k) for k in self.config['chips'].keys()], reverse=True)
        selected = {}
        remaining = amount
        for chip in available_chips:
            if remaining >= chip:
                count = remaining // chip
                remaining = remaining % chip
                selected[chip] = count
        return selected

    def execute_bet(self, target_char):
        if target_char == 'T':
            lookup = self.pattern_index - 1
            resolved_side = None
            while lookup >= 0:
                if self.pattern[lookup] in 'PB':
                    resolved_side = self.pattern[lookup]
                    break
                lookup -= 1
            target_char = resolved_side if resolved_side else 'B'

        # Capture balance before betting for accurate history
        current_bal = self.get_current_balance()
        if current_bal is not None:
            self.current_bet_start_balance = current_bal
        elif self.last_end_balance is not None:
            self.current_bet_start_balance = self.last_end_balance
            
        # Humanized pre-bet delay: Ensure window is open and looks natural
        time.sleep(random.uniform(0.8, 1.5))
        
        target_key = 'target_a' if target_char == 'B' else 'target_b'
        target = self.config[target_key]
        chips_to_click = self.select_chips(self.current_bet)
        
        for chip_val, count in chips_to_click.items():
            chip_config = self.config['chips'].get(str(chip_val))
            if chip_config:
                # Randomize chip click coordinates (±3 pixels)
                chip_x = chip_config['x'] + random.randint(-3, 3)
                chip_y = chip_config['y'] + random.randint(-3, 3)
                # Randomize movement speed (0.1s to 0.3s)
                move_dur = random.uniform(0.1, 0.3)
                
                pyautogui.click(chip_x, chip_y, duration=move_dur)
                time.sleep(random.uniform(0.05, 0.15))
                
                # Randomize target click coordinates (±5 pixels)
                target_x = target['x'] + random.randint(-5, 5)
                target_y = target['y'] + random.randint(-5, 5)
                
                # For multiple clicks, add slight intervals
                for _ in range(count):
                    pyautogui.click(x=target_x, y=target_y, duration=random.uniform(0.05, 0.1))
                    time.sleep(random.uniform(0.02, 0.08))
                
                time.sleep(random.uniform(0.05, 0.15))

        self.push_monitoring_update()

    def execute_test_bet(self):
        """Standard $10 bet on Banker for physical testing."""
        target = self.config['target_a'] # Banker
        chip_10 = self.config['chips'].get('10')
        if not chip_10:
            logger.log("Cannot test clicks: Chip 10 not calibrated.", "ERROR")
            return
            
        logger.log("Testing humanized clicks: Chip 10 -> Banker", "INFO")
        
        # Randomize chip click
        cx = chip_10['x'] + random.randint(-3, 3)
        cy = chip_10['y'] + random.randint(-3, 3)
        pyautogui.click(cx, cy, duration=random.uniform(0.15, 0.35))
        
        time.sleep(random.uniform(0.1, 0.3))
        
        # Randomize target click
        tx = target['x'] + random.randint(-5, 5)
        ty = target['y'] + random.randint(-5, 5)
        pyautogui.click(tx, ty, duration=random.uniform(0.15, 0.35))
        
        logger.log(f"Click test complete. Offset applied: ({tx-target['x']}, {ty-target['y']})", "SUCCESS")

    def run_cycle(self):
        self.push_monitoring_update()
        self.drift_detection() 
        
        elapsed_seconds = time.time() - self.start_time

        # 1. CHECK DURATION LIMIT (Whichever comes first skip/stop)
        if self.target_duration > 0 and elapsed_seconds >= self.target_duration:
            logger.log(f"SESSION STOP: Time limit of {int(self.target_duration / 60)}m reached.", "WARNING")
            self.running = False
            return

        # 2. CHECK PROFIT LIMIT
        if self.target_percentage is not None:
            current_bal = self.get_current_balance()
            if self.starting_balance is None and current_bal is not None:
                self.starting_balance = current_bal
                self.target_balance = self.starting_balance + (self.target_percentage / 100 * self.starting_balance)
                self.first_run = False

            if current_bal is not None and self.target_balance is not None:
                if current_bal >= self.target_balance:
                    logger.log(f"GOAL REACHED! Profit target (>{self.target_percentage}%) hit.", "SUCCESS")
                    self.running = False
                    return
        
        current_target_char = self.pattern[self.pattern_index] 
        if current_target_char == 'T':
            lookup = self.pattern_index - 1
            resolved_side = None
            while lookup >= 0:
                if self.pattern[lookup] in 'PB':
                    resolved_side = self.pattern[lookup]
                    break
                lookup -= 1
            current_target_char = resolved_side if resolved_side else 'B'
        
        outcome = self.analyze_state()
        if outcome:
            start_bal = self.get_current_balance()
            logger.log(f"Outcome: {outcome}", "SUCCESS")
            self.wait_for_result_to_clear()
            
            current_target_name = "BANKER" if current_target_char == 'B' else "PLAYER"
            actual_result = "LOSS"
            if outcome == "TIE": actual_result = "PUSH"
            elif outcome == current_target_name or outcome == "GENERIC_WIN": actual_result = "WIN"
                
            logger.log(f"Result determined: {actual_result}", "INFO")

            prev_bet = self.current_bet
            prev_level = self.martingale_level

            # --- SESSION START HANDLING ---
            if self.last_result is None:
                logger.log("First hand detected (Baseline). Ignoring result for stats/betting.", "WARNING")
                self.current_bet = self.base_bet
                self.martingale_level = 0
                self.pattern_index = 0
                self.last_result = "SIGHTED" # Custom state to mark baseline is done
                self.last_end_balance = self.get_current_balance()
                self.execute_bet(self.pattern[self.pattern_index])
                return

            # --- STANDARD LOGIC ---
            if actual_result == "WIN":
                self.current_bet = self.base_bet
                self.martingale_level = 0
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern)
            elif actual_result == "PUSH":
                logger.log("Tie detected: Keeping same pattern index for next bet.", "INFO")
                # pattern_index is NOT incremented, so the next bet is on the same side.
            elif actual_result == "LOSS":
                # Smart Banker Multiplier Override (2.11x)
                # Only apply if currently betting on Banker AND the pattern contains consecutive Bankers (e.g. "BB")
                current_target_char = self.pattern[self.pattern_index]
                has_consecutive_bankers = "BB" in self.pattern
                
                if current_target_char == 'B' and has_consecutive_bankers:
                    self.current_bet = math.ceil(self.current_bet * 2.11 / 10) * 10
                    logger.log(f"Banker Multiplier (2.11x) applied (Pattern contains 'BB'). Rounding up to nearest 10.", "INFO")
                else:
                    multipliers = self.strategies.get(self.strategy, self.strategies["Standard"])
                    if self.martingale_level < len(multipliers):
                        multiplier = multipliers[self.martingale_level]
                        self.current_bet = int(self.current_bet * multiplier)
                    else:
                        self.current_bet *= 2

                self.martingale_level += 1
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern)

                if self.martingale_level > self.max_level:
                    self.running = False
                    return

            self.last_result = actual_result
            
            # Capture end balance AFTER result clears (payout has settled)
            end_bal = self.get_current_balance()
            
            # Use the balance from BEFORE the bet for the start of history
            history_start = self.current_bet_start_balance if self.current_bet_start_balance is not None else self.last_end_balance
            
            if actual_result != "PUSH":
                self.push_play_history(history_start, end_bal, prev_level, prev_bet)
                
            self.last_end_balance = end_bal
            # Important: Reset round start balance after logging
            self.current_bet_start_balance = None 

            self.execute_bet(self.pattern[self.pattern_index])
            # Post-bet idle delay
            time.sleep(random.uniform(1.5, 3.0))
        else:
            if time.time() - self.last_sync_time > 5:
                self.push_monitoring_update()
            time.sleep(0.2) # Increased polling frequency (from 1s to 0.2s)

    def start(self):
        self.running = True
        self.start_time = time.time()
        
        # Initial balance capture
        self.last_end_balance = self.get_current_balance()
        
        logger.log("Bot session active. Listening for commands...", "INFO")
        try:
            while True:
                if self.running:
                    self.run_cycle()
                else:
                    # Idle loop: check for remote commands periodically
                    if time.time() - self.last_sync_time > 5:
                        self.push_monitoring_update()
                    time.sleep(1)
        except KeyboardInterrupt:
            logger.log("Bot stopped manually.", "INFO")
