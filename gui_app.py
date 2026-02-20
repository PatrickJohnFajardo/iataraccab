import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import sys
import os
from bot_logic import Bot
from utils import logger
import calibration


class BaccaratGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Baccarat Automation Bot v2.0")
        self.root.geometry("620x800")
        self.root.configure(bg="#2c3e50")
        
        # Create a Canvas and Scrollbar for scrollability
        self.canvas = tk.Canvas(self.root, bg="#2c3e50", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#2c3e50")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=600)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Bind MouseWheel to Canvas
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Add trace for strategy change
        # (Included in setup_ui but re-referenced here for clarity)
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.is_running = False
        self.is_calibrating = False
        self.calib_event = threading.Event()
        
        # Initialize bot on startup for immediate DB registration
        self.initialize_bot_instance()
        
        self.setup_ui()
        self.bind_keys()

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def bind_keys(self):
        self.root.bind("<space>", self.on_space_pressed)

    def on_space_pressed(self, event):
        if self.is_calibrating:
            self.trigger_next_step()

    def setup_ui(self):
        # Main Container - Now parented to scrollable_frame
        self.main_frame = tk.Frame(self.scrollable_frame, bg="#2c3e50")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=20)
        
        # Title
        title_label = tk.Label(self.main_frame, text="BACCARAT BOT", font=("Helvetica", 24, "bold"), fg="#ecf0f1", bg="#2c3e50")
        title_label.pack(pady=10)
        
        # --- Setup Section ---
        self.setup_frame = tk.LabelFrame(self.main_frame, text="Bot Setup", fg="#ecf0f1", bg="#2c3e50", font=("Helvetica", 10, "bold"))
        self.setup_frame.pack(fill=tk.X, pady=10, padx=5)
        
        self.calib_btn = ttk.Button(self.setup_frame, text="Run Calibration", command=self.start_calibration)
        self.calib_btn.pack(side=tk.LEFT, padx=10, pady=10)
 
        self.next_btn = ttk.Button(self.setup_frame, text="NEXT STEP", command=self.trigger_next_step, state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=5)

        # --- Bot Configuration ---
        self.config_frame = tk.LabelFrame(self.main_frame, text="Bot Settings", fg="#ecf0f1", bg="#2c3e50", font=("Helvetica", 10, "bold"))
        self.config_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # Base Bet
        tk.Label(self.config_frame, text="Base Bet:", fg="#ecf0f1", bg="#2c3e50").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        self.base_bet_var = tk.StringVar(value="10")
        self.base_bet_entry = ttk.Entry(self.config_frame, textvariable=self.base_bet_var, width=10)
        self.base_bet_entry.grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Mode
        tk.Label(self.config_frame, text="Mode:", fg="#ecf0f1", bg="#2c3e50").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        self.mode_var = tk.StringVar(value="Sequence")
        self.mode_combo = ttk.Combobox(self.config_frame, textvariable=self.mode_var, values=["Sequence", "Standard Martingale"], state="readonly")
        self.mode_combo.grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        self.mode_var.trace_add("write", self.toggle_mode_fields)

        # Pattern
        self.pattern_label = tk.Label(self.config_frame, text="Pattern:", fg="#ecf0f1", bg="#2c3e50")
        self.pattern_label.grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        self.pattern_options = ["All P", "All B", "PB", "BP", "PPPB", "BBBP"]
        self.pattern_var = tk.StringVar(value="PPPB")
        self.pattern_combo = ttk.Combobox(self.config_frame, textvariable=self.pattern_var, values=self.pattern_options, width=17)
        self.pattern_combo.grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Side (For Standard mode)
        self.side_label = tk.Label(self.config_frame, text="Bet Side:", fg="#ecf0f1", bg="#2c3e50")
        self.side_var = tk.StringVar(value="Banker")
        self.side_combo = ttk.Combobox(self.config_frame, textvariable=self.side_var, values=["Banker", "Player"], state="readonly")

        # Strategy (Tank, Sweeper, etc.)
        tk.Label(self.config_frame, text="Strategy:", fg="#ecf0f1", bg="#2c3e50").grid(row=3, column=0, sticky=tk.W, padx=10, pady=5)
        self.strategy_var = tk.StringVar(value="Standard")
        self.strategy_combo = ttk.Combobox(self.config_frame, textvariable=self.strategy_var, values=["Standard", "Tank", "Sweeper", "Burst"], state="readonly")
        self.strategy_combo.grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
        self.strategy_var.trace_add("write", self.on_strategy_change)

        # Target Profit %
        tk.Label(self.config_frame, text="Target Profit %:", fg="#ecf0f1", bg="#2c3e50").grid(row=4, column=0, sticky=tk.W, padx=10, pady=5)
        self.target_pct_var = tk.StringVar(value="10") # Default to 10%
        self.target_pct_entry = ttk.Entry(self.config_frame, textvariable=self.target_pct_var, width=10)
        self.target_pct_entry.grid(row=4, column=1, sticky=tk.W, padx=10, pady=5)

        # Max Martingale Level
        tk.Label(self.config_frame, text="Max Martingale Level:", fg="#ecf0f1", bg="#2c3e50").grid(row=5, column=0, sticky=tk.W, padx=10, pady=5)
        self.max_level_var = tk.StringVar(value="10")
        self.max_level_entry = ttk.Entry(self.config_frame, textvariable=self.max_level_var, width=10)
        self.max_level_entry.grid(row=5, column=1, sticky=tk.W, padx=10, pady=5)

        # Initial Toggle
        self.toggle_mode_fields()

        # --- Remote Settings (Website) ---
        self.remote_frame = tk.LabelFrame(self.main_frame, text="Remote Settings (Website)", fg="#f1c40f", bg="#2c3e50", font=("Helvetica", 10, "bold"))
        self.remote_frame.pack(fill=tk.X, pady=10, padx=5)
        
        # Grid for remote settings
        self.remote_labels = {}
        fields = [
            ("Base Bet:", "bet"),
            ("Pattern:", "pattern"),
            ("Strategy:", "strategy"),
            ("Target %:", "target_profit"),
            ("Status:", "command")
        ]
        
        for i, (label_text, key) in enumerate(fields):
            tk.Label(self.remote_frame, text=label_text, fg="#ecf0f1", bg="#2c3e50").grid(row=i//2, column=(i%2)*2, sticky=tk.W, padx=10, pady=2)
            val_lbl = tk.Label(self.remote_frame, text="---", fg="#f1c40f", bg="#2c3e50", font=("Helvetica", 10, "bold"))
            val_lbl.grid(row=i//2, column=(i%2)*2+1, sticky=tk.W, padx=5, pady=2)
            self.remote_labels[key] = val_lbl

        # --- Logs ---
        log_frame = tk.LabelFrame(self.main_frame, text="Bot Logs", fg="#ecf0f1", bg="#2c3e50", font=("Helvetica", 10, "bold"))
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=5)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', height=10, bg="#34495e", fg="#ecf0f1", font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Redirect logger to GUI
        self.setup_logging()

        # --- Controls ---
        cntrl_frame = tk.Frame(self.main_frame, bg="#2c3e50")
        cntrl_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = tk.Button(cntrl_frame, text="START BOT", command=self.start_bot_thread, bg="#27ae60", fg="white", font=("Helvetica", 12, "bold"), width=15)
        self.start_btn.pack(side=tk.LEFT, expand=True, padx=5)
        
        self.stop_btn = tk.Button(cntrl_frame, text="STOP BOT", command=self.stop_bot, state=tk.DISABLED, bg="#c0392b", fg="white", font=("Helvetica", 12, "bold"), width=15)
        self.stop_btn.pack(side=tk.LEFT, expand=True, padx=5)
        
        self.test_btn = tk.Button(cntrl_frame, text="TEST CLICKS", command=self.test_bot_clicks, bg="#2980b9", fg="white", font=("Helvetica", 12, "bold"), width=15)
        self.test_btn.pack(side=tk.LEFT, expand=True, padx=5)
        
        self.enable_bot_controls() # Changed from disable_bot_controls to enable_bot_controls

    def setup_logging(self):
        # Override logger.log to also write to our log_area
        original_log = logger.log
        
        def gui_log(message, level="INFO"):
            original_log(message, level)
            self.root.after(0, self.append_log, f"[{level}] {message}")
            
        logger.log = gui_log

    def append_log(self, text):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, text + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')



    def start_calibration(self):
        if messagebox.askyesno("Calibration", "Calibration instructions will appear in the Bot Logs.\nUse SPACE or the NEXT STEP button to capture points.\nContinue?"):
            self.is_calibrating = True
            self.calib_btn.config(state=tk.DISABLED)
            self.next_btn.config(state=tk.NORMAL)
            self.calib_event.clear()
            threading.Thread(target=self.run_calibration, daemon=True).start()

    def trigger_next_step(self):
        if self.is_calibrating:
            self.calib_event.set()

    def run_calibration(self):
        def gui_waiter(msg):
            self.calib_event.clear()
            # Wait for event to be set
            self.calib_event.wait()
            self.calib_event.clear()

        try:
            logger.log("CALIBRATION STARTED: Watch the logs for instructions.", "WARNING")
            calibration.main(wait_func=gui_waiter)
            logger.log("CALIBRATION FINISHED", "SUCCESS")
            self.root.after(0, lambda: messagebox.showinfo("Success", "Calibration complete!"))
        except Exception as e:
            logger.log(f"Calibration Error: {e}", "ERROR")
            self.root.after(0, lambda: messagebox.showerror("Error", f"Calibration failed: {e}"))
        finally:
            self.is_calibrating = False
            self.root.after(0, lambda: self.calib_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.next_btn.config(state=tk.DISABLED))

    def toggle_mode_fields(self, *args):
        mode = self.mode_var.get()
        if mode == "Standard Martingale":
            self.pattern_label.grid_remove()
            self.pattern_entry.grid_remove()
            self.side_label.grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
            self.side_combo.grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        else:
            self.side_label.grid_remove()
            self.side_combo.grid_remove()
            self.pattern_label.grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
            self.pattern_combo.grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)


    def enable_bot_controls(self):
        self.start_btn.config(state=tk.NORMAL)
        self.base_bet_entry.config(state=tk.NORMAL)
        self.pattern_combo.config(state="normal")
        self.mode_combo.config(state="readonly")

    def disable_bot_controls(self):
        self.start_btn.config(state=tk.DISABLED)

    def on_strategy_change(self, *args):
        """Automatically set defaults when Burst strategy is selected."""
        if self.strategy_var.get() == "Burst":
            self.base_bet_var.set("90")
            self.max_level_var.set("3")
            logger.log("Burst Strategy selected: Auto-set Base Bet to 90 and Max Level to 3.", "INFO")

    def initialize_bot_instance(self):
        """Creates the initial bot instance for monitoring/registration."""
        try:
            self.bot = Bot(on_settings_sync=self.update_remote_settings_display)
            logger.log(f"Bot Registered as: {self.bot.pc_name}", "SUCCESS")
        except Exception as e:
            logger.log(f"Startup Monitoring Error: {e}", "DEBUG")
            self.bot = None

    def update_remote_settings_display(self, remote_data):
        """Callback to update GUI with remote settings."""
        if not hasattr(self, 'remote_labels'): return
        
        def update():
            for key, label in self.remote_labels.items():
                val = remote_data.get(key)
                if key == 'command':
                    status = "RUNNING" if str(val).lower() in ['true', 'start', 'run', '1'] else "STOPPED"
                    label.config(text=status)
                elif val is not None:
                    label.config(text=str(val))
                    
        self.root.after(0, update)

    def start_bot_thread(self):
        base_bet = self.base_bet_var.get()
        if not base_bet.isdigit():
            messagebox.showerror("Input Error", "Base Bet must be a number.")
            return
            
        pattern = self.pattern_var.get().strip()
        # Map descriptive labels to actual logic
        if pattern.upper() == "ALL P": pattern = "P"
        elif pattern.upper() == "ALL B": pattern = "B"
        
        if not pattern:
            messagebox.showerror("Input Error", "Pattern cannot be empty.")
            return

        target_pct = None
        pct_val = self.target_pct_var.get().strip()
        if pct_val:
            try:
                target_pct = float(pct_val)
            except ValueError:
                messagebox.showerror("Input Error", "Target Profit % must be a number.")
                return

        max_level = self.max_level_var.get()
        if not max_level.isdigit():
            messagebox.showerror("Input Error", "Max Martingale Level must be a number.")
            return

        reset_on_cycle = (self.mode_var.get() == "Sequence")
        
        if self.mode_var.get() == "Standard Martingale":
            pattern = "B" if self.side_var.get() == "Banker" else "P"
            reset_on_cycle = False

        # Update existing bot instance or create if failed earlier
        if not self.bot:
            self.initialize_bot_instance()
            
        if self.bot:
            self.bot.base_bet = int(base_bet)
            self.bot.current_bet = self.bot.base_bet
            self.bot.pattern = pattern.upper().replace("-", "").replace(" ", "")
            self.bot.reset_on_cycle = reset_on_cycle
            self.bot.target_percentage = target_pct
            self.bot.max_level = int(max_level)
            self.bot.strategy = self.strategy_var.get()
            self.bot.pattern_index = 0
            self.bot.martingale_level = 0
            self.bot.last_result = None # Force first hand to be baseline
            self.bot.first_run = True
            self.bot.starting_balance = None # Reset for new session
            self.bot.target_balance = None
            self.bot.start_time = time.time() # RESET CLOCK ON GUI START
        
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
        self.bot_thread.start()

    def run_bot(self):
        try:
            self.bot.running = True
            logger.log(f"Bot session active. Listening for commands...", "INFO")
            
            # The 'is_running' flag is controlled by the GUI START/STOP buttons.
            # The 'bot.running' flag is controlled by remote Supabase commands.
            while self.is_running:
                if self.bot.running:
                    # Run a single cycle of the bot logic
                    self.bot.run_cycle()
                else:
                    # IDLE MODE: Bot is stopped remotely, but the thread is still listening
                    # We check Supabase every 5 seconds to see if 'RUN' is sent back
                    if time.time() - self.bot.last_sync_time > 5:
                        self.bot.push_monitoring_update(status="Idle")
                    time.sleep(1)

        except Exception as e:
            logger.log(f"Bot Internal Error: {e}", "ERROR")
            self.is_running = False
        finally:
            self.root.after(0, self.on_bot_stopped)

    def stop_bot(self):
        self.is_running = False
        if self.bot:
            self.bot.running = False
            self.bot.push_monitoring_update(status="Stopped")
        logger.log("Stopping bot...", "INFO")

    def on_bot_stopped(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        logger.log("Bot stopped.", "INFO")

    def test_bot_clicks(self):
        if self.is_running:
            messagebox.showwarning("Busy", "Cannot test clicks while bot is running.")
            return
            
        if not self.bot:
            self.initialize_bot_instance()
            
        if self.bot:
            threading.Thread(target=self.bot.execute_test_bet, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = BaccaratGUI(root)
    root.mainloop()
