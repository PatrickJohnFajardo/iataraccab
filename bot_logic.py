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
    def __init__(self, config_file='config.json', pattern_string='B', base_bet=10, reset_on_cycle=True, target_balance=None, max_level=6):
        self.config_file = config_file
        self.config = self.load_config()
        self.running = False
        self.base_bet = base_bet
        self.current_bet = self.base_bet
        self.last_result = None 
        self.target_balance = target_balance
        self.max_level = max_level
        self.first_run = True # Flag for initial safety checks
        self.last_sync_time = 0
        
        # v2 Pattern Strategy
        # Clean the input: ensure uppercase, remove invalid chars if any, though we mostly trust main.py
        self.pattern = pattern_string.upper().replace("-", "").replace(" ", "")
        
        # Validation: Allow P, B, and T (Tie/Repeat)
        if not self.pattern or any(c not in 'PBT' for c in self.pattern):
            logger.log(f"Invalid Pattern '{self.pattern}'! Defaulting to 'B'.", "WARNING")
            self.pattern = 'B'
            
        self.pattern_index = 0
        self.reset_on_cycle = reset_on_cycle
        
        mode_str = "Cycle-Reset" if self.reset_on_cycle else "Infinite Martingale"
        logger.log(f"Bot Initialized. Pattern: {self.pattern} | Mode: {mode_str} | Base: {self.base_bet}", "INFO")

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
        """Pushes state TO cloud AND pulls settings FROM cloud."""
        if not self.sb_url or not self.sb_key:
            return

        headers = {
            "apikey": self.sb_key,
            "Authorization": f"Bearer {self.sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        # 1. Prepare PUSH data
        effective_status = status if status else ("Running" if self.running else "Stopped")
        balance = self.get_current_balance()
        
        # We only send what we are 100% sure exists to avoid Schema Cache errors
        payload = {
            "pc_name": self.pc_name,
            "status": effective_status,
            "balance": balance if balance is not None else 0,
            "level": self.martingale_level
        }

        try:
            # We add on_conflict=pc_name to ensure Supabase knows which column to check for duplicates
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
                # Log detailed error to help the user identify missing columns
                logger.log(f"Supabase Sync Failed: {response.text}", "DEBUG")
                if "column" in response.text.lower():
                    logger.log("Table schema mismatch detected. Check column names.", "ERROR")
        except Exception as e:
            logger.log(f"Monitoring sync error: {e}", "DEBUG")

    def sync_remote_settings(self, remote_data):
        """Applies configuration changes from the Harmony Dashboard."""
        # 1. Pattern Sync
        new_pattern = remote_data.get('pattern')
        if new_pattern and new_pattern.upper() != self.pattern:
            logger.log(f"REMOTE UPDATE: Pattern changed from {self.pattern} -> {new_pattern.upper()}", "WARNING")
            self.pattern = new_pattern.upper().replace("-", "").replace(" ", "")
            self.pattern_index = 0 # Reset pattern sequence on change

        # 2. Level (Base Bet) Sync
        new_level = remote_data.get('level')
        if new_level is not None and int(new_level) != self.base_bet:
            logger.log(f"REMOTE UPDATE: Base Bet (Level) changed from {self.base_bet} -> {new_level}", "WARNING")
            self.base_bet = int(new_level)
            self.current_bet = self.base_bet
            self.martingale_level = 1

        # 3. Target Profit Sync
        new_profit = remote_data.get('target_profit')
        if new_profit is not None and float(new_profit) != self.target_balance:
            logger.log(f"REMOTE UPDATE: Target Balance changed from {self.target_balance} -> {new_profit}", "WARNING")
            self.target_balance = float(new_profit)

        # 4. Command Sync (Boolean: True=RUN, False=STOP)
        # We accept 'command' as boolean or string "true"/"false"/"run"/"stop"
        remote_cmd = remote_data.get('command')
        
        should_run = True # Default to Running if missing
        
        if isinstance(remote_cmd, bool):
            should_run = remote_cmd
        elif isinstance(remote_cmd, str):
            normalized = remote_cmd.lower().strip()
            if normalized in ['false', 'stop', '0']:
                should_run = False
            elif normalized in ['true', 'start', 'run', '1']:
                should_run = True
                
        if not should_run and self.running:
            logger.log("REMOTE COMMAND: FALSE (STOP) received. Bot entering IDLE mode.", "ERROR")
            self.running = False
        elif should_run and not self.running:
            self.running = True
            logger.log("REMOTE COMMAND: TRUE (RUN) received. Resuming bot cycle...", "SUCCESS")

    def capture_status_region(self, region_key):
        """Captures the screenshot of the defined status region."""
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
        """
        Checks the dedicated Tie Region for GREEN color AND 'TIE' text.
        """
        try:
            # 1. Capture Tie Region
            img = self.capture_status_region('status_region_tie')
            
            # 2. Check Green Color Dominance
            # Convert to numpy array for fast pixel analysis
            np_img = np.array(img)
            # Calculate average color
            avg_color = np_img.mean(axis=(0, 1))
            r, g, b = avg_color
            
            # Simple Green Dominance Check: G should be highest and significantly distinct
            is_green = (g > r + 10) and (g > b + 10) and (g > 80)
            
            if is_green:
                logger.log(f"Tie Region Green Detected (R={r:.1f}, G={g:.1f}, B={b:.1f})", "DEBUG")
                
                # 3. Verify with OCR
                gray_image = img.convert('L')
                # Pre-process for better OCR (thresholding)
                img_thresh = gray_image.point(lambda p: p > 150 and 255) 
                
                text = pytesseract.image_to_string(img_thresh).strip().lower()
                if "tie" in text:
                    logger.log(f"Tie Confirmed via OCR: '{text}'", "SUCCESS")
                    return True
                else:
                    logger.log(f"Tie Region Green but no 'OCR' text found. Text: '{text}'. Assuming generic Tie.", "WARNING")
                    # If strictly green enough, arguably we can assume Tie. 
                    # User asked to look for "green AND tie". Strict mode:
                    return False
                    
        except Exception as e:
            logger.log(f"Tie region check error: {e}", "DEBUG")
            
        return False

    def analyze_state(self):
        """
        Analyzes the captured image for text (OCR) and secondary indicators.
        Returns: 'BANKER', 'PLAYER', 'TIE', or None (Unknown/Waiting)
        """
        # 1. Check Tie Region FIRST
        if self.check_tie_region():
            return "TIE"

        # 2. Check Main Region (Player/Banker)
        image = self.capture_status_region('status_region_main')

        # --- DEBUG: SAVE IMAGE ---
        try:
            image.save("debug_scan_region.png")
        except:
            pass
        # -------------------------

        gray_image = image.convert('L')
        # Simple thresholding to clean up background noise
        # img_thresh = gray_image.point(lambda p: p > 200 and 255)  
        
        text = pytesseract.image_to_string(gray_image).strip().lower()
        
        if len(text) > 1:
             logger.log(f"Main Region OCR Read: '{text}'", "DEBUG")

        if "tie" in text:
            # Fallback if "Tie" appears in main region (unlikely but safe)
            return "TIE"
        if "banker" in text:
            return "BANKER"
        if "player" in text:
            return "PLAYER"
        
        if "win" in text:
            logger.log("Saw 'Win' but no side name. Inferring Generic Win.", "WARNING")
            return "GENERIC_WIN"
            
        return None

    def get_current_balance(self):
        """Extracts the numerical balance from the balance status region."""
        if 'status_region_balance' not in self.config:
            # Fallback or silent return to avoid spamming logs
            return None
            
        try:
            image = self.capture_status_region('status_region_balance')
            gray_image = image.convert('L')
            text = pytesseract.image_to_string(gray_image).strip()
            
            # Clean text: keep only digits and decimal point
            clean_text = "".join(c for c in text if c.isdigit() or c == '.')
            if clean_text:
                val = float(clean_text)
                return val
        except Exception as e:
            logger.log(f"Balance detection error: {e}", "DEBUG")
        return None

    def wait_for_result_to_clear(self):
        """Wait until the result banner disappears."""
        logger.log("Waiting for result banner to clear...", "INFO")
        time.sleep(5)
        return True

    def drift_detection(self):
        # Safety check: verify that buttons are where we expect them to be.
        target = self.config['target_a']
        current_color = pyautogui.pixel(int(target['x']), int(target['y']))
        baseline = target.get('color')
        if baseline:
            diff = sum(abs(c - b) for c, b in zip(current_color, baseline))
            if diff > 100:
                logger.log(f"Drift Warning (Ignored): Expected {baseline}, Got {current_color}", "WARNING")
                return False 
        return True

    def select_chips(self, amount):
        if not self.config.get('chips'):
            logger.log("No chips configured! Run calibration again.", "ERROR")
            return {}
        
        available_chips = sorted([int(k) for k in self.config['chips'].keys()], reverse=True)
        selected = {}
        remaining = amount
        for chip in available_chips:
            if remaining >= chip:
                count = remaining // chip
                remaining = remaining % chip
                selected[chip] = count
        if remaining > 0:
            logger.log(f"Warning: Could not exactly match amount {amount}. Remainder: {remaining}", "WARNING")
        return selected

    def execute_bet(self, target_char):
        """
        Dynamic Betting based on current target char (P/B/T).
        """
        # If the pattern says 'T', it means "Repeat previous betting side"
        # as requested: "ignore the tie, and bet the previous bet will be used"
        if target_char == 'T':
            lookup = self.pattern_index - 1
            resolved_side = None
            while lookup >= 0:
                if self.pattern[lookup] in 'PB':
                    resolved_side = self.pattern[lookup]
                    break
                lookup -= 1
            target_char = resolved_side if resolved_side else 'B'
            logger.log(f"Execute Bet resolving 'T' to: {target_char}", "DEBUG")

        logger.log("Waiting 1s for betting window to open...", "DEBUG")
        time.sleep(1.0) # Added delay per user request
        
        # Determine Target Key based on Char
        target_key = 'target_a' if target_char == 'B' else 'target_b'
        target_name = "BANKER" if target_char == 'B' else "PLAYER"
        target = self.config[target_key]
        
        logger.log(f"Executing Bet: {self.current_bet} on {target_name} [{self.pattern_index + 1}/{len(self.pattern)}]", "INFO")
        
        # 1. Select Chips
        chips_to_click = self.select_chips(self.current_bet)
        
        # 2. Execute Clicks
        for chip_val, count in chips_to_click.items():
            chip_config = self.config['chips'].get(str(chip_val))
            if chip_config:
                # Step A: Click the Chip ONCE to select it
                logger.log(f"Selecting Chip [{chip_val}]", "DEBUG")
                pyautogui.click(chip_config['x'], chip_config['y'], duration=0.1)
                time.sleep(0.1)
                
                # Step B: Click the Bet Spot
                logger.log(f"Placing {count} chip(s) on {target_name}", "DEBUG")
                pyautogui.click(
                    x=target['x'], 
                    y=target['y'], 
                    clicks=count, 
                    interval=0.25,
                    duration=0.1
                )
                time.sleep(0.1)
            else:
                logger.log(f"Chip {chip_val} not found in config!", "ERROR")

        self.push_monitoring_update(bet_side=target_char, bet_amount=self.current_bet)
        logger.log("Bet Placed.", "SUCCESS")

    def run_cycle(self):
        """Single iteration of the logic loop."""
        
        # 0. Sync and Pulse (Heartbeat)
        self.push_monitoring_update()
        
        # 0.1 Safety Check
        self.drift_detection() 
        
        # 0.1 Balance Check
        if self.target_balance is not None:
            current_bal = self.get_current_balance()
            
            if self.first_run:
                logger.log(f"Initial Balance Check: {current_bal if current_bal is not None else 'Unknown'}", "INFO")
                self.first_run = False

            if current_bal is not None and current_bal >= self.target_balance:
                logger.log(f"SAFETY STOP: Target Balance {self.target_balance} already reached or exceeded (Current: {current_bal}).", "WARNING")
                self.running = False
                return
        
        # 1. Determine Current Strategy Step
        current_target_char = self.pattern[self.pattern_index] # 'P', 'B', or 'T'
        
        # If the pattern says 'T', it means "Repeat previous betting side"
        # as requested: "ignore the tie, and bet the previous bet will be used"
        if current_target_char == 'T':
            # Search backwards for the last non-T side (P or B)
            lookup = self.pattern_index - 1
            resolved_side = None
            while lookup >= 0:
                if self.pattern[lookup] in 'PB':
                    resolved_side = self.pattern[lookup]
                    break
                lookup -= 1
            
            # If no previous P/B found (e.g. starts with T), default to 'B'
            current_target_char = resolved_side if resolved_side else 'B'
            logger.log(f"Pattern step is 'T'. Repeating previous side: {current_target_char}", "DEBUG")
        
        # 2. State Detection
        # img capture is now handled inside analyze_state() for specific regions
        outcome = self.analyze_state()
        
        if outcome:
            logger.log(f"Detected Outcome: {outcome}", "SUCCESS")
            self.wait_for_result_to_clear()
            
            # --- Result Evaluation ---
            # Use the already resolved current_target_char from top of run_cycle
            current_target_name = "BANKER" if current_target_char == 'B' else "PLAYER"
            
            actual_result = None
            if outcome == "TIE":
                actual_result = "PUSH"
            elif outcome == current_target_name:
                actual_result = "WIN"
            elif outcome == "GENERIC_WIN":
                actual_result = "WIN"
            else:
                # Opponent Won
                actual_result = "LOSS"
                
            logger.log(f"Pattern[{self.pattern_index}] {current_target_char} | Outcome: {outcome} -> Result: {actual_result}", "INFO")

            # --- Pattern & Martingale Logic ---
            
            if self.last_result is None:
                logger.log(f"First detected result ({outcome}). Syncing Logic...", "INFO")
                # We do NOT bet immediately on sync to be safe, or we DO?
                # V1 logic was to sync then place bet.
                # V2 logic: If we are syncing, we just set the bet for the NEXT round.
                self.current_bet = self.base_bet
                self.pattern_index = 0
                logger.log("Sync Complete. Preparing first bet.", "INFO")
                
            elif actual_result == "PUSH":
                 logger.log("Result TIE/PUSH. Maintaining bet amount but Advancing Pattern.", "INFO")
                 # Advance index to next pattern step
                 self.pattern_index = (self.pattern_index + 1) % len(self.pattern)
                 # Bet amount stays self.current_bet (Push) 
                 
            elif actual_result == "WIN":
                logger.log("Result WIN. Resetting Bet. Advancing Pattern.", "INFO")
                self.current_bet = self.base_bet
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern)
                
            elif actual_result == "LOSS":
                self.martingale_level += 1
                
                # Check for Max Martingale Level Limit
                if self.martingale_level > self.max_level:
                    logger.log(f"MAX LEVEL REACHED ({self.max_level}). Stopping bot for safety.", "ERROR")
                    self.current_bet = self.base_bet # Reset for next session
                    self.running = False
                    return

                # Calculate next bet
                self.current_bet *= 2
                logger.log(f"Result LOSS. Martingale Level {self.martingale_level-1} -> Doubling to {self.current_bet}.", "INFO")
            
            # Reset Martingale level trackers on Win or final Loss Reset
            if actual_result == "WIN" or self.current_bet == self.base_bet:
                self.martingale_level = 1

            # Always advance pattern on Loss too
            self.pattern_index = (self.pattern_index + 1) % len(self.pattern)

            self.last_result = actual_result
            
            # Place the NEXT bet immediately
            next_target_char = self.pattern[self.pattern_index]
            self.execute_bet(next_target_char)
            
            time.sleep(2) 
        else:
            # Periodic Sync (Every 5 seconds even if no result detected)
            if time.time() - self.last_sync_time > 5:
                self.push_monitoring_update()
            time.sleep(1)

    def start(self):
        self.running = True
        logger.log("Bot started. Press Ctrl+C in terminal to stop.", "INFO")
        try:
            while self.running:
                self.run_cycle()
        except KeyboardInterrupt:
            logger.log("Bot stopped by user.", "INFO")
