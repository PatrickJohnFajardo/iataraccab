import customtkinter as ctk
import tkinter as tk
from threading import Thread
import time
import os
import sys
import pyautogui
import json
from PIL import Image

# Internal modules
from auth import AuthManager
from utils import logger
import calibration
import bot_logic

# Theme Settings
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class BaccaratBotGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Baccarat Automation Bot v2.0")
        self.geometry("900x600")
        
        # Authentication Manager
        self.auth = AuthManager()
        self.current_user = None

        # Bot Instance
        self.bot = None
        self.bot_thread = None

        # Main Layout Container
        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)

        self.show_login_screen()
        
        # Connect logger to GUI
        logger.set_callback(self.log_to_gui)

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    # --- Login Screen ---
    def show_login_screen(self):
        self.clear_container()
        
        frame = ctk.CTkFrame(self.container, width=400, height=300)
        frame.place(relx=0.5, rely=0.5, anchor="center")

        label = ctk.CTkLabel(frame, text="Login", font=("Roboto", 24))
        label.pack(pady=20)

        self.username_entry = ctk.CTkEntry(frame, placeholder_text="Username")
        self.username_entry.pack(pady=10)

        self.password_entry = ctk.CTkEntry(frame, placeholder_text="Password", show="*")
        self.password_entry.pack(pady=10)

        btn = ctk.CTkButton(frame, text="Login", command=self.attempt_login)
        btn.pack(pady=20)
        
        self.msg_label = ctk.CTkLabel(frame, text="", text_color="red")
        self.msg_label.pack()

    def attempt_login(self):
        u = self.username_entry.get()
        p = self.password_entry.get()
        if self.auth.login(u, p):
            self.current_user = u
            self.show_dashboard()
        else:
            self.msg_label.configure(text="Invalid Credentials")

    # --- Dashboard ---
    def show_dashboard(self):
        self.clear_container()

        # Sidebar
        self.sidebar = ctk.CTkFrame(self.container, width=200, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        
        title_lbl = ctk.CTkLabel(self.sidebar, text="Baccarat Bot", font=("Roboto", 20, "bold"))
        title_lbl.pack(pady=20)

        ctk.CTkButton(self.sidebar, text="Home", command=lambda: self.switch_frame("home")).pack(pady=10, padx=10)
        ctk.CTkButton(self.sidebar, text="Calibration", command=lambda: self.switch_frame("calibration")).pack(pady=10, padx=10)
        ctk.CTkButton(self.sidebar, text="Logs", command=lambda: self.switch_frame("logs")).pack(pady=10, padx=10)
        
        ctk.CTkButton(self.sidebar, text="Logout", fg_color="red", command=self.logout).pack(side="bottom", pady=20, padx=10)

        # Main Content Area
        self.main_area = ctk.CTkFrame(self.container)
        self.main_area.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # Initialize Frames
        self.frames = {
            "home": self.create_home_frame(),
            "calibration": self.create_calibration_frame(),
            "logs": self.create_log_frame()
        }
        
        self.switch_frame("home")

    def switch_frame(self, name):
        # Hide all
        for frame in self.frames.values():
            frame.pack_forget()
        # Show selected
        self.frames[name].pack(fill="both", expand=True)

    def logout(self):
        self.current_user = None
        if self.bot and self.bot.running:
            self.stop_bot()
        self.show_login_screen()

    # --- Home Frame ---
    def create_home_frame(self):
        frame = ctk.CTkFrame(self.main_area)
        
        # Initial Settings
        opt_frame = ctk.CTkFrame(frame)
        opt_frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(opt_frame, text="Base Bet:").pack(side="left", padx=10)
        self.base_bet_var = ctk.StringVar(value="10")
        ctk.CTkEntry(opt_frame, textvariable=self.base_bet_var, width=60).pack(side="left")

        ctk.CTkLabel(opt_frame, text="Pattern (e.g. PPPB):").pack(side="left", padx=10)
        self.pattern_var = ctk.StringVar(value="PPPB")
        ctk.CTkEntry(opt_frame, textvariable=self.pattern_var, width=100).pack(side="left")

        # Start/Stop
        ctrl_frame = ctk.CTkFrame(frame)
        ctrl_frame.pack(fill="x", padx=20, pady=10)
        
        self.start_btn = ctk.CTkButton(ctrl_frame, text="START BOT", command=self.start_bot, fg_color="green")
        self.start_btn.pack(side="left", padx=20, expand=True)

        self.stop_btn = ctk.CTkButton(ctrl_frame, text="STOP BOT", command=self.stop_bot, fg_color="red", state="disabled")
        self.stop_btn.pack(side="right", padx=20, expand=True)

        # Status Display
        self.status_lbl = ctk.CTkLabel(frame, text="Status: IDLE", font=("Roboto", 16))
        self.status_lbl.pack(pady=40)

        return frame

    def start_bot(self):
        try:
            base = int(self.base_bet_var.get())
            pat = self.pattern_var.get()
            
            # Initialize Bot
            # Using reset_on_cycle=True as default for pattern mode
            self.bot = bot_logic.Bot(base_bet=base, pattern_string=pat, reset_on_cycle=True)
            
            # Start in Thread
            self.bot_thread = Thread(target=self.bot.start, daemon=True)
            self.bot_thread.start()
            
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.status_lbl.configure(text="Status: RUNNING")
            logger.log("Bot started from GUI", "INFO")
        except Exception as e:
            logger.log(f"Failed to start bot: {e}", "ERROR")

    def stop_bot(self):
        if self.bot:
            self.bot.running = False
            self.status_lbl.configure(text="Status: STOPPING...")
            # Wait a bit or checked by polling
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            logger.log("Stop signal sent to bot.", "INFO")

    # --- Calibration Frame ---
    def create_calibration_frame(self):
        frame = ctk.CTkFrame(self.main_area)
        
        ctk.CTkLabel(frame, text="Calibration Utility", font=("Roboto", 18, "bold")).pack(pady=10)
        ctk.CTkLabel(frame, text="Hover over the target, then click the button immediately.").pack()

        # Grid for buttons
        grid = ctk.CTkFrame(frame)
        grid.pack(pady=20, padx=20)
        
        self.calib_config = {}

        # Targets
        ctk.CTkButton(grid, text="Set Target A (Banker)", command=lambda: self.calib_item("target_a")).grid(row=0, column=0, padx=10, pady=10)
        ctk.CTkButton(grid, text="Set Target B (Player)", command=lambda: self.calib_item("target_b")).grid(row=0, column=1, padx=10, pady=10)
        ctk.CTkButton(grid, text="Set Target C (Tie)", command=lambda: self.calib_item("target_c")).grid(row=0, column=2, padx=10, pady=10)

        # Regions
        ctk.CTkButton(grid, text="Set Region Main", command=lambda: self.calib_region("status_region_main")).grid(row=1, column=0, padx=10, pady=10)
        ctk.CTkButton(grid, text="Set Region Tie", command=lambda: self.calib_region("status_region_tie")).grid(row=1, column=1, padx=10, pady=10)

        # Save
        ctk.CTkButton(frame, text="Save Configuration", command=self.save_calib, fg_color="blue").pack(pady=20)

        return frame

    def calib_item(self, key):
        # 3 second delay to move mouse
        # Ideally we'd like a 'press enter' listener but for GUI 'click and wait 3s' is ok
        # Actually proper way: Popup 'Press Enter to capture' that binds key event
        
        top = ctk.CTkToplevel(self)
        top.geometry("300x150")
        top.title("Capture")
        ctk.CTkLabel(top, text=f"Place mouse over {key}.\nPress SPACE to capture.").pack(pady=20)
        
        def on_key(event):
            x, y = pyautogui.position()
            self.calib_config[key] = {"x": x, "y": y}
            logger.log(f"Captured {key}: {x}, {y}", "SUCCESS")
            top.destroy()
            
        top.bind("<space>", on_key)
        top.focus_force()

    def calib_region(self, key):
        top = ctk.CTkToplevel(self)
        top.geometry("300x150")
        top.title("Capture Region")
        
        lbl = ctk.CTkLabel(top, text=f"Region {key}.\n1. Hover Top-Left & Press '1'\n2. Hover Bottom-Right & Press '2'")
        lbl.pack(pady=20)
        
        temp_coords = {}

        def on_1(event):
            x, y = pyautogui.position()
            temp_coords['tl'] = (x, y)
            lbl.configure(text="Top-Left captured! Now Bottom-Right -> '2'")
        
        def on_2(event):
            if 'tl' not in temp_coords: return
            x, y = pyautogui.position()
            tl_x, tl_y = temp_coords['tl']
            w = x - tl_x
            h = y - tl_y
            self.calib_config[key] = {"x": tl_x, "y": tl_y, "width": w, "height": h}
            logger.log(f"Captured Region {key}: {w}x{h}", "SUCCESS")
            top.destroy()

        top.bind("1", on_1)
        top.bind("2", on_2)
        top.focus_force()

    def save_calib(self):
        # Load existing first to not overwrite unseen keys
        existing = {}
        if os.path.exists("config.json"):
            with open("config.json", 'r') as f:
                try: existing = json.load(f)
                except: pass
        
        existing.update(self.calib_config)
        with open("config.json", 'w') as f:
            json.dump(existing, f, indent=4)
        logger.log("Configuration Saved!", "SUCCESS")

    # --- Log Frame ---
    def create_log_frame(self):
        frame = ctk.CTkFrame(self.main_area)
        self.log_text = ctk.CTkTextbox(frame, width=600, height=400)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        # Disable editing
        self.log_text.configure(state="disabled")
        return frame

    def log_to_gui(self, message):
        # Must be thread safe if called from bot thread
        self.after(0, self._append_log, message)

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

if __name__ == "__main__":
    app = BaccaratBotGUI()
    app.mainloop()
