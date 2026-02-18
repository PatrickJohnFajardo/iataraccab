import pyautogui
import json
import time
import sys
from utils import logger
from PIL import Image

CONFIG_FILE = 'config.json'

def get_coordinate(label, wait_func=input):
    """
    Prompts the user to hover over a target and records coordinates.
    Uses wait_func to wait for user confirmation.
    """
    logger.log(f"Calibrating: {label}", "INFO")
    logger.log(f"Please hover your mouse over {label} and press 'Next/Space'.", "WARNING")
    
    wait_func("Press Enter/Space when ready...")
    
    x, y = pyautogui.position()
    logger.log(f"Recorded {label} at ({x}, {y})", "SUCCESS")
    return {"x": x, "y": y}

def get_region(label, wait_func=input):
    """
    Prompts user to define a region (Top-Left and Bottom-Right).
    """
    logger.log(f"Calibrating Region: {label}", "INFO")
    
    logger.log(f"Step 1: Hover over TOP-LEFT of {label} and press 'Next/Space'.", "WARNING")
    wait_func("Wait for top-left...")
    tl_x, tl_y = pyautogui.position()
    logger.log(f"Top-Left recorded at ({tl_x}, {tl_y})", "SUCCESS")
    
    logger.log(f"Step 2: Hover over BOTTOM-RIGHT of {label} and press 'Next/Space'.", "WARNING")
    wait_func("Wait for bottom-right...")
    br_x, br_y = pyautogui.position()
    logger.log(f"Bottom-Right recorded at ({br_x}, {br_y})", "SUCCESS")
    
    width = br_x - tl_x
    height = br_y - tl_y
    
    if width <= 0 or height <= 0:
        logger.log("Invalid region dimensions!", "ERROR")
        return None
        
    return {"x": tl_x, "y": tl_y, "width": width, "height": height}

def capture_color_baseline(coords, label):
    """
    Captures a small screenshot at the coordinate to establish baseline color.
    For buttons, we might want to capture a small 5x5 region around the center.
    """
    # Capture a small region around the click point
    region = (coords['x'] - 2, coords['y'] - 2, 5, 5)
    try:
        img = pyautogui.screenshot(region=region)
        # Get the center pixel color
        pixel = img.getpixel((2, 2))
        logger.log(f"Baseline color for {label}: {pixel}", "INFO")
        return pixel
    except Exception as e:
        logger.log(f"Failed to capture color for {label}: {e}", "ERROR")
        return (0, 0, 0)

def main(wait_func=input):
    logger.log("Starting Calibration Phase...", "INFO")
    logger.log("HINT: You can use the GUI 'Next' button or SPACE key (if bound).", "DEBUG")
    config = {}
    
    # 1. Capture Targets
    config['target_a'] = get_coordinate("Target A (Banker)", wait_func)
    config['target_b'] = get_coordinate("Target B (Player)", wait_func)
    config['target_c'] = get_coordinate("Target C (Tie)", wait_func)
    
    # 2. Capture Regions
    config['status_region_main'] = get_region("Main Status Region", wait_func)
    config['status_region_tie'] = get_region("Tie Status Region", wait_func)
    config['status_region_balance'] = get_region("Balance Status Region", wait_func)
    
    if not config['status_region_main'] or not config['status_region_tie'] or not config['status_region_balance']:
        logger.log("Region calibration failed.", "ERROR")
        return
        
    # 3. Chip Calibration
    logger.log("--- Calibrating Chips ---", "INFO")
    chips = {}
    chip_values = [10, 50, 100, 250, 500, 1000, 5000, 10000]
    
    for val in chip_values:
        config['chips'] = chips # Update mid-loop for partial saves if needed
        chips[str(val)] = get_coordinate(f"Chip [{val}]", wait_func)
    
    config['chips'] = chips

    # 4. Color Baselines
    logger.log("--- Capturing Color Baselines ---", "INFO")
    logger.log("Ensure buttons are currently CLICKABLE.", "WARNING")
    wait_func("Wait for color capture...")
    
    config['target_a']['color'] = capture_color_baseline(config['target_a'], "Target A")
    config['target_b']['color'] = capture_color_baseline(config['target_b'], "Target B")
    config['target_c']['color'] = capture_color_baseline(config['target_c'], "Target C")

    # 5. Save to JSON
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
        
    logger.log(f"Calibration complete. Configuration saved.", "SUCCESS")

if __name__ == "__main__":
    main()
