"""
ML-based scoring for Super Hard Card Game.

Trains a neural network to predict win probability from game state,
replacing the hand-crafted Evaluator.evaluate() heuristic.

Usage:
    python ml_scoring.py collect [--games N] [--output PATH]
    python ml_scoring.py train [--data PATH] [--model PATH] [--epochs N]
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
# plus debug_card_types, giving a deterministic ordering.

CARD_NAME_TO_ID: dict[str, int] = {}
for _i, _cls in enumerate(cards.all_card_types + cards.debug_card_types, start=1):
    CARD_NAME_TO_ID[_cls.__name__] = _i
NUM_CARD_TYPES = len(CARD_NAME_TO_ID) + 1  # +1 for empty slot (index 0)
EMPTY_CARD_ID = 0

# ============================================================
# Feature Extraction
# ============================================================

# Layout constants
_FIELD_SLOTS = MAX_FIELD_SIZE  # 5 per player
_HAND_SLOTS = MAX_HAND_SIZE    # 9 per player
_GRAVEYARD_SLOTS = 15          # per player (card IDs only)
_BANISHED_SLOTS = 10           # per player (card IDs only)
_DECK_SLOTS = 20               # per player (card IDs only)

# Total card ID slots: field + hand (with numeric) + graveyard + banished + deck (IDs only)
NUM_CARD_SLOTS = (
    (_FIELD_SLOTS + _HAND_SLOTS) * 2               # 28 (field + hand, both players)
    + (_GRAVEYARD_SLOTS + _BANISHED_SLOTS + _DECK_SLOTS) * 2  # 90 (gy + banish + deck, both players)
)  # 118 total

# Per-slot numeric features
_FIELD_NUMERIC_PER_SLOT = 22  # see _encode_field_slot
_HAND_NUMERIC_PER_SLOT = 12   # see _encode_hand_slot
_GLOBAL_NUMERIC = 22

NUM_NUMERIC_FEATURES = (
    _GLOBAL_NUMERIC
    + _FIELD_SLOTS * 2 * _FIELD_NUMERIC_PER_SLOT
    + _HAND_SLOTS * 2 * _HAND_NUMERIC_PER_SLOT
)  # 22 + 220 + 216 = 458


def _encode_field_slot(card: Optional[cards.Card]) -> tuple[int, list[float]]:
    """Encode a single field slot. Returns (card_id, numeric_features[22])."""
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
        ]
    else:
        return EMPTY_CARD_ID, [0.0] * _FIELD_NUMERIC_PER_SLOT

    return card_id, numeric


def _encode_hand_slot(card: Optional[cards.Card]) -> tuple[int, list[float]]:
    """Encode a single hand slot. Returns (card_id, numeric_features[12])."""
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
        card_ids:  list of int,   length NUM_CARD_SLOTS  (118)
        numeric:   list of float, length NUM_NUMERIC_FEATURES (458)
    """
    opponent = 3 - player
    card_ids: list[int] = []
    numeric: list[float] = []

    # --- Global features (22) ---
    numeric.extend([
        snapshot.turn / 30.0,                                           # 0  turn
        snapshot.hp[player] / 30.0,                                     # 1  own hp
        snapshot.hp[opponent] / 30.0,                                   # 2  opp hp
        snapshot.max_hp[player] / 30.0,                                 # 3  own max_hp
        snapshot.max_hp[opponent] / 30.0,                               # 4  opp max_hp
        snapshot.foxtail[player] / 9.0,                                 # 5  own foxtail
        snapshot.foxtail[opponent] / 9.0,                               # 6  opp foxtail
        len(snapshot.hands[player]) / 9.0,                              # 7  own hand size
        len(snapshot.hands[opponent]) / 9.0,                            # 8  opp hand size
        len(snapshot.decks[player]) / 40.0,                             # 9  own deck size
        len(snapshot.decks[opponent]) / 40.0,                           # 10 opp deck size
        len(snapshot.graveyard[player]) / 40.0,                         # 11 own graveyard size
        len(snapshot.graveyard[opponent]) / 40.0,                       # 12 opp graveyard size
        len(snapshot.fields[player]) / 5.0,                             # 13 own field count
        len(snapshot.fields[opponent]) / 5.0,                           # 14 opp field count (was missing)
        len(snapshot.banished[player]) / 40.0,                          # 15 own banished count
        len(snapshot.banished[opponent]) / 40.0,                        # 16 opp banished count
        float(snapshot.current_player == player),                       # 17 is it our turn?
        snapshot.enhance_used_this_turn[player] / 3.0,                  # 18 own enhance used
        snapshot.enhance_used_this_turn[opponent] / 3.0,                # 19 opp enhance used
        snapshot.max_enhance_allowed_per_turn[player] / 3.0,            # 20 own max enhance/turn
        snapshot.amount_card_generated_from_void[player] / 10.0,        # 21 own cards generated
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

    # --- Graveyard card IDs (player then opponent, 15 slots each) ---
    for p in [player, opponent]:
        card_ids.extend(_encode_zone_card_ids(snapshot.graveyard[p], _GRAVEYARD_SLOTS))

    # --- Banished card IDs (player then opponent, 10 slots each) ---
    for p in [player, opponent]:
        card_ids.extend(_encode_zone_card_ids(snapshot.banished[p], _BANISHED_SLOTS))

    # --- Deck card IDs (player then opponent, 20 slots each) ---
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


def create_model(num_card_types: int = NUM_CARD_TYPES,
                 embedding_dim: int = 16,
                 hidden_dim: int = 256):
    """Create and return a ScoringModel instance."""
    torch, nn = _import_torch()

    class ScoringModel(nn.Module):
        """
        Predicts win probability from game state features.

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

        actions = get_ai_actions(ai, state)
        for action in actions:
            if action[0] == 'end_turn':
                break
            apply_action(state, current_player, action)
            if state.concluded:
                break

        if not state.concluded:
            GameSimulator.end_turn(state)

        # Snapshot AFTER end_turn (start of next player's turn)
        # Record from BOTH players' perspectives for balanced training
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
# Training
# ============================================================

def train_model(
    data_path: str,
    model_save_path: str,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 0.001,
    validation_split: float = 0.1,
):
    """
    Train the scoring model on collected data.

    Saves model weights + metadata to model_save_path.
    """
    torch, nn = _import_torch()

    # Load data
    print(f"Loading data from {data_path}...")
    card_ids_list = []
    numeric_list = []
    labels_list = []

    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            sample = json.loads(line)
            card_ids_list.append(sample["card_ids"])
            numeric_list.append(sample["numeric"])
            labels_list.append(sample["label"])

    n = len(labels_list)
    print(f"Loaded {n} samples")

    if n == 0:
        print("No data to train on.")
        return

    # Convert to tensors
    card_ids_tensor = torch.tensor(card_ids_list, dtype=torch.long)
    numeric_tensor = torch.tensor(numeric_list, dtype=torch.float32)
    labels_tensor = torch.tensor(labels_list, dtype=torch.float32).unsqueeze(1)

    # Train/val split
    indices = list(range(n))
    random.shuffle(indices)
    val_size = max(1, int(n * validation_split))
    val_indices = indices[:val_size]
    train_indices = indices[val_size:]

    train_card_ids = card_ids_tensor[train_indices]
    train_numeric = numeric_tensor[train_indices]
    train_labels = labels_tensor[train_indices]

    val_card_ids = card_ids_tensor[val_indices]
    val_numeric = numeric_tensor[val_indices]
    val_labels = labels_tensor[val_indices]

    print(f"Train: {len(train_indices)}, Validation: {len(val_indices)}")

    # Create model
    model = create_model()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()

    best_val_loss = float('inf')
    best_state_dict = None

    # Training loop
    for epoch in range(1, epochs + 1):
        model.train()

        # Shuffle training data
        perm = torch.randperm(len(train_indices))
        train_card_ids = train_card_ids[perm]
        train_numeric = train_numeric[perm]
        train_labels = train_labels[perm]

        epoch_loss = 0.0
        num_batches = 0

        for start in range(0, len(train_indices), batch_size):
            end = min(start + batch_size, len(train_indices))
            batch_cids = train_card_ids[start:end]
            batch_nums = train_numeric[start:end]
            batch_labels = train_labels[start:end]

            optimizer.zero_grad()
            predictions = model(batch_cids, batch_nums)
            loss = loss_fn(predictions, batch_labels)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            num_batches += 1

        avg_train_loss = epoch_loss / num_batches

        # Validation
        model.eval()
        with torch.no_grad():
            val_preds = model(val_card_ids, val_numeric)
            val_loss = loss_fn(val_preds, val_labels).item()

            # Accuracy: predict win if > 0.5
            val_correct = ((val_preds > 0.5).float() == val_labels).float().mean().item()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state_dict = {k: v.clone() for k, v in model.state_dict().items()}

        if epoch % 5 == 0 or epoch == 1:
            print(f"  Epoch {epoch:3d}/{epochs}  "
                  f"train_loss={avg_train_loss:.4f}  "
                  f"val_loss={val_loss:.4f}  "
                  f"val_acc={val_correct:.3f}"
                  f"{'  *best*' if best_state_dict is not None and val_loss <= best_val_loss else ''}")

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
    }
    torch.save(save_data, model_save_path)
    print(f"\nModel saved to: {model_save_path}")
    print(f"Best validation loss: {best_val_loss:.4f}")


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

    def __init__(self, model_path: str):
        torch, nn = _import_torch()
        self._torch = torch

        checkpoint = torch.load(model_path, weights_only=False)

        # Verify card mapping matches current game
        saved_map = checkpoint["card_name_to_id"]
        if saved_map != CARD_NAME_TO_ID:
            print("WARNING: Card ID mapping in model differs from current game. "
                  "Model may produce inaccurate results. Retrain recommended.")

        self.model = create_model(
            num_card_types=checkpoint["num_card_types"],
        )
        self.model.load_state_dict(checkpoint["model_state_dict"])
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

        card_ids_t = self._torch.tensor([card_ids], dtype=self._torch.long)
        numeric_t = self._torch.tensor([numeric], dtype=self._torch.float32)

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
    collect_parser.add_argument("--games", type=int, default=3000,
                                help="Number of games to simulate (default: 3000)")
    collect_parser.add_argument("--output", type=str, default="./ml/ml_training_data.jsonl",
                                help="Output file path (default: ./ml/ml_training_data.jsonl)")
    collect_parser.add_argument("--ai-cuets", type=int, default=2,
                                help="AI CUETS parameter (default: 2)")
    collect_parser.add_argument("--ai-max-states", type=int, default=4,
                                help="AI max unique states (default: 4)")
    collect_parser.add_argument("--max-turns", type=int, default=200,
                                help="Max turns per game (default: 200)")

    # train
    train_parser = subparsers.add_parser("train", help="Train the model")
    train_parser.add_argument("--data", type=str, default="./ml/ml_training_data.jsonl",
                               help="Training data path (default: ./ml/ml_training_data.jsonl)")
    train_parser.add_argument("--model", type=str, default="./ml/ml_model.pt",
                               help="Model save path (default: ./ml/ml_model.pt)")
    train_parser.add_argument("--epochs", type=int, default=50,
                               help="Training epochs (default: 50)")
    train_parser.add_argument("--batch-size", type=int, default=64,
                               help="Batch size (default: 64)")
    train_parser.add_argument("--lr", type=float, default=0.001,
                               help="Learning rate (default: 0.001)")

    # info
    info_parser = subparsers.add_parser("info", help="Show model info")
    info_parser.add_argument("--model", type=str, default="./ml/ml_model.pt",
                              help="Model path (default: ./ml/ml_model.pt)")

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

    elif args.command == "train":
        print(f"Training model: {args.data} -> {args.model}")
        train_model(
            data_path=args.data,
            model_save_path=args.model,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
        )

    elif args.command == "info":
        _print_info(args.model)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
