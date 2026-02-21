import math

def calculate_bet(current_bet, pattern, pattern_index, actual_result, strategy="Standard"):
    strategies = {
        "Standard": [2] * 20
    }
    
    if actual_result == "WIN":
        return 10, (pattern_index + 1) % len(pattern)
    elif actual_result == "LOSS":
        current_target_char = pattern[pattern_index]
        has_consecutive_bankers = "BB" in pattern
        
        if current_target_char == 'B' and has_consecutive_bankers:
            new_bet = math.ceil(current_bet * 2.11 / 10) * 10
            print(f"DEBUG: 2.11x Applied! Side: {current_target_char}, Pattern: {pattern}")
            return new_bet, (pattern_index + 1) % len(pattern)
        else:
            multipliers = strategies.get(strategy, strategies["Standard"])
            multiplier = multipliers[0] # simplified for test
            new_bet = int(current_bet * multiplier)
            print(f"DEBUG: Standard Multiplier ({multiplier}x) Applied. Side: {current_target_char}, Pattern: {pattern}")
            return new_bet, (pattern_index + 1) % len(pattern)
    return current_bet, pattern_index

# Test Case 1: PPPB (Single Banker)
print("Test Case 1: PPPB")
calculate_bet(10, "PPPB", 3, "LOSS") # Should be Standard (2x)

# Test Case 2: BBBP (Consecutive Bankers)
print("\nTest Case 2: BBBP")
calculate_bet(10, "BBBP", 0, "LOSS") # Should be 2.11x

# Test Case 3: PPBB (Consecutive Bankers)
print("\nTest Case 3: PPBB")
calculate_bet(10, "PPBB", 2, "LOSS") # Should be 2.11x
