import pyautogui
import pytesseract
import json
import os
import numpy as np
from PIL import Image

def test_ocr():
    # Setup Tesseract path
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    
    # Load config
    if not os.path.exists('config.json'):
        print("Config file not found!")
        return
        
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    print("--- Starting OCR Debugging ---")
    
    # 1. Test Balance OCR
    if 'status_region_balance' in config:
        print("\nChecking Balance Region...")
        reg = config['status_region_balance']
        img = pyautogui.screenshot(region=(reg['x'], reg['y'], reg['width'], reg['height']))
        img.save('debug_balance.png')
        text = pytesseract.image_to_string(img.convert('L')).strip()
        print(f"RAW Text detected: '{text}'")
        clean_text = "".join(c for c in text if c.isdigit() or c == '.')
        print(f"CLEANED Balance: '{clean_text}'")
    
    # 2. Test Main Status (BANKER/PLAYER)
    if 'status_region_main' in config:
        print("\nChecking Main Status Region...")
        reg = config['status_region_main']
        img = pyautogui.screenshot(region=(reg['x'], reg['y'], reg['width'], reg['height']))
        img.save('debug_main_status.png')
        text = pytesseract.image_to_string(img.convert('L')).strip().lower()
        print(f"Text detected: '{text}'")
        if "banker" in text: print("-> Detected: BANKER")
        elif "player" in text: print("-> Detected: PLAYER")
        else: print("-> No standard status detected.")

    # 3. Test Tie Recognition
    if 'status_region_tie' in config:
        print("\nChecking Tie Region...")
        reg = config['status_region_tie']
        img = pyautogui.screenshot(region=(reg['x'], reg['y'], reg['width'], reg['height']))
        img.save('debug_tie.png')
        
        # Color Analysis
        np_img = np.array(img)
        avg_color = np_img.mean(axis=(0, 1))
        r, g, b = avg_color
        print(f"Avg Color: R={r:.1f}, G={g:.1f}, B={b:.1f}")
        
        green_mask = (g > r + 10) and (g > b + 10) and (g > 80)
        print(f"Color Mask (is it green enough?): {green_mask}")
        
        # OCR with thresholding (as used in bot_logic.py)
        processed = img.convert('L').point(lambda p: p > 150 and 255)
        processed.save('debug_tie_processed.png')
        text = pytesseract.image_to_string(processed).strip().lower()
        print(f"OCR Text detected: '{text}'")
        if "tie" in text or green_mask:
            print("-> TIE SYSTEM WOULD TRIGGER")
        else:
            print("-> TIE SYSTEM WOULD NOT TRIGGER")

    print("\n--- Debug Complete ---")
    print("Debug images have been saved to the project folder.")

if __name__ == "__main__":
    test_ocr()
