"""
ML-based scoring for Super Hard Card Game.

Trains a neural network to predict win probability from game state,
replacing the hand-crafted Evaluator.evaluate() heuristic.

Usage:
    python ml_scoring.py collect [--games N] [--output PATH]
    python ml_scoring.py preprocess [--data PATH] [--output PATH]
    python ml_scoring.py train [--data PATH] [--model PATH] [--epochs N] [--device auto|cpu|cuda]
    python ml_scoring.py test [--data PATH] [--model PATH] [--validation-split F] [--device auto|cpu|cuda]
    python ml_scoring.py info [--model PATH]

Requires: torch (PyTorch)
"""

import json
import os
import random
import argparse
from typing import Optional

import cards
from ai_player_new import (
    GameStateSnapshot,
    GameSimulator,
    MinimaxAI,
    Evaluator,
    MAX_FIELD_SIZE,
    MAX_HAND_SIZE,
)

# ============================================================
# Card ID Mapping
# ============================================================

# Build a stable mapping: card class name -> integer ID.
# Index 0 is reserved for "empty slot."
# The order follows cards.all_card_types (sorted by type/cost/name)

CARD_NAME_TO_ID: dict[str, int] = {}
for _i, _cls in enumerate(cards.all_card_types, start=1):
    CARD_NAME_TO_ID[_cls.__name__] = _i
NUM_CARD_TYPES = len(CARD_NAME_TO_ID) + 1  # +1 for empty slot (index 0)
EMPTY_CARD_ID = 0

# ============================================================
# Feature Extraction
# ============================================================

# Layout constants
_FIELD_SLOTS = MAX_FIELD_SIZE  # 5 per player
_HAND_SLOTS = MAX_HAND_SIZE    # 9 per player
_GRAVEYARD_SLOTS = 60          # per player (card IDs only)
_BANISHED_SLOTS = 60           # per player (card IDs only)
_DECK_SLOTS = 60               # per player (card IDs only)

# Total card ID slots: field + hand (with numeric) + graveyard + banished + deck (IDs only)
NUM_CARD_SLOTS = (
    (_FIELD_SLOTS + _HAND_SLOTS) * 2               # 28 (field + hand, both players)
    + (_GRAVEYARD_SLOTS + _BANISHED_SLOTS + _DECK_SLOTS) * 2  # 360 (gy + banish + deck, both players)
)  # 388 total

# Per-slot numeric features
_FIELD_NUMERIC_PER_SLOT = 23  # see _encode_field_slot
_HAND_NUMERIC_PER_SLOT = 13   # see _encode_hand_slot
_GLOBAL_NUMERIC = 20

NUM_NUMERIC_FEATURES = (
    _GLOBAL_NUMERIC
    + _FIELD_SLOTS * 2 * _FIELD_NUMERIC_PER_SLOT
    + _HAND_SLOTS * 2 * _HAND_NUMERIC_PER_SLOT
)  # 20 + 230 + 234 = 484


def _encode_field_slot(card: Optional[cards.Card]) -> tuple[int, list[float]]:
    """Encode a single field slot. Returns (card_id, numeric_features[23])."""
    if card is None:
        return EMPTY_CARD_ID, [0.0] * _FIELD_NUMERIC_PER_SLOT

    card_id = CARD_NAME_TO_ID.get(card.__class__.__name__, EMPTY_CARD_ID)

    if isinstance(card, cards.Follower):
        numeric = [
            1.0,                                        # 0  is_occupied
            1.0,                                        # 1  is_follower
            0.0,                                        # 2  is_amulet
            card.attack / 30.0,                         # 3  attack
            card.hp / 30.0,                             # 4  hp
            card.max_hp / 30.0,                         # 5  max_hp
            card.original_cost / 10.0,                  # 6  original_cost
            card.cost / 10.0,                           # 7  cost
            float(card.ability_protect),                # 8  protect
            float(card.ability_drain),                  # 9  drain
            float(card.ability_lethal),                 # 10 lethal
            float(card.ability_rush),                   # 11 rush
            float(card.ability_super_rush),             # 12 super_rush
            float(card.can_attack_this_turn),           # 13 can_attack
            card.attack_ability / 2.0,                  # 14 attack_ability (0/1/2)
            float(card.is_enhanced),                    # 15 is_enhanced
            float(card.summoned_this_turn),             # 16 summoned_this_turn
            float(card.can_enhance),                    # 17 can_enhance
            card.how_many_attacks_max_of_turn / 3.0,    # 18 attacks_max_per_turn
            card.how_many_attacks_done_of_turn / 3.0,   # 19 attacks_done_this_turn
            0.0,                                        # 20 amulet_counter (N/A)
            0.0,                                        # 21 amulet_counter_max (N/A)
            len(card.extra_effect_list) / 5.0,          # 22 extra_effect_count (normalized to max 5)
        ]
    elif isinstance(card, cards.Amulet):
        numeric = [
            1.0,                                        # 0  is_occupied
            0.0,                                        # 1  is_follower
            1.0,                                        # 2  is_amulet
            0.0,                                        # 3  attack (N/A)
            0.0,                                        # 4  hp (N/A)
            0.0,                                        # 5  max_hp (N/A)
            card.original_cost / 10.0,                  # 6  original_cost
            card.cost / 10.0,                           # 7  cost
            0.0,                                        # 8  protect (N/A)
            0.0,                                        # 9  drain (N/A)
            0.0,                                        # 10 lethal (N/A)
            0.0,                                        # 11 rush (N/A)
            0.0,                                        # 12 super_rush (N/A)
            0.0,                                        # 13 can_attack (N/A)
            0.0,                                        # 14 attack_ability (N/A)
            0.0,                                        # 15 is_enhanced (N/A)
            0.0,                                        # 16 summoned_this_turn (N/A)
            0.0,                                        # 17 can_enhance (N/A)
            0.0,                                        # 18 attacks_max (N/A)
            0.0,                                        # 19 attacks_done (N/A)
            card.counter / 10.0,                        # 20 amulet_counter
            card.counter_max / 10.0,                    # 21 amulet_counter_max
            len(card.extra_effect_list) / 5.0,          # 22 extra_effect_count (normalized to max 5)
        ]
    else:
        raise Exception(f"Unexpected card type on field: {card.__class__.__name__}")
        # return EMPTY_CARD_ID, [0.0] * _FIELD_NUMERIC_PER_SLOT

    return card_id, numeric


def _encode_hand_slot(card: Optional[cards.Card]) -> tuple[int, list[float]]:
    """Encode a single hand slot. Returns (card_id, numeric_features)."""
    if card is None:
        return EMPTY_CARD_ID, [0.0] * _HAND_NUMERIC_PER_SLOT

    card_id = CARD_NAME_TO_ID.get(card.__class__.__name__, EMPTY_CARD_ID)

    is_follower = isinstance(card, cards.Follower)
    is_amulet = isinstance(card, cards.Amulet)
    is_spell = isinstance(card, cards.Spell)

    numeric = [
        1.0,                                            # 0  is_occupied
        float(is_follower),                             # 1  is_follower
        float(is_amulet),                               # 2  is_amulet
        float(is_spell),                                # 3  is_spell
        card.cost / 10.0,                               # 4  cost
        card.original_cost / 10.0,                      # 5  original_cost
        card.attack / 30.0 if is_follower else 0.0,     # 6  attack (followers only)
        card.hp / 30.0 if is_follower else 0.0,         # 7  hp (followers only)
        float(card.can_enhance) if is_follower else 0.0,  # 8  can_enhance
        float(card.ability_protect) if is_follower else 0.0,  # 9  protect
        float(card.ability_drain) if is_follower else 0.0,    # 10 drain
        float(card.ability_lethal) if is_follower else 0.0,   # 11 lethal
        len(card.extra_effect_list) / 5.0,                     # 12 extra_effect_count (normalized to max 5)
    ]
    return card_id, numeric


def _encode_zone_card_ids(
    zone: list[cards.Card], max_slots: int
) -> list[int]:
    """Encode card IDs for a zone (graveyard/banished/deck). No numeric features."""
    ids: list[int] = []
    for i in range(max_slots):
        if i < len(zone):
            ids.append(CARD_NAME_TO_ID.get(zone[i].__class__.__name__, EMPTY_CARD_ID))
        else:
            ids.append(EMPTY_CARD_ID)
    return ids


def extract_features(
    snapshot: GameStateSnapshot, player: int
) -> tuple[list[int], list[float]]:
    """
    Extract features from a game state, from `player`'s perspective.

    Returns:
        card_ids:  list of int,   length NUM_CARD_SLOTS  (388)
        numeric:   list of float, length NUM_NUMERIC_FEATURES (484)
    """
    opponent = 3 - player
    card_ids: list[int] = []
    numeric: list[float] = []

    # --- Global features (20) ---
    numeric.extend([
        snapshot.turn / 30.0,                                    
        snapshot.hp[player] / 30.0,                               
        snapshot.hp[opponent] / 30.0,                               
        snapshot.max_hp[player] / 30.0,                             
        snapshot.max_hp[opponent] / 30.0,                             
        # snapshot.foxtail[player] / 9.0,                              
        # snapshot.foxtail[opponent] / 9.0,                            
        # no need for foxtail features as in end state, it is always 0 and 9 respectively
        len(snapshot.hands[player]) / 9.0,                            
        len(snapshot.hands[opponent]) / 9.0,                           
        len(snapshot.decks[player]) / 40.0,                            
        len(snapshot.decks[opponent]) / 40.0,                           
        len(snapshot.graveyard[player]) / 40.0,                        
        len(snapshot.graveyard[opponent]) / 40.0,                       
        len(snapshot.fields[player]) / 5.0,                             
        len(snapshot.fields[opponent]) / 5.0,                           
        len(snapshot.banished[player]) / 40.0,                         
        len(snapshot.banished[opponent]) / 40.0,                        
        float(snapshot.current_player == player),                       
        snapshot.enhance_used_this_turn[player] / 3.0,                  
        snapshot.enhance_used_this_turn[opponent] / 3.0,                
        snapshot.max_enhance_allowed_per_turn[player] / 3.0,            
        snapshot.amount_card_generated_from_void[player] / 10.0,        
    ])

    # --- Field features (player then opponent, 5 slots each) ---
    for p in [player, opponent]:
        field = snapshot.fields[p]
        for i in range(_FIELD_SLOTS):
            card = field[i] if i < len(field) else None
            cid, nums = _encode_field_slot(card)
            card_ids.append(cid)
            numeric.extend(nums)

    # --- Hand features (player then opponent, 9 slots each) ---
    for p in [player, opponent]:
        hand = snapshot.hands[p]
        for i in range(_HAND_SLOTS):
            card = hand[i] if i < len(hand) else None
            cid, nums = _encode_hand_slot(card)
            card_ids.append(cid)
            numeric.extend(nums)

    # --- Graveyard card IDs (player then opponent, 60 slots each) ---
    for p in [player, opponent]:
        card_ids.extend(_encode_zone_card_ids(snapshot.graveyard[p], _GRAVEYARD_SLOTS))

    # --- Banished card IDs (player then opponent, 60 slots each) ---
    for p in [player, opponent]:
        card_ids.extend(_encode_zone_card_ids(snapshot.banished[p], _BANISHED_SLOTS))

    # --- Deck card IDs (player then opponent, 60 slots each) ---
    for p in [player, opponent]:
        card_ids.extend(_encode_zone_card_ids(snapshot.decks[p], _DECK_SLOTS))

    return card_ids, numeric


# ============================================================
# Model Definition
# ============================================================

def _import_torch():
    """Import torch lazily so the rest of the module works without it."""
    try:
        import torch
        import torch.nn as nn
        return torch, nn
    except ImportError:
        raise ImportError(
            "PyTorch is required for ML scoring. Install with: pip install torch"
        )


def _select_device(device: str = "auto"):
    """
    Resolve and return the torch device for training/inference.

    Args:
        device: "auto", "cpu", or "cuda".
            - auto: use CUDA/ROCm GPU if available, else CPU
            - cuda: force CUDA/ROCm GPU (falls back to CPU with warning if unavailable)
            - cpu: force CPU
    """
    torch, _ = _import_torch()

    normalized = (device or "auto").strip().lower()
    if normalized not in {"auto", "cpu", "cuda"}:
        print(f"WARNING: Unknown device '{device}'. Falling back to auto.")
        normalized = "auto"

    if normalized == "cpu":
        print("Using device: cpu")
        return torch.device("cpu")

    cuda_available = torch.cuda.is_available()
    if normalized == "cuda":
        if cuda_available:
            if getattr(torch.version, "hip", None):
                print(f"Using device: cuda (ROCm/hip {torch.version.hip})")
            else:
                print(f"Using device: cuda ({torch.cuda.get_device_name(0)})")
            return torch.device("cuda")
        print("WARNING: --device cuda requested but no CUDA/ROCm GPU available. Using cpu.")
        return torch.device("cpu")

    # auto mode
    if cuda_available:
        if getattr(torch.version, "hip", None):
            print(f"Using device: cuda (ROCm/hip {torch.version.hip})")
        else:
            print(f"Using device: cuda ({torch.cuda.get_device_name(0)})")
        return torch.device("cuda")

    print("Using device: cpu")
    return torch.device("cpu")


def create_model(num_card_types: int = NUM_CARD_TYPES,
                 embedding_dim: int = 16,
                 hidden_dim: int = 256):
    """Create and return a ScoringModel instance."""
    torch, nn = _import_torch()

    class ScoringModel(nn.Module):
        """
        Predicts win probability from end game state.

        Input:
            card_ids:  (batch, NUM_CARD_SLOTS)   - integer card type indices
            numeric:   (batch, NUM_NUMERIC_FEATURES) - normalized float features

        Output:
            (batch, 1) - win probability in [0, 1]
        """
        def __init__(self):
            super().__init__()
            self.embedding = nn.Embedding(num_card_types, embedding_dim)

            input_dim = NUM_CARD_SLOTS * embedding_dim + NUM_NUMERIC_FEATURES
            self.network = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim // 2, hidden_dim // 4),
                nn.ReLU(),
                nn.Linear(hidden_dim // 4, 1),
                nn.Sigmoid(),
            )

        def forward(self, card_ids_tensor, numeric_tensor):
            emb = self.embedding(card_ids_tensor)                 # (B, 118, E)
            emb_flat = emb.view(emb.size(0), -1)                 # (B, 118*E)
            x = torch.cat([emb_flat, numeric_tensor], dim=1)      # (B, 118*E + N)
            return self.network(x)                                 # (B, 1)

    return ScoringModel()


# ============================================================
# Data Collection
# ============================================================

def _collect_single_game(
    deck1_recipe: Optional[dict[str, int]],
    deck2_recipe: Optional[dict[str, int]],
    ai_cuets: int = 2,
    ai_max_states: int = 4,
    max_turns: int = 200,
) -> list[dict]:
    """
    Play one full game with the existing heuristic AI and collect
    (state, perspective_player, outcome) samples at each turn boundary.

    Returns a list of sample dicts ready for serialization.
    """
    from simulate_games import (
        create_deck,
        create_game_state_with_decks,
        get_ai_actions,
        get_random_ai_actions,
        apply_action,
    )

    deck1 = create_deck(deck1_recipe)
    deck2 = create_deck(deck2_recipe)
    state = create_game_state_with_decks(deck1, deck2)

    ai1 = MinimaxAI(
        player_number=1,
        cuets_player_turn=ai_cuets,
        cuets_opp_turn=ai_cuets // 2,
        unique_states_max_player_turn=ai_max_states,
        unique_states_max_opp_turn=ai_max_states // 2
    )
    ai2 = MinimaxAI(
        player_number=2,
        cuets_player_turn=ai_cuets,
        cuets_opp_turn=ai_cuets // 2,
        unique_states_max_player_turn=ai_max_states,
        unique_states_max_opp_turn=ai_max_states // 2
    )

    ais = {1: ai1, 2: ai2}
    snapshots: list[tuple[int, list[int], list[float]]] = []  # (perspective_player, card_ids, numeric)

    while not state.concluded and state.turn <= max_turns:
        current_player = state.current_player
        ai = ais[current_player]

        # actions = get_ai_actions(ai, state)
        actions = get_random_ai_actions(ai, state)

        for action in actions:
            if action[0] == 'end_turn':
                break
            apply_action(state, current_player, action)
            if state.concluded:
                break

        if not state.concluded:
            GameSimulator.end_turn(state)

        for p in [1, 2]:
            cids, nums = extract_features(state, p)
            snapshots.append((p, cids, nums))

    # Label all snapshots with outcome
    winner = state.winner
    samples = []
    for perspective_player, cids, nums in snapshots:
        if winner is None:
            label = 0.5  # draw
        elif winner == perspective_player:
            label = 1.0  # win
        else:
            label = 0.0  # loss
        samples.append({
            "card_ids": cids,
            "numeric": nums,
            "label": label,
        })

    return samples


def collect_training_data(
    num_games: int,
    output_path: str,
    ai_cuets: int = 2,
    ai_max_states: int = 4,
    max_turns: int = 200,
):
    """
    Run num_games simulated games and save training data to output_path (JSONL).
    Uses all saved decks in round-robin matchups, plus random decks.
    """
    from simulate_games import load_saved_decks

    saved_decks = load_saved_decks()
    deck_names = list(saved_decks.keys())
    deck_recipes: list[Optional[dict[str, int]]] = [saved_decks[n] for n in deck_names]

    # Add None for random decks
    if len(deck_recipes) < 2:
        deck_recipes.extend([None, None])
    elif len(deck_recipes) < 4:
        deck_recipes.append(None)

    total_samples = 0
    with open(output_path, "w", encoding="utf-8") as f:
        for game_i in range(num_games):
            # Pick two random decks (can be the same recipe - different shuffle)
            r1 = random.choice(deck_recipes)
            r2 = random.choice(deck_recipes)

            try:
                samples = _collect_single_game(
                    r1, r2,
                    ai_cuets=ai_cuets,
                    ai_max_states=ai_max_states,
                    max_turns=max_turns,
                )
                for sample in samples:
                    f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                total_samples += len(samples)
            except Exception as e:
                print(f"  Game {game_i + 1}: ERROR - {e}")
                continue

            if (game_i + 1) % 10 == 0 or game_i == 0:
                print(f"  Game {game_i + 1}/{num_games} done, {total_samples} samples so far")

    print(f"Data collection complete: {num_games} games, {total_samples} samples")
    print(f"Saved to: {output_path}")

    # Save the card ID mapping alongside the data
    mapping_path = output_path.rsplit(".", 1)[0] + "_card_map.json"
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(CARD_NAME_TO_ID, f, ensure_ascii=False, indent=2)
    print(f"Card mapping saved to: {mapping_path}")


# ============================================================
# Data Preprocessing & Loading
# ============================================================

def preprocess_data(jsonl_path: str, output_path: str):
    """
    Convert JSONL training data to compact binary .pt format.

    Reads the JSONL line by line using numpy arrays to avoid the massive
    memory overhead of Python lists. Peak memory is ~5-6 GB per 1M samples
    instead of ~30 GB with the raw Python list approach.
    """
    import numpy as np
    torch, _ = _import_torch()

    # Pass 1: count lines and validate first sample
    print(f"Counting samples in {jsonl_path}...")
    n = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if n == 0:
                sample = json.loads(line)
                if len(sample["card_ids"]) != NUM_CARD_SLOTS:
                    raise ValueError(
                        f"card_ids length mismatch: got {len(sample['card_ids'])}, "
                        f"expected {NUM_CARD_SLOTS}. Re-run collect."
                    )
                if len(sample["numeric"]) != NUM_NUMERIC_FEATURES:
                    raise ValueError(
                        f"numeric length mismatch: got {len(sample['numeric'])}, "
                        f"expected {NUM_NUMERIC_FEATURES}. Re-run collect."
                    )
            n += 1

    if n == 0:
        print("No data found.")
        return

    print(f"Found {n} samples. Pre-allocating arrays...")
    # Use int16 for card IDs during processing (values are small),
    # converted to int64 at save time.
    card_ids_arr = np.zeros((n, NUM_CARD_SLOTS), dtype=np.int16)
    numeric_arr = np.zeros((n, NUM_NUMERIC_FEATURES), dtype=np.float32)
    labels_arr = np.zeros(n, dtype=np.float32)

    # Pass 2: fill arrays
    print("Parsing data...")
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            sample = json.loads(line)
            card_ids_arr[i] = sample["card_ids"]
            numeric_arr[i] = sample["numeric"]
            labels_arr[i] = sample["label"]
            if (i + 1) % 100000 == 0:
                print(f"  {i + 1}/{n} samples processed")

    print("Converting to tensors and saving...")
    # Keep card_ids as int16 — values are small (<200 card types).
    # Cast to int64 (torch.long) only per-batch during training to avoid 4x memory waste.
    card_ids_tensor = torch.from_numpy(card_ids_arr)  # stays int16
    del card_ids_arr
    numeric_tensor = torch.from_numpy(numeric_arr)
    del numeric_arr
    labels_tensor = torch.from_numpy(labels_arr)
    del labels_arr

    save_data = {
        "card_ids": card_ids_tensor,
        "numeric": numeric_tensor,
        "labels": labels_tensor,
        "num_samples": n,
        "num_card_slots": NUM_CARD_SLOTS,
        "num_numeric_features": NUM_NUMERIC_FEATURES,
    }
    torch.save(save_data, output_path)
    print(f"Preprocessed data saved to: {output_path} ({n} samples)")


def _load_data(
    data_path: str,
) -> tuple:
    """
    Load training/test data from either .pt (preprocessed) or .jsonl (raw).

    Returns (card_ids_tensor, numeric_tensor, labels_tensor).
    card_ids_tensor is int16 to save memory; callers must cast to long per-batch.
    labels_tensor has shape (N, 1).
    """
    import numpy as np
    torch, _ = _import_torch()

    if data_path.endswith(".pt"):
        print(f"Loading preprocessed data from {data_path}...")
        data = torch.load(data_path, weights_only=False)
        saved_slots = data.get("num_card_slots")
        saved_numeric = data.get("num_numeric_features")
        if saved_slots != NUM_CARD_SLOTS:
            raise ValueError(
                f"Preprocessed card_ids slots mismatch: got {saved_slots}, "
                f"expected {NUM_CARD_SLOTS}. Re-run preprocess."
            )
        if saved_numeric != NUM_NUMERIC_FEATURES:
            raise ValueError(
                f"Preprocessed numeric features mismatch: got {saved_numeric}, "
                f"expected {NUM_NUMERIC_FEATURES}. Re-run preprocess."
            )
        card_ids_tensor = data["card_ids"]
        # Convert old int64 format to int16 to save ~4x memory
        if card_ids_tensor.dtype == torch.int64:
            print("  Converting card_ids from int64 to int16 (saving memory)...")
            card_ids_tensor = card_ids_tensor.to(torch.int16)
        numeric_tensor = data["numeric"]
        labels_tensor = data["labels"].unsqueeze(1)
        del data
        print(f"Loaded {len(labels_tensor)} samples (card_ids dtype: {card_ids_tensor.dtype})")
        return card_ids_tensor, numeric_tensor, labels_tensor

    # JSONL loading — use numpy to avoid Python list memory overhead
    # (Python list of ints uses ~28 bytes/int vs 2 bytes for int16 numpy)
    print(f"Loading data from {data_path}...")

    # Pass 1: count and validate
    n = 0
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            if n == 0:
                sample = json.loads(line)
                if len(sample["card_ids"]) != NUM_CARD_SLOTS:
                    raise ValueError(
                        f"Dataset card_ids length mismatch: got {len(sample['card_ids'])}, "
                        f"expected {NUM_CARD_SLOTS}. Re-run collect."
                    )
                if len(sample["numeric"]) != NUM_NUMERIC_FEATURES:
                    raise ValueError(
                        f"Dataset numeric length mismatch: got {len(sample['numeric'])}, "
                        f"expected {NUM_NUMERIC_FEATURES}. Re-run collect."
                    )
            n += 1

    if n == 0:
        print("No data found.")
        card_ids_tensor = torch.zeros((0, NUM_CARD_SLOTS), dtype=torch.int16)
        numeric_tensor = torch.zeros((0, NUM_NUMERIC_FEATURES), dtype=torch.float32)
        labels_tensor = torch.zeros((0, 1), dtype=torch.float32)
        return card_ids_tensor, numeric_tensor, labels_tensor

    print(f"Found {n} samples. Loading with numpy arrays...")
    card_ids_arr = np.zeros((n, NUM_CARD_SLOTS), dtype=np.int16)
    numeric_arr = np.zeros((n, NUM_NUMERIC_FEATURES), dtype=np.float32)
    labels_arr = np.zeros(n, dtype=np.float32)

    # Pass 2: fill arrays
    with open(data_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            sample = json.loads(line)
            card_ids_arr[i] = sample["card_ids"]
            numeric_arr[i] = sample["numeric"]
            labels_arr[i] = sample["label"]
            if (i + 1) % 100000 == 0:
                print(f"  {i + 1}/{n} samples loaded")

    print(f"Loaded {n} samples, converting to tensors...")
    card_ids_tensor = torch.from_numpy(card_ids_arr)  # int16
    del card_ids_arr
    numeric_tensor = torch.from_numpy(numeric_arr)
    del numeric_arr
    labels_tensor = torch.from_numpy(labels_arr).unsqueeze(1)
    del labels_arr
    return card_ids_tensor, numeric_tensor, labels_tensor


# ============================================================
# Training
# ============================================================

def train_model(
    data_path: str,
    model_save_path: str,
    epochs: int = 50,
    batch_size: int = 512,
    lr: float = 0.001,
    validation_split: float = 0.1,
    device: str = "auto",
):
    """
    Train the scoring model on collected data.

    Saves model weights + metadata to model_save_path.

    Memory-optimized:
    - card_ids stored as int16, cast to long per-batch only
    - Validation batched (not sent to GPU all at once)
    - Shuffling via index permutation (no full-tensor copy per epoch)
    - Mixed precision (fp16) on CUDA/ROCm GPUs
    """
    import gc
    torch, nn = _import_torch()

    # Load data (card_ids are int16 to save memory)
    card_ids_tensor, numeric_tensor, labels_tensor = _load_data(data_path)
    n = len(labels_tensor)

    if n == 0:
        print("No data to train on.")
        return

    # Train/val split — use torch.randperm to avoid Python list overhead
    perm = torch.randperm(n)
    val_size = max(1, int(n * validation_split))
    val_idx = perm[:val_size]
    train_idx = perm[val_size:]

    # Split data and free originals immediately
    train_card_ids = card_ids_tensor[train_idx]
    train_numeric = numeric_tensor[train_idx]
    train_labels = labels_tensor[train_idx]

    val_card_ids = card_ids_tensor[val_idx]
    val_numeric = numeric_tensor[val_idx]
    val_labels = labels_tensor[val_idx]

    del card_ids_tensor, numeric_tensor, labels_tensor, perm, val_idx, train_idx
    gc.collect()

    n_train = len(train_labels)
    n_val = len(val_labels)
    print(f"Train: {n_train}, Validation: {n_val}")

    torch_device = _select_device(device)
    use_amp = torch_device.type == "cuda"
    # GradScaler triggers illegal memory access on ROCm/HIP — disable it there.
    # autocast alone still gives fp16 speedup without the scaler.
    is_rocm = bool(getattr(torch.version, "hip", None))
    use_scaler = use_amp and not is_rocm
    if use_amp:
        if is_rocm:
            print("Using mixed precision (fp16) for faster training (GradScaler disabled on ROCm)")
        else:
            print("Using mixed precision (fp16) for faster training and lower GPU memory")

    # Keep validation data on CPU — batch it to GPU during evaluation
    # (moving entire val set to GPU caused OOM on 8GB GPUs)

    # Create model
    model = create_model()
    model.to(torch_device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()
    scaler = torch.amp.GradScaler("cuda") if use_scaler else None

    best_val_loss = float('inf')
    best_state_dict = None

    # Training loop
    for epoch in range(1, epochs + 1):
        model.train()

        # Shuffle via index permutation — no full-tensor copy
        shuffle_perm = torch.randperm(n_train)

        epoch_loss = 0.0
        num_batches = 0

        for start in range(0, n_train, batch_size):
            end = min(start + batch_size, n_train)
            idx = shuffle_perm[start:end]

            # Cast card_ids int16 -> long only for this batch, directly on device
            batch_cids = train_card_ids[idx].to(torch_device, dtype=torch.long)
            batch_nums = train_numeric[idx].to(torch_device)
            batch_labels = train_labels[idx].to(torch_device)

            optimizer.zero_grad()

            if use_amp:
                with torch.amp.autocast("cuda"):
                    predictions = model(batch_cids, batch_nums)
                # BCELoss must run in fp32 (outside autocast)
                loss = loss_fn(predictions.float(), batch_labels)
                if scaler is not None:
                    scaler.scale(loss).backward()
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    loss.backward()
                    optimizer.step()
            else:
                predictions = model(batch_cids, batch_nums)
                loss = loss_fn(predictions, batch_labels)
                loss.backward()
                optimizer.step()

            epoch_loss += loss.item()
            num_batches += 1

        avg_train_loss = epoch_loss / num_batches

        # Batched validation — don't send entire val set to GPU at once
        model.eval()
        val_loss_sum = 0.0
        val_correct_sum = 0
        val_count = 0

        with torch.no_grad():
            for start in range(0, n_val, batch_size):
                end = min(start + batch_size, n_val)
                batch_cids = val_card_ids[start:end].to(torch_device, dtype=torch.long)
                batch_nums = val_numeric[start:end].to(torch_device)
                batch_labels = val_labels[start:end].to(torch_device)

                if use_amp:
                    with torch.amp.autocast("cuda"):
                        preds = model(batch_cids, batch_nums)
                    # BCELoss must run in fp32
                    batch_loss = loss_fn(preds.float(), batch_labels).item()
                else:
                    preds = model(batch_cids, batch_nums)
                    batch_loss = loss_fn(preds, batch_labels).item()

                batch_count = end - start
                val_loss_sum += batch_loss * batch_count
                val_correct_sum += int(((preds > 0.5).float() == batch_labels).sum().item())
                val_count += batch_count

        val_loss = val_loss_sum / val_count
        val_correct = val_correct_sum / val_count

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            # Save best weights to CPU to avoid using GPU memory
            best_state_dict = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        if epoch % 5 == 0 or epoch == 1:
            print(f"  Epoch {epoch:3d}/{epochs}  "
                  f"train_loss={avg_train_loss:.4f}  "
                  f"val_loss={val_loss:.4f}  "
                  f"val_acc={val_correct:.3f}"
                  f"{'  *best*' if val_loss <= best_val_loss else ''}")

    # Save best model
    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)

    save_data = {
        "model_state_dict": model.state_dict(),
        "card_name_to_id": CARD_NAME_TO_ID,
        "num_card_types": NUM_CARD_TYPES,
        "num_card_slots": NUM_CARD_SLOTS,
        "num_numeric_features": NUM_NUMERIC_FEATURES,
        "best_val_loss": best_val_loss,
        "trained_device": str(torch_device),
        "torch_version": torch.__version__,
        "torch_hip_version": getattr(torch.version, "hip", None),
    }
    torch.save(save_data, model_save_path)
    print(f"\nModel saved to: {model_save_path}")
    print(f"Best validation loss: {best_val_loss:.4f}")


def test_model(
    data_path: str,
    model_path: str,
    batch_size: int = 256,
    validation_split: float = 0.5,
    device: str = "auto",
):
    """
    Evaluate a saved model on a held-out subset from the provided dataset.

    The held-out subset is selected the same way as training validation split:
    shuffle all indices, then take the first max(1, int(n * validation_split)).
    """
    torch, nn = _import_torch()

    card_ids_tensor, numeric_tensor, labels_tensor = _load_data(data_path)
    n = len(labels_tensor)

    if n == 0:
        print("No data to test on.")
        return

    if not (0.0 < validation_split < 1.0):
        raise ValueError(f"validation_split must be in (0, 1), got {validation_split}")

    indices = list(range(n))
    random.shuffle(indices)
    test_size = max(1, int(n * validation_split))
    test_indices = indices[:test_size]

    test_card_ids = card_ids_tensor[test_indices]
    test_numeric = numeric_tensor[test_indices]
    test_labels = labels_tensor[test_indices]

    # Free originals
    del card_ids_tensor, numeric_tensor, labels_tensor
    import gc; gc.collect()

    n_test = len(test_indices)
    print(f"Test subset: {n_test} samples (validation_split={validation_split})")

    torch_device = _select_device(device)
    # Keep test data on CPU — batch it to GPU during evaluation
    # (moving entire set to GPU caused OOM on 8GB GPUs)

    print(f"Loading model from {model_path}...")
    checkpoint = torch.load(model_path, map_location=torch_device, weights_only=False)

    saved_num_card_slots = checkpoint.get("num_card_slots")
    saved_num_numeric_features = checkpoint.get("num_numeric_features")
    if saved_num_card_slots != NUM_CARD_SLOTS:
        raise ValueError(
            f"Model card slot count mismatch: model={saved_num_card_slots}, runtime={NUM_CARD_SLOTS}. "
            "Retrain model with current slot constants."
        )
    if saved_num_numeric_features != NUM_NUMERIC_FEATURES:
        raise ValueError(
            f"Model numeric feature count mismatch: model={saved_num_numeric_features}, "
            f"runtime={NUM_NUMERIC_FEATURES}. Retrain model with current feature extractor."
        )

    saved_map = checkpoint.get("card_name_to_id")
    if saved_map != CARD_NAME_TO_ID:
        print("WARNING: Card ID mapping in model differs from current game. "
              "Evaluation may be inaccurate. Retrain recommended.")

    model = create_model(num_card_types=checkpoint["num_card_types"])
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(torch_device)
    model.eval()

    loss_fn = nn.BCELoss()
    total_loss = 0.0
    total_correct = 0
    total_count = 0

    use_amp = torch_device.type == "cuda"

    with torch.no_grad():
        for start in range(0, n_test, batch_size):
            end = min(start + batch_size, n_test)
            # Transfer batch from CPU to GPU with int16->long cast for card_ids
            batch_cids = test_card_ids[start:end].to(torch_device, dtype=torch.long)
            batch_nums = test_numeric[start:end].to(torch_device)
            batch_labels = test_labels[start:end].to(torch_device)

            if use_amp:
                with torch.amp.autocast("cuda"):
                    preds = model(batch_cids, batch_nums)
                # BCELoss must run in fp32
                batch_loss = loss_fn(preds.float(), batch_labels).item()
            else:
                preds = model(batch_cids, batch_nums)
                batch_loss = loss_fn(preds, batch_labels).item()
            batch_count = end - start

            total_loss += batch_loss * batch_count
            total_correct += int(((preds > 0.5).float() == batch_labels).sum().item())
            total_count += batch_count

    avg_loss = total_loss / total_count
    accuracy = total_correct / total_count

    print("\nTest results")
    print(f"  Samples:  {total_count}")
    print(f"  BCE loss: {avg_loss:.4f}")
    print(f"  Accuracy: {accuracy:.4f}")


# ============================================================
# MLEvaluator - Drop-in replacement for Evaluator.evaluate
# ============================================================

class MLEvaluator:
    """
    ML-based game state evaluator.

    Usage:
        evaluator = MLEvaluator("model.pt")
        score = evaluator.evaluate(state, player, only_care_about_winorlose=False)
    """

    def __init__(self, model_path: str, device: str = "auto"):
        torch, _ = _import_torch()
        self._torch = torch
        self.device = _select_device(device)

        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)

        saved_num_card_slots = checkpoint.get("num_card_slots")
        saved_num_numeric_features = checkpoint.get("num_numeric_features")
        if saved_num_card_slots != NUM_CARD_SLOTS:
            raise ValueError(
                f"Model card slot count mismatch: model={saved_num_card_slots}, runtime={NUM_CARD_SLOTS}. "
                "Retrain model with current slot constants."
            )
        if saved_num_numeric_features != NUM_NUMERIC_FEATURES:
            raise ValueError(
                f"Model numeric feature count mismatch: model={saved_num_numeric_features}, "
                f"runtime={NUM_NUMERIC_FEATURES}. Retrain model with current feature extractor."
            )

        # Verify card mapping matches current game
        saved_map = checkpoint["card_name_to_id"]
        if saved_map != CARD_NAME_TO_ID:
            print("WARNING: Card ID mapping in model differs from current game. "
                  "Model may produce inaccurate results. Retrain recommended.")

        self.model = create_model(
            num_card_types=checkpoint["num_card_types"],
        )
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()

    def evaluate(self, state: GameStateSnapshot, player: int,
                 only_care_about_winorlose: bool) -> float:
        """
        Evaluate game state from player's perspective.

        Returns:
            float('inf')  if player has won
            float('-inf') if player has lost
            0.0           if draw or only_care_about_winorlose and game not over
            [0.0, 200.0]  ML-predicted score (higher = more likely to win)
        """
        opponent = 3 - player

        # Terminal states: keep exact values for compatibility with search
        if state.concluded:
            if state.winner == player:
                return float('inf')
            elif state.winner == opponent:
                return float('-inf')
            else:
                return 0.0

        if only_care_about_winorlose:
            return 0.0

        # Extract features and predict
        card_ids, numeric = extract_features(state, player)

        card_ids_t = self._torch.tensor([card_ids], dtype=self._torch.long, device=self.device)
        numeric_t = self._torch.tensor([numeric], dtype=self._torch.float32, device=self.device)

        with self._torch.no_grad():
            win_prob = self.model(card_ids_t, numeric_t).item()

        # Scale to [0, 200] range to be comparable with the heuristic evaluator's
        # base-100 scoring. 100 = even, >100 = winning, <100 = losing.
        return win_prob * 200.0


# ============================================================
# CLI
# ============================================================

def _print_info(model_path: str):
    """Print information about a saved model."""
    torch, _ = _import_torch()
    checkpoint = torch.load(model_path, weights_only=False)

    print(f"Model: {model_path}")
    print(f"  Card types:       {checkpoint['num_card_types']}")
    print(f"  Card slots:       {checkpoint['num_card_slots']}")
    print(f"  Numeric features: {checkpoint['num_numeric_features']}")
    print(f"  Best val loss:    {checkpoint.get('best_val_loss', 'N/A')}")
    print(f"  Trained device:   {checkpoint.get('trained_device', 'N/A')}")
    if checkpoint.get('torch_hip_version'):
        print(f"  ROCm/HIP version: {checkpoint['torch_hip_version']}")
    print(f"  Torch version:    {checkpoint.get('torch_version', 'N/A')}")
    print(f"  Card mapping:     {len(checkpoint['card_name_to_id'])} cards")

    # Model size
    state_dict = checkpoint["model_state_dict"]
    total_params = sum(p.numel() for p in state_dict.values())
    print(f"  Total parameters: {total_params:,}")


def main():
    parser = argparse.ArgumentParser(description="ML Scoring for Super Hard Card Game")
    subparsers = parser.add_subparsers(dest="command")

    # collect
    collect_parser = subparsers.add_parser("collect", help="Collect training data")
    collect_parser.add_argument("--games", type=int, default=10000,
                                help="Number of games to simulate (default: 10000)")
    collect_parser.add_argument("--output", type=str, default="./ml/ml_training_data.jsonl",
                                help="Output file path (default: ./ml/ml_training_data.jsonl)")
    collect_parser.add_argument("--ai-cuets", type=int, default=4,
                                help="AI CUETS parameter (default: 4)")
    collect_parser.add_argument("--ai-max-states", type=int, default=4,
                                help="AI max unique states (default: 4)")
    collect_parser.add_argument("--max-turns", type=int, default=200,
                                help="Max turns per game (default: 200)")

    # preprocess
    preprocess_parser = subparsers.add_parser("preprocess",
                                               help="Convert JSONL to compact .pt format (saves memory)")
    preprocess_parser.add_argument("--data", type=str, default="./ml/ml_training_data.jsonl",
                                    help="Input JSONL data path (default: ./ml/ml_training_data.jsonl)")
    preprocess_parser.add_argument("--output", type=str, default="./ml/ml_training_data.pt",
                                    help="Output .pt file path (default: ./ml/ml_training_data.pt)")

    # train
    train_parser = subparsers.add_parser("train", help="Train the model")
    train_parser.add_argument("--data", type=str, default="./ml/ml_training_data.pt",
                               help="Training data path, .pt or .jsonl (default: ./ml/ml_training_data.pt)")
    train_parser.add_argument("--model", type=str, default="./ml/model.pt",
                               help="Model save path (default: ./ml/model.pt)")
    train_parser.add_argument("--epochs", type=int, default=30,
                               help="Training epochs (default: 30)")
    train_parser.add_argument("--batch-size", type=int, default=512,
                               help="Batch size (default: 512)")
    train_parser.add_argument("--lr", type=float, default=0.001,
                               help="Learning rate (default: 0.001)")
    train_parser.add_argument("--device", type=str, default="auto",
                               choices=["auto", "cpu", "cuda"],
                               help="Training device (default: auto). Use 'cuda' for NVIDIA/ROCm PyTorch builds.")

    # info
    info_parser = subparsers.add_parser("info", help="Show model info")
    info_parser.add_argument("--model", type=str, default="./ml/model.pt",
                              help="Model path (default: ./ml/model.pt)")

    # test
    test_parser = subparsers.add_parser("test", help="Test a model on held-out data subset")
    test_parser.add_argument("--data", type=str, default="./ml/ml_training_data.pt",
                             help="Data path, .pt or .jsonl (default: ./ml/ml_training_data.pt)")
    test_parser.add_argument("--model", type=str, default="./ml/model.pt",
                             help="Model path (default: ./ml/model.pt)")
    test_parser.add_argument("--validation-split", type=float, default=0.5,
                             help="Held-out subset ratio using train/validation split logic (default: 0.5)")
    test_parser.add_argument("--batch-size", type=int, default=256,
                             help="Batch size for evaluation (default: 256)")
    test_parser.add_argument("--device", type=str, default="auto",
                             choices=["auto", "cpu", "cuda"],
                             help="Evaluation device (default: auto). Use 'cuda' for NVIDIA/ROCm PyTorch builds.")

    args = parser.parse_args()

    if args.command == "collect":
        print(f"Collecting training data: {args.games} games -> {args.output}")
        collect_training_data(
            num_games=args.games,
            output_path=args.output,
            ai_cuets=args.ai_cuets,
            ai_max_states=args.ai_max_states,
            max_turns=args.max_turns,
        )

    elif args.command == "preprocess":
        print(f"Preprocessing: {args.data} -> {args.output}")
        preprocess_data(
            jsonl_path=args.data,
            output_path=args.output,
        )

    elif args.command == "train":
        print(f"Training model: {args.data} -> {args.model}")
        train_model(
            data_path=args.data,
            model_save_path=args.model,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
            device=args.device,
        )

    elif args.command == "info":
        _print_info(args.model)

    elif args.command == "test":
        print(f"Testing model: {args.model} on {args.data} (validation_split={args.validation_split})")
        test_model(
            data_path=args.data,
            model_path=args.model,
            batch_size=args.batch_size,
            validation_split=args.validation_split,
            device=args.device,
        )

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
