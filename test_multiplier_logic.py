def calculate_bet(current_bet, pattern, pattern_index, actual_result, martingale_level=0, strategy="Standard"):
    strategies = {
        "Standard": [2] * 20,
        "Sweeper": [3, 3, 3, 2, 2, 2, 2, 2, 2, 2]
    }
    
    if actual_result == "WIN":
        return 10, (pattern_index + 1) % len(pattern), 0
    elif actual_result == "LOSS":
        current_target_char = pattern[pattern_index]
        has_consecutive_bankers = "BB" in pattern
        
        if current_target_char == 'B' and has_consecutive_bankers:
            new_bet = math.ceil(current_bet * 2.11 / 10) * 10
            return new_bet, (pattern_index + 1) % len(pattern), martingale_level + 1
        else:
            multipliers = strategies.get(strategy, strategies["Standard"])
            if martingale_level < len(multipliers):
                multiplier = multipliers[martingale_level]
                new_bet = int(current_bet * multiplier)
            else:
                new_bet = current_bet * 2
            return new_bet, (pattern_index + 1) % len(pattern), martingale_level + 1
    return current_bet, pattern_index, martingale_level

# Test Case: Sweeper Strategy Transition
print("Testing Sweeper Strategy Transition (PPPB)")
pattern = "PPPB"
bet = 10
m_level = 0
p_idx = 0

for i in range(5):
    side = pattern[p_idx]
    old_bet = bet
    bet, p_idx, m_level = calculate_bet(bet, pattern, p_idx, "LOSS", m_level, "Sweeper")
    print(f"Loss {i+1}: Side {side}, Martingale Level {m_level}, Bet: {old_bet} -> {bet} (multiplier {bet/old_bet if old_bet > 0 else 'N/A'}x)")
