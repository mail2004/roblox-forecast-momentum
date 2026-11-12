#!/usr/bin/env python3
"""
ROBLOX UP-AND-COMING FORECAST — MOMENTUM MODEL
Target: Beat house baseline (-37.2 nats) → TOP 1 ($100)

Strategy:
1. Chart 76% volatile → baseline persistence FAILS
2. Momentum model: rising games get MORE prob, falling get LESS
3. Recency weighting: last 3-5 reads matter most
4. Exponential decay for older history
5. Normalize probabilities per place (sum to 1.0)
"""

import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import math

# I/O paths
INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

def load_history():
    """Load chart history from input/history.ndjson"""
    history_file = INPUT_DIR / "history.ndjson"
    history = []
    with open(history_file, 'r') as f:
        for line in f:
            history.append(json.loads(line.strip()))
    return history

def load_task():
    """Load task params from input/task.json"""
    task_file = INPUT_DIR / "task.json"
    with open(task_file, 'r') as f:
        return json.load(f)

def calculate_momentum_scores(history, recency_window=5, decay_factor=0.7):
    """
    Calculate momentum scores for each game based on:
    - Position trajectory (rising = higher score, falling = lower)
    - Recency weighting (last N reads matter most)
    - Player count growth
    
    Returns: {universe_id: momentum_score}
    """
    game_positions = defaultdict(list)  # {uid: [(timestamp, position, playing)]}
    
    # Collect position history
    for read in history:
        for i, game in enumerate(read['up_and_coming'], 1):
            game_positions[game['universe_id']].append({
                'timestamp': read['at'],
                'position': i,
                'playing': game['playing']
            })
    
    momentum = {}
    
    for uid, pos_history in game_positions.items():
        if len(pos_history) < 2:
            # New game — neutral momentum
            momentum[uid] = 1.0
            continue
        
        # Take last N reads (recency window)
        recent = pos_history[-recency_window:]
        
        # Calculate weighted momentum
        # Rising (position getting LOWER number) = positive momentum
        # Falling (position getting HIGHER number) = negative momentum
        
        position_changes = []
        player_changes = []
        
        for i in range(1, len(recent)):
            prev = recent[i-1]
            curr = recent[i]
            
            # Position change (negative = rising)
            pos_delta = curr['position'] - prev['position']
            position_changes.append(-pos_delta)  # Invert: rising = positive
            
            # Player count change
            if prev['playing'] > 0:
                player_pct = (curr['playing'] - prev['playing']) / prev['playing']
                player_changes.append(player_pct)
        
        # Exponential decay weights (more recent = more weight)
        weights = [decay_factor ** (len(position_changes) - i - 1) 
                   for i in range(len(position_changes))]
        total_weight = sum(weights)
        
        # Weighted average momentum
        if total_weight > 0:
            avg_pos_momentum = sum(w * c for w, c in zip(weights, position_changes)) / total_weight
            avg_player_momentum = sum(w * c for w, c in zip(weights, player_changes)) / len(player_changes) if player_changes else 0
            
            # Combine position & player momentum (position weighs more)
            combined = 0.7 * avg_pos_momentum + 0.3 * avg_player_momentum
            
            # Convert to score (1.0 = neutral, >1 = rising, <1 = falling)
            # Scale: +5 position gain = 2x prob, -5 = 0.5x prob
            momentum[uid] = max(0.1, 1.0 + combined * 0.2)
        else:
            momentum[uid] = 1.0
    
    return momentum

def generate_forecast(history, task):
    """Generate probabilistic forecast for top 10 places"""
    
    # Get last chart state
    last_read = history[-1]
    last_chart = last_read['up_and_coming']
    places = task['places']  # Should be 10
    
    # Calculate momentum scores
    momentum = calculate_momentum_scores(history)
    
    # Build probability distribution for each place
    probabilities = []
    top10_candidates = []
    
    for place in range(1, places + 1):
        # For each place, consider games from current top 15
        # (top 10 + 5 rising challengers)
        candidates = last_chart[:15]
        
        # Base probabilities from current positions
        # Place k: high prob for game at k, moderate for k±1, k±2
        place_probs = {}
        
        for i, game in enumerate(candidates, 1):
            uid = game['universe_id']
            
            # Distance from target place
            distance = abs(i - place)
            
            # Base probability (closer = higher)
            if distance == 0:
                base_prob = 0.5
            elif distance == 1:
                base_prob = 0.15
            elif distance == 2:
                base_prob = 0.08
            elif distance == 3:
                base_prob = 0.04
            else:
                base_prob = 0.02
            
            # Apply momentum multiplier
            momentum_score = momentum.get(uid, 1.0)
            adjusted_prob = base_prob * momentum_score
            
            place_probs[uid] = adjusted_prob
        
        # Normalize to sum ~0.80 (leave 0.20 for unnamed games)
        total = sum(place_probs.values())
        if total > 0:
            scale = 0.80 / total
            for uid in place_probs:
                place_probs[uid] *= scale
        
        # Sort by probability and take top candidates for this place
        sorted_candidates = sorted(place_probs.items(), key=lambda x: x[1], reverse=True)
        
        # Add to probabilities list (top 5 per place to stay under 100 row limit)
        for uid, prob in sorted_candidates[:5]:
            if prob >= 0.01:  # Filter noise
                probabilities.append({
                    "universe_id": uid,
                    "place": place,
                    "p": round(prob, 6)
                })
    
    # Generate top10 guess (highest momentum * current position)
    top10_scores = {}
    for game in last_chart[:15]:
        uid = game['universe_id']
        # Score = (inverse position) * momentum
        position_score = 1.0 / game['rank']
        momentum_score = momentum.get(uid, 1.0)
        top10_scores[uid] = position_score * momentum_score
    
    sorted_top10 = sorted(top10_scores.items(), key=lambda x: x[1], reverse=True)
    top10 = [uid for uid, score in sorted_top10[:10]]
    
    return {
        "probabilities": probabilities,
        "top10": top10
    }

def main():
    """Main entry point"""
    print("🎯 ROBLOX FORECAST — MOMENTUM MODEL")
    print("=" * 60)
    
    # Load inputs
    history = load_history()
    task = load_task()
    
    print(f"✓ Loaded {len(history)} history reads")
    print(f"✓ Forecast window: {task['window']['from']} → {task['window']['until']}")
    print(f"✓ Places to forecast: {task['places']}")
    
    # Generate forecast
    print("\n→ Calculating momentum scores...")
    forecast = generate_forecast(history, task)
    
    print(f"✓ Generated {len(forecast['probabilities'])} probability rows")
    print(f"✓ Top 10 guess: {forecast['top10'][:3]}... ({len(forecast['top10'])} games)")
    
    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "forecast.json"
    
    with open(output_file, 'w') as f:
        json.dump(forecast, f, indent=2)
    
    print(f"\n✓ Forecast written: {output_file}")
    print("=" * 60)
    print("💰 Target: Beat baseline (-37.2 nats) → TOP 1 placement")

if __name__ == "__main__":
    main()
