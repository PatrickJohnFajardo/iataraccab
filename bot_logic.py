import pyautogui
import pytesseract
import json
import time
import os
import numpy as np
from PIL import Image, ImageOps
import requests
from utils import logger

# Configuration for Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class Bot:
    def __init__(self, config_file='config.json', pattern_string='B', base_bet=10, reset_on_cycle=True, target_percentage=None, max_level=10, strategy="Standard"):
        self.config_file = config_file
        self.config = self.load_config()
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
        self.last_sync_time = 0
        
        # Strategy Multipliers (Multipliers for the NEXT level based on current level)
        # Level 1 is base_bet. Level 2 = L1 * multi[0], Level 3 = L2 * multi[1], etc.
        self.strategies = {
            "Standard": [2] * 20, # 2x all the way
            "Tank":    [2, 2, 2, 2, 2, 3, 2, 3, 2, 2],
            "Sweeper": [3, 3, 3, 3, 2, 2, 2, 2, 2, 2]
        }
        
        # v2 Pattern Strategy
        self.pattern = pattern_string.upper().replace("-", "").replace(" ", "")
        
        if not self.pattern or any(c not in 'PBT' for c in self.pattern):
            logger.log(f"Invalid Pattern '{self.pattern}'! Defaulting to 'B'.", "WARNING")
            self.pattern = 'B'
            
        self.pattern_index = 0
        self.reset_on_cycle = reset_on_cycle
        
        mode_str = "Cycle-Reset" if self.reset_on_cycle else "Infinite Martingale"
        logger.log(f"Bot Initialized. Pattern: {self.pattern} | Strategy: {self.strategy} | Target: {self.target_percentage}%", "INFO")

        # Monitoring Settings
        self.sb_config = self.config.get('supabase', {})
        self.pc_name = self.sb_config.get('pc_name', 'Unknown-PC')
        self.sb_url = self.sb_config.get('url')
        self.sb_key = self.sb_config.get('key')
        self.martingale_level = 1
        
        if self.sb_url and self.sb_key:
            self.push_monitoring_update(status="Starting")
            
    def load_config(self):
        if not os.path.exists(self.config_file):
            logger.log("Config file not found! Run calibration first.", "ERROR")
            raise FileNotFoundError("Config file not found.")
        with open(self.config_file, 'r') as f:
            return json.load(f)

    def push_monitoring_update(self, status=None, bet_side=None, bet_amount=None):
        if not self.sb_url or not self.sb_key:
            return

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        effective_status = status if status else ("Running" if self.running else "Stopped")
        balance = self.get_current_balance()
        
        payload = {
            "pc_name": self.pc_name,
            "status": effective_status,
            "balance": balance if balance is not None else 0,
            "level": self.martingale_level,
            "strategy": self.strategy
        }

        try:
            url = f"{self.sb_url}/rest/v1/bot_monitoring?on_conflict=pc_name"
            upsert_headers = {
                **headers, 
                "Prefer": "resolution=merge-duplicates,return=representation"
            }
            
            response = requests.post(url, headers=upsert_headers, json=payload, timeout=5)
            self.last_sync_time = time.time()
            
            if response.status_code in [200, 201]:
                data = response.json()
                if data and len(data) > 0:
                    self.sync_remote_settings(data[0])
            else:
                logger.log(f"Supabase Sync Failed: {response.text}", "DEBUG")
        except Exception as e:
            logger.log(f"Monitoring sync error: {e}", "DEBUG")

    def sync_remote_settings(self, remote_data):
        # 1. Pattern Sync
        new_pattern = remote_data.get('pattern')
        if new_pattern and new_pattern.upper() != self.pattern:
            logger.log(f"REMOTE UPDATE: Pattern changed from {self.pattern} -> {new_pattern.upper()}", "WARNING")
            self.pattern = new_pattern.upper().replace("-", "").replace(" ", "")
            self.pattern_index = 0

        # 2. Level (Base Bet) Sync
        new_level = remote_data.get('level')
        if new_level is not None and int(new_level) != self.base_bet:
            logger.log(f"REMOTE UPDATE: Base Bet changed from {self.base_bet} -> {new_level}", "WARNING")
            self.base_bet = int(new_level)
            self.current_bet = self.base_bet
            self.martingale_level = 1

        # 3. Strategy Sync
        new_strategy = remote_data.get('strategy')
        if new_strategy and new_strategy in self.strategies and new_strategy != self.strategy:
            logger.log(f"REMOTE UPDATE: Strategy changed from {self.strategy} -> {new_strategy}", "WARNING")
            self.strategy = new_strategy

        # 4. Target Profit Sync (Percentage)
        new_profit_pct = remote_data.get('target_profit') # Assumed to be percentage now
        if new_profit_pct is not None and float(new_profit_pct) != self.target_percentage:
            logger.log(f"REMOTE UPDATE: Target % changed from {self.target_percentage} -> {new_profit_pct}", "WARNING")
            self.target_percentage = float(new_profit_pct)
            # Recalculate target if we have starting balance
            if self.starting_balance:
                self.target_balance = self.starting_balance + (self.target_percentage / 100 * self.starting_balance)

        # 5. Command Sync
        remote_cmd = remote_data.get('command')
        should_run = True 
        if isinstance(remote_cmd, bool):
            should_run = remote_cmd
        elif isinstance(remote_cmd, str):
            normalized = remote_cmd.lower().strip()
            if normalized in ['false', 'stop', '0']:
                should_run = False
            elif normalized in ['true', 'start', 'run', '1']:
                should_run = True
                
        if not should_run and self.running:
            logger.log("REMOTE COMMAND: STOP received.", "ERROR")
            self.running = False
        elif should_run and not self.running:
            self.running = True
            logger.log("REMOTE COMMAND: RUN received.", "SUCCESS")

    def capture_status_region(self, region_key):
        region_config = self.config.get(region_key)
        if not region_config:
            raise ValueError(f"Region {region_key} not configured.")
        
        region = (
            int(region_config['x']), 
            int(region_config['y']), 
            int(region_config['width']), 
            int(region_config['height'])
        )
        return pyautogui.screenshot(region=region)

    def check_tie_region(self):
        try:
            img = self.capture_status_region('status_region_tie')
            np_img = np.array(img)
            avg_color = np_img.mean(axis=(0, 1))
            r, g, b = avg_color
            is_green = (g > r + 10) and (g > b + 10) and (g > 80)
            if is_green:
                gray_image = img.convert('L')
                img_thresh = gray_image.point(lambda p: p > 150 and 255) 
                text = pytesseract.image_to_string(img_thresh).strip().lower()
                if "tie" in text:
                    return True
        except Exception as e:
            logger.log(f"Tie region check error: {e}", "DEBUG")
        return False

    def analyze_state(self):
        if self.check_tie_region():
            return "TIE"
        image = self.capture_status_region('status_region_main')
        gray_image = image.convert('L')
        text = pytesseract.image_to_string(gray_image).strip().lower()
        if "banker" in text: return "BANKER"
        if "player" in text: return "PLAYER"
        if "win" in text: return "GENERIC_WIN"
        return None

    def get_current_balance(self):
        if 'status_region_balance' not in self.config:
            return None
        try:
            image = self.capture_status_region('status_region_balance')
            gray_image = image.convert('L')
            text = pytesseract.image_to_string(gray_image).strip()
            clean_text = "".join(c for c in text if c.isdigit() or c == '.')
            if clean_text:
                return float(clean_text)
        except Exception as e:
            logger.log(f"Balance detection error: {e}", "DEBUG")
        return None

    def wait_for_result_to_clear(self):
        logger.log("Waiting for result banner to clear...", "INFO")
        time.sleep(5)
        return True

    def drift_detection(self):
        target = self.config['target_a']
        current_color = pyautogui.pixel(int(target['x']), int(target['y']))
        baseline = target.get('color')
        if baseline:
            diff = sum(abs(c - b) for c, b in zip(current_color, baseline))
            if diff > 100:
                return False 
        return True

    def select_chips(self, amount):
        if not self.config.get('chips'):
            logger.log("No chips configured!", "ERROR")
            return {}
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

        time.sleep(1.0)
        target_key = 'target_a' if target_char == 'B' else 'target_b'
        target_name = "BANKER" if target_char == 'B' else "PLAYER"
        target = self.config[target_key]
        
        logger.log(f"Executing Bet: {self.current_bet} on {target_name} (Lvl {self.martingale_level})", "INFO")
        chips_to_click = self.select_chips(self.current_bet)
        for chip_val, count in chips_to_click.items():
            chip_config = self.config['chips'].get(str(chip_val))
            if chip_config:
                pyautogui.click(chip_config['x'], chip_config['y'], duration=0.1)
                time.sleep(0.1)
                pyautogui.click(x=target['x'], y=target['y'], clicks=count, interval=0.25, duration=0.1)
                time.sleep(0.1)

        self.push_monitoring_update(bet_side=target_char, bet_amount=self.current_bet)

    def run_cycle(self):
        self.push_monitoring_update()
        self.drift_detection() 
        
        # --- Profit Percentage Logic ---
        if self.target_percentage is not None:
            current_bal = self.get_current_balance()
            if self.starting_balance is None and current_bal is not None:
                self.starting_balance = current_bal
                self.target_balance = self.starting_balance + (self.target_percentage / 100 * self.starting_balance)
                logger.log(f"Session Started. Capital: {self.starting_balance} | Target: {self.target_balance} ({self.target_percentage}%)", "INFO")
                self.first_run = False

            if current_bal is not None and self.target_balance is not None:
                if current_bal >= self.target_balance:
                    logger.log(f"GOAL REACHED! Current: {current_bal} >= Target: {self.target_balance}", "SUCCESS")
                    self.running = False
                    return
        
        # 1. Determine Current Strategy Step
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
        
        # 2. State Detection
        outcome = self.analyze_state()
        if outcome:
            logger.log(f"Detected Outcome: {outcome}", "SUCCESS")
            self.wait_for_result_to_clear()
            
            current_target_name = "BANKER" if current_target_char == 'B' else "PLAYER"
            actual_result = "LOSS"
            if outcome == "TIE": actual_result = "PUSH"
            elif outcome == current_target_name or outcome == "GENERIC_WIN": actual_result = "WIN"
                
            logger.log(f"Pattern[{self.pattern_index}] {current_target_char} | Outcome: {outcome} -> {actual_result}", "INFO")

            if self.last_result is None:
                self.current_bet = self.base_bet
                self.martingale_level = 1
                self.pattern_index = 0
                logger.log("Synced. Preparing first bet.", "INFO")
            elif actual_result == "WIN":
                self.current_bet = self.base_bet
                self.martingale_level = 1
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern)
            elif actual_result == "PUSH":
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern)
            elif actual_result == "LOSS":
                # Advanced Martingale Multiplier Logic
                multipliers = self.strategies.get(self.strategy, self.strategies["Standard"])
                if self.martingale_level <= len(multipliers):
                    multiplier = multipliers[self.martingale_level - 1]
                    self.current_bet *= multiplier
                else:
                    self.current_bet *= 2 # Safety fallback

                self.martingale_level += 1
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern)

                if self.martingale_level > self.max_level:
                    logger.log(f"MAX LEVEL {self.max_level} REACHED. Safety Stop.", "ERROR")
                    self.running = False
                    return

            self.last_result = actual_result
            self.execute_bet(self.pattern[self.pattern_index])
            time.sleep(2) 
        else:
            if time.time() - self.last_sync_time > 5:
                self.push_monitoring_update()
            time.sleep(1)

    def start(self):
        self.running = True
        try:
            while self.running:
                self.run_cycle()
        except KeyboardInterrupt:
            logger.log("Bot stopped.", "INFO")
