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

# Strategy name mapping: DB uses lowercase enums, bot uses capitalized internally
STRATEGY_DB_TO_BOT = {"standard": "Standard", "tank": "Tank", "sweeper": "Sweeper", "burst": "Burst"}
STRATEGY_BOT_TO_DB = {v: k for k, v in STRATEGY_DB_TO_BOT.items()}

# Game Mode mapping
MODE_DB_TO_BOT = {"Classic": "Classic Baccarat", "classic": "Classic Baccarat", "Always 8 Baccarat": "Always 8 Baccarat", "Always 8": "Always 8 Baccarat", "always 8": "Always 8 Baccarat"}
MODE_BOT_TO_DB = {"Classic Baccarat": "Classic", "Always 8 Baccarat": "Always 8"}

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
        self.local_mode = False
        self.game_mode = "Classic Baccarat"
        self.betting_mode = "Sequence"
        self.session_lost_amount = 0 # Track accumulated loss for specific recovery modes
        
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
        
        # Handle Bot Identity (find or create bot row in DB)
        self.handle_bot_identity()
        
        if self.sb_url and self.sb_key and self.bot_id:
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

    def handle_bot_identity(self):
        """Finds or creates a bot row in the Supabase 'bot' table."""
        self.sb_config = self.config.get('supabase', {})
        self.bot_id = self.sb_config.get('bot_id', '')
        self.sb_url = self.sb_config.get('url')
        self.sb_key = self.sb_config.get('key')
        
        if not self.sb_url or not self.sb_key:
            logger.log("Supabase credentials missing.", "DEBUG")
            return

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json",
        }
        
        # 1. If we already have a bot_id, verify it exists
        if self.bot_id:
            try:
                url = f"{self.sb_url}/rest/v1/bot?id=eq.{self.bot_id}&select=id"
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code == 200 and resp.json():
                    logger.log(f"Bot identity confirmed: {self.bot_id}", "INFO")
                    return
                else:
                    logger.log(f"Bot ID {self.bot_id} not found in DB. Creating new one...", "WARNING")
                    self.bot_id = ''
            except Exception as e:
                logger.log(f"Bot ID verification error: {e}", "DEBUG")
                return

        # 2. Try to find via GUID → unit → user → bot chain
        current_hwid = get_hwid()
        try:
            # Look up unit by GUID
            url = f"{self.sb_url}/rest/v1/units?guid=eq.{current_hwid}&select=id"
            resp = requests.get(url, headers=headers, timeout=5)
            unit_id = None
            user_id = None
            
            if resp.status_code == 200 and resp.json():
                unit_id = resp.json()[0]['id']
                logger.log(f"Found unit for this machine: {unit_id}", "INFO")
                
                # Look up user_account by unit_id
                url = f"{self.sb_url}/rest/v1/user_account?unit_id=eq.{unit_id}&select=id"
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code == 200 and resp.json():
                    user_id = resp.json()[0]['id']
                    logger.log(f"Found user for this unit: {user_id}", "INFO")
                    
                    # Check if a bot already exists for this user
                    url = f"{self.sb_url}/rest/v1/bot?user_id=eq.{user_id}&select=id"
                    resp = requests.get(url, headers=headers, timeout=5)
                    if resp.status_code == 200 and resp.json():
                        self.bot_id = resp.json()[0]['id']
                        logger.log(f"Found existing bot: {self.bot_id}", "SUCCESS")
                        self._save_bot_id()
                        return
        except Exception as e:
            logger.log(f"GUID chain lookup error: {e}", "DEBUG")

        # 3. No bot found — create one
        try:
            payload = {
                "status": "Starting",
                "bet": self.base_bet,
                "pattern": self.pattern if self.pattern in ['P', 'B', 'PB', 'BP', 'PPPB', 'BBBP'] else 'B',
                "level": self.max_level,
                "target_profit": self.target_percentage or 10.0,
                "command": False,
                "duration": 60,
                "strategy": STRATEGY_BOT_TO_DB.get(self.strategy, "standard"),
                "bot_status": "stop",
                "balance": 0,
                "mode": MODE_BOT_TO_DB.get(self.game_mode, "Classic"),
            }
            # Link to user if we found one
            if user_id:
                payload["user_id"] = user_id
                
            url = f"{self.sb_url}/rest/v1/bot"
            resp = requests.post(
                url,
                headers={**headers, "Prefer": "return=representation"},
                json=payload,
                timeout=5
            )
            if resp.status_code in (200, 201) and resp.json():
                self.bot_id = resp.json()[0]['id']
                logger.log(f"Created new bot in DB: {self.bot_id}", "SUCCESS")
                self._save_bot_id()
            else:
                logger.log(f"Failed to create bot: {resp.status_code} {resp.text}", "ERROR")
        except Exception as e:
            logger.log(f"Bot creation error: {e}", "ERROR")

    def _save_bot_id(self):
        """Persist bot_id to config.json."""
        if 'supabase' not in self.config:
            self.config['supabase'] = {}
        self.config['supabase']['bot_id'] = self.bot_id
        self.config['supabase']['hardware_id'] = get_hwid()
        self.save_config()

    def push_monitoring_update(self, status=None):
        if not self.sb_url or not self.sb_key or not self.bot_id:
            return

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json",
        }
        
        balance = self.get_current_balance()
        
        if balance is not None and balance < 10:
            effective_status = "Burned"
        elif status:
            effective_status = status
        else:
            effective_status = "Running" if self.running else "Stopped"
        
        # Only push status and balance — don't overwrite settings from the website
        payload = {
            "status": effective_status,
            "balance": balance if balance is not None else 0,
        }

        try:
            # PATCH the bot row (use minimal to avoid PostgREST 204-no-body issues)
            url = f"{self.sb_url}/rest/v1/bot?id=eq.{self.bot_id}"
            response = requests.patch(
                url,
                headers={**headers, "Prefer": "return=minimal"},
                json=payload,
                timeout=5
            )
            self.last_sync_time = time.time()
            
            if response.status_code in [200, 204]:
                # Always do a separate GET to pull the latest remote settings
                get_resp = requests.get(
                    f"{self.sb_url}/rest/v1/bot?id=eq.{self.bot_id}&select=*",
                    headers=headers,
                    timeout=5
                )
                if get_resp.status_code == 200:
                    data = get_resp.json()
                    if data:
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
        if not self.sb_url or not self.sb_key or not self.bot_id:
            return

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json"
        }

        s_bal = start_bal if start_bal is not None else 0
        e_bal = end_bal if end_bal is not None else 0
        pnl = e_bal - s_bal

        payload = {
            "bot_id": self.bot_id,
            "start_balance": s_bal,
            "end_balance": e_bal,
            "level": str(level),
            "pnl": pnl,
        }

        try:
            url = f"{self.sb_url}/rest/v1/play_history"
            requests.post(url, headers=headers, json=payload, timeout=5)
        except Exception as e:
            logger.log(f"History log error: {e}", "DEBUG")

    def apply_constraints(self):
        """Enforces safety rules defined by the system/UI."""
        # 1. Bet Size vs Max Level Mapping
        bet_limits = {200: 10, 100: 11, 50: 12, 10: 14}
        
        strict_limit = 14
        for trigger_bet, limit in sorted(bet_limits.items(), reverse=True):
            if self.base_bet >= trigger_bet:
                strict_limit = limit
                break
        
        if self.max_level > strict_limit:
            logger.log(f"Max Level {self.max_level} exceeds safety limit for Bet {self.base_bet}. Clamping to {strict_limit}.", "WARNING")
            self.max_level = strict_limit

        # 2. Level vs Strategy Constraints
        if self.max_level >= 4 and self.strategy in ["Sweeper", "Burst"]:
            logger.log(f"Strategy {self.strategy} is not allowed for Level {self.max_level}. Reverting to Standard.", "WARNING")
            self.strategy = "Standard"

    def sync_remote_settings(self, remote_data):
        if self.local_mode:
            # Still update status/balance to DB, but don't accept changes FROM DB
            return

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
            if new_bet < 10:
                new_bet = 10
            
            if new_bet != self.base_bet:
                self.base_bet = new_bet
                self.current_bet = self.base_bet
                self.martingale_level = 1

        # 3. Strategy Sync (DB stores lowercase: standard, sweeper, etc.)
        new_strategy_db = remote_data.get('strategy')
        if new_strategy_db:
            new_strategy = STRATEGY_DB_TO_BOT.get(new_strategy_db, new_strategy_db)
            if new_strategy in self.strategies and new_strategy != self.strategy:
                self.strategy = new_strategy

        # 4. Max Level Sync
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
        if new_profit_pct is not None:
            try:
                pct = float(new_profit_pct)
                if pct != self.target_percentage:
                    self.target_percentage = pct
                    if self.starting_balance:
                        self.target_balance = self.starting_balance + (self.target_percentage / 100 * self.starting_balance)
            except (ValueError, TypeError):
                pass

        # 6. Duration Limit Sync (minutes from DB)
        raw_duration = remote_data.get('duration')
        if raw_duration in [None, "", 0, "0"]:
            self.target_duration = 0
        else:
            try:
                self.target_duration = int(raw_duration) * 60
            except ValueError:
                self.target_duration = 0

        # 7. Game Mode Sync
        raw_mode = remote_data.get('mode')
        if raw_mode:
            new_game_mode = MODE_DB_TO_BOT.get(raw_mode, raw_mode)
            if new_game_mode in ["Classic Baccarat", "Always 8 Baccarat"]:
                if new_game_mode != self.game_mode:
                    self.game_mode = new_game_mode
                    logger.log(f"Synced Game Mode: {self.game_mode}", "INFO")

        # 8. Bot Status Sync (enum: 'run' or 'stop')
        bot_status = remote_data.get('bot_status')
        if bot_status:
            should_run = (bot_status == 'run')
        else:
            # Fallback to command field
            remote_cmd = remote_data.get('command')
            if isinstance(remote_cmd, bool):
                should_run = remote_cmd
            else:
                should_run = str(remote_cmd).lower() in ['true', 'start', 'run', '1']
                
        if not should_run and self.running:
            self.running = False
            logger.log("Stopping bot (Remote Command)...", "INFO")
        elif should_run and not self.running:
            self.start_time = time.time()
            self.running = True
            logger.log("Starting bot (Remote Command)...", "INFO")

        # 10. Final validation
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
            
        # Humanized pre-bet delay
        time.sleep(random.uniform(0.8, 1.5))
        
        target_key = 'target_a' if target_char == 'B' else 'target_b'
        target = self.config[target_key]
        chips_to_click = self.select_chips(self.current_bet)
        
        for chip_val, count in chips_to_click.items():
            chip_config = self.config['chips'].get(str(chip_val))
            if chip_config:
                chip_x = chip_config['x'] + random.randint(-3, 3)
                chip_y = chip_config['y'] + random.randint(-3, 3)
                move_dur = random.uniform(0.1, 0.3)
                
                pyautogui.click(chip_x, chip_y, duration=move_dur)
                time.sleep(random.uniform(0.05, 0.15))
                
                target_x = target['x'] + random.randint(-5, 5)
                target_y = target['y'] + random.randint(-5, 5)
                
                for _ in range(count):
                    pyautogui.click(x=target_x, y=target_y, duration=random.uniform(0.05, 0.1))
                    time.sleep(random.uniform(0.02, 0.08))
                
                time.sleep(random.uniform(0.05, 0.15))

        self.push_monitoring_update()

    def execute_test_bet(self):
        """Standard $10 bet on Banker for physical testing."""
        target = self.config['target_a']
        chip_10 = self.config['chips'].get('10')
        if not chip_10:
            logger.log("Cannot test clicks: Chip 10 not calibrated.", "ERROR")
            return
            
        logger.log("Testing humanized clicks: Chip 10 -> Banker", "INFO")
        
        cx = chip_10['x'] + random.randint(-3, 3)
        cy = chip_10['y'] + random.randint(-3, 3)
        pyautogui.click(cx, cy, duration=random.uniform(0.15, 0.35))
        
        time.sleep(random.uniform(0.1, 0.3))
        
        tx = target['x'] + random.randint(-5, 5)
        ty = target['y'] + random.randint(-5, 5)
        pyautogui.click(tx, ty, duration=random.uniform(0.15, 0.35))
        
        logger.log(f"Click test complete. Offset applied: ({tx-target['x']}, {ty-target['y']})", "SUCCESS")

    def run_cycle(self):
        self.push_monitoring_update()
        self.drift_detection() 
        
        current_bal = self.get_current_balance()

        # --- INITIALIZE TARGETS IF NEW SESSION ---
        if self.starting_balance is None and current_bal is not None:
            self.starting_balance = current_bal
            if self.target_percentage:
                self.target_balance = self.starting_balance + (self.target_percentage / 100 * self.starting_balance)
                logger.log(f"Session Start Balance: {self.starting_balance} | Goal: {self.target_balance}", "INFO")

        # 1. OPTIONAL: Periodic Sync if idle
        if not self.analyze_state():
            if time.time() - self.last_sync_time > 5:
                self.push_monitoring_update()
            time.sleep(0.2)
            # We still check limits here so bot can stop while waiting for a hand if time runs out
            elapsed_seconds = time.time() - self.start_time
            if self.target_duration > 0 and elapsed_seconds >= self.target_duration:
                logger.log(f"SESSION STOP: Time limit reached.", "WARNING")
                self.stop_remotely("Time Limit")
                return
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
                self.last_result = "SIGHTED"
                self.last_end_balance = self.get_current_balance()
                self.execute_bet(self.pattern[self.pattern_index])
                return

            # --- STANDARD LOGIC ---
            if actual_result == "WIN":
                self.current_bet = self.base_bet
                self.martingale_level = 0
                self.session_lost_amount = 0 # Reset recovery tracking
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern)
            elif actual_result == "PUSH":
                logger.log("Tie detected: Keeping same pattern index for next bet.", "INFO")
            elif actual_result == "LOSS":
                if self.game_mode == "Always 8 Baccarat":
                    self.session_lost_amount += prev_bet
                    # Formula: ((total lost) / 0.62) + 50
                    raw_bet = (self.session_lost_amount / 0.62) + 50
                    self.current_bet = math.ceil(raw_bet / 10) * 10
                    logger.log(f"Always 8 Logic: Total Lost={self.session_lost_amount}, Next Bet={self.current_bet}", "INFO")
                else:
                    # Smart Banker Multiplier Override (2.11x)
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
            
            end_bal = self.get_current_balance()
            history_start = self.current_bet_start_balance if self.current_bet_start_balance is not None else self.last_end_balance
            
            if actual_result != "PUSH":
                self.push_play_history(history_start, end_bal, prev_level, prev_bet)
                
            self.last_end_balance = end_bal
            self.current_bet_start_balance = None 

            # --- AFTER LOGGING: CHECK LIMITS ---
            elapsed_seconds = time.time() - self.start_time
            if self.target_duration > 0 and elapsed_seconds >= self.target_duration:
                logger.log(f"SESSION STOP: Time limit reached.", "WARNING")
                self.stop_remotely("Time Limit")
                return

            if self.target_percentage is not None:
                current_bal = self.get_current_balance()
                if current_bal is not None and self.target_balance is not None:
                    if current_bal >= self.target_balance:
                        logger.log(f"GOAL REACHED! Profit target (>{self.target_percentage}%) hit.", "SUCCESS")
                        self.stop_remotely("Goal Reached")
                        return

            # --- PLACING NEXT BET ---
            self.execute_bet(self.pattern[self.pattern_index])
            time.sleep(random.uniform(1.5, 3.0))
        else:
            time.sleep(0.1)

    def stop_remotely(self, reason_status):
        """Stops the bot and updates the database status so it doesn't auto-restart."""
        self.running = False
        self.push_monitoring_update(status=reason_status)
        
        # Also set bot_status to 'stop' in DB so the website toggle flips to off
        if self.sb_url and self.sb_key and self.bot_id:
            headers = {
                "apikey": self.sb_key,
                "Authorization": f"Bearer {self.sb_key}",
                "Content-Type": "application/json",
            }
            try:
                url = f"{self.sb_url}/rest/v1/bot?id=eq.{self.bot_id}"
                requests.patch(url, headers=headers, json={"bot_status": "stop"}, timeout=5)
            except:
                pass


    def start(self):
        self.running = True
        self.start_time = time.time()
        
        self.last_end_balance = self.get_current_balance()
        
        logger.log("Bot session active. Listening for commands...", "INFO")
        try:
            while True:
                if self.running:
                    self.run_cycle()
                else:
                    if time.time() - self.last_sync_time > 5:
                        self.push_monitoring_update()
                    time.sleep(1)
        except KeyboardInterrupt:
            logger.log("Bot stopped manually.", "INFO")
