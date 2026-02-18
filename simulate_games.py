"""
AI vs AI Game Simulation Script for Super Hard Card Game.
Simulates multiple games between two AI players and reports win rates.
"""
import random
import json
import os
import cards
from ai_player_new import (
    GameStateSnapshot,
    GameSimulator,
    MinimaxAI,
    Evaluator,
    AIError,
    CardNotFoundError,
    MAX_FOXTAIL,
    _find_card_by_id,
    _find_card_by_void_id,
    _find_card_in_zones,
    _find_card_in_zones_by_void_id,
)

DECKS_SAVE_FILE = "saved_decks.json"


def load_saved_decks() -> dict[str, dict[str, int]]:
    """Load saved decks from JSON file. Returns empty dict if file not found."""
    if not os.path.exists(DECKS_SAVE_FILE):
        return {}
    try:
        with open(DECKS_SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "saved_decks" in data and isinstance(data["saved_decks"], dict):
            return data["saved_decks"]
    except (json.JSONDecodeError, KeyError, ValueError):
        pass
    return {}


def build_deck_from_recipe(recipe: dict[str, int]) -> list[cards.Card]:
    """Build a list of Card instances from a deck recipe."""
    deck = []
    for card_type in cards.all_card_types:
        card = card_type()
        if card.name in recipe:
            for _ in range(recipe[card.name]):
                deck.append(card_type())
    random.shuffle(deck)
    return deck


def create_random_deck() -> list[cards.Card]:
    """Create a random deck using the default card types."""
    example_deck = []
    card_types = cards.all_card_types
    selected_card_types = random.sample(card_types, 15)
    for card_type in selected_card_types:
        for _ in range(3):
            example_deck.append(card_type())
            random.shuffle(example_deck)
    return example_deck


def create_deck(recipe: dict[str, int] | None) -> list[cards.Card]:
    """Create a deck from a recipe, or a random deck if recipe is None."""
    if recipe is not None:
        return build_deck_from_recipe(recipe)
    return create_random_deck()


def create_game_state(
    deck1_recipe: dict[str, int] | None = None,
    deck2_recipe: dict[str, int] | None = None,
) -> GameStateSnapshot:
    """Create a new game state with specified or random decks."""
    state = GameStateSnapshot()
    state.decks[1] = create_deck(deck1_recipe)
    state.decks[2] = create_deck(deck2_recipe)
    state.current_player = 2  # Player 2 goes first (as in the original game)
    return state


def simulate_single_game(
    ai1: MinimaxAI,
    ai2: MinimaxAI,
    deck1_recipe: dict[str, int] | None = None,
    deck2_recipe: dict[str, int] | None = None,
    max_turns: int = 200,
) -> int | None:
    """
    Simulate a single game between two AIs.

    Returns:
        1 if player 1 wins, 2 if player 2 wins, None if draw
    """
    state = create_game_state(deck1_recipe, deck2_recipe)
    ais = {1: ai1, 2: ai2}

    while not state.concluded and state.turn <= max_turns:
        current_player = state.current_player
        ai = ais[current_player]

        # Get best actions for this turn
        # We need to use a temporary wrapper to make the state compatible
        actions = get_ai_actions(ai, state)

        # Apply all actions except end_turn
        for action in actions:
            if action[0] == 'end_turn':
                break
            apply_action(state, current_player, action)
            if state.concluded:
                break

        if not state.concluded:
            GameSimulator.end_turn(state)

    return state.winner


def get_ai_actions(ai: MinimaxAI, state: GameStateSnapshot) -> list[tuple]:
    """
    Get the best actions from the AI for the current state.
    Mirrors MinimaxAI.get_best_turn_actions() but works directly on GameStateSnapshot.
    """
    ai.endturnstate_evaluated = 0
    ai.endturnstate_evaluated_additional = 0
    ai.loss_endturnstate_avoided = 0

    best_score = float('-inf')
    best_actions = []

    all_sequences = ai._generate_random_turn_sequences(
        state, ai.player_number,
        ai.continuous_unique_endturnstates_req_player_turn,
        ai.unique_states_max_player_turn
    )

    for actions in all_sequences:
        test_state = state.copy()
        for action in actions:
            if not ai._apply_action(test_state, ai.player_number, action):
                raise AIError("Invalid action sequence generated.")

        GameSimulator.end_turn(test_state)
        score = Evaluator.evaluate(test_state, ai.player_number, only_care_about_winorlose=False)

        # Advanced evaluation: simulate opponent's turn
        if not score == float('inf') and not score == float('-inf') and not score == 0.0:
            opponent_sequences = ai._generate_random_turn_sequences(
                test_state, 3 - ai.player_number,
                ai.continuous_unique_endturnstates_req_opp_turn,
                ai.unique_states_max_opp_turn
            )
            for single_opp_seq in opponent_sequences:
                opp_test_state = test_state.copy()
                for opp_action in single_opp_seq:
                    if not ai._apply_action(opp_test_state, test_state.current_player, opp_action):
                        raise AIError("Invalid opponent action sequence generated.")

                GameSimulator.end_turn(opp_test_state)
                opp_score = Evaluator.evaluate(opp_test_state, 3 - ai.player_number, only_care_about_winorlose=True)
                ai.endturnstate_evaluated_additional += 1

                if opp_score == float('inf'):
                    score = float('-inf')
                    ai.loss_endturnstate_avoided += 1
                    break

        ai.endturnstate_evaluated += 1

        if score > best_score:
            best_score = score
            best_actions = actions

        if best_score == float('inf'):
            break

    best_actions.append(('end_turn',))
    return best_actions


def apply_action(state: GameStateSnapshot, player: int, action: tuple) -> bool:
    """
    Apply an action to the state. Mirrors MinimaxAI._apply_action().
    Handles is_generated cards via void_id lookup.
    """
    action_type = action[0]

    if action_type == 'play':
        card, target, effect_choice = action[1], action[2], action[3]
        if card.is_generated:
            actual_card = _find_card_by_void_id(state.hands[player], card.void_id)
        else:
            actual_card = _find_card_by_id(state.hands[player], card.unique_id)
        if actual_card is None:
            raise CardNotFoundError(f"Card to play not found in hand: {card}")

        actual_target = None
        if target is not None:
            if target.is_generated:
                actual_target = _find_card_in_zones_by_void_id(state, target.void_id, player)
            else:
                actual_target = _find_card_in_zones(state, target.unique_id, player)
            if actual_target is None:
                raise CardNotFoundError(f"Target for card play not found: {target}")

        return GameSimulator.play_card(state, player, actual_card, actual_target, effect_choice)

    elif action_type == 'attack':
        attacker, target = action[1], action[2]
        if attacker.is_generated:
            actual_attacker = next(
                (f for f in state.fields[player]
                 if f.void_id == attacker.void_id and f.can_attack_this_turn),
                None
            )
        else:
            actual_attacker = next(
                (f for f in state.fields[player]
                 if f.unique_id == attacker.unique_id and f.can_attack_this_turn),
                None
            )
        if actual_attacker is None:
            raise CardNotFoundError(f"Attacker not found on field: {attacker}")

        if target == "leader":
            actual_target = "leader"
        else:
            actual_target = _find_card_by_id(state.fields[3 - player], target.unique_id)
            if actual_target is None:
                raise CardNotFoundError(f"Attack target not found on field: {target}")

        return GameSimulator.follower_attack(state, player, actual_attacker, actual_target)

    elif action_type == 'enhance':
        follower, extra_target, effect_choice = action[1], action[2], action[3]
        if follower.is_generated:
            actual_follower = next(
                (f for f in state.fields[player]
                 if f.void_id == follower.void_id and f.can_enhance),
                None
            )
        else:
            actual_follower = next(
                (f for f in state.fields[player]
                 if f.unique_id == follower.unique_id and f.can_enhance),
                None
            )
        if actual_follower is None:
            raise CardNotFoundError(f"Follower to enhance not found on field: {follower}")

        actual_target = None
        if extra_target is not None:
            if extra_target.is_generated:
                actual_target = _find_card_in_zones_by_void_id(state, extra_target.void_id, player)
            else:
                actual_target = _find_card_in_zones(state, extra_target.unique_id, player)
            if actual_target is None:
                raise CardNotFoundError(f"Extra target for enhance not found: {extra_target}")

        return GameSimulator.enhance_follower(state, player, actual_follower, actual_target,
                                              effect_choice=effect_choice)

    elif action_type == 'draw':
        return GameSimulator.draw_card(state, player)

    return False


def simulate_games(
    num_games: int,
    deck1_recipe: dict[str, int] | None = None,
    deck2_recipe: dict[str, int] | None = None,
    cuets_player_turn: int = 6,
    cuets_opp_turn: int = 3,
    usm_player_turn: int = 400,
    usm_opp_turn: int = 80,
) -> dict:
    """
    Simulate multiple games and return statistics.

    Args:
        num_games: Number of games to simulate
        deck1_recipe: Deck recipe for player 1 (None = random each game)
        deck2_recipe: Deck recipe for player 2 (None = random each game)
        cuets_player_turn: CUETS (Continuous Unique End Turn States) for player's turn
        cuets_opp_turn: CUETS for opponent's turn simulation

    Returns:
        Dictionary with win counts and rates
    """
    import sys

    ai1 = MinimaxAI(player_number=1, cuets_player_turn=cuets_player_turn, cuets_opp_turn=cuets_opp_turn,
                    unique_states_max_player_turn=usm_player_turn, unique_states_max_opp_turn=usm_opp_turn)
    ai2 = MinimaxAI(player_number=2, cuets_player_turn=cuets_player_turn, cuets_opp_turn=cuets_opp_turn,
                    unique_states_max_player_turn=usm_player_turn, unique_states_max_opp_turn=usm_opp_turn)

    wins = {1: 0, 2: 0, None: 0}  # None = draw

    last_progress = -1

    for i in range(num_games):
        # Print progress every 1%
        progress = int((i + 1) / num_games * 100)
        if progress > last_progress:
            print(f"Progress: {progress}% ({i + 1}/{num_games} games)")
            sys.stdout.flush()
            last_progress = progress

        winner = simulate_single_game(ai1, ai2, deck1_recipe, deck2_recipe)
        wins[winner] += 1

    return {
        'total_games': num_games,
        'player1_wins': wins[1],
        'player2_wins': wins[2],
        'draws': wins[None],
        'player1_winrate': wins[1] / num_games * 100,
        'player2_winrate': wins[2] / num_games * 100,
        'draw_rate': wins[None] / num_games * 100,
    }


def ask_int(prompt: str, default: int | None = None) -> int:
    """Ask the user for an integer value."""
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if raw == "" and default is not None:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Please enter a valid integer.")


def ask_deck_selection(player: int, saved_decks: dict[str, dict[str, int]]) -> dict[str, int] | None:
    """Ask the user to select a deck for a player. Returns recipe or None for random."""
    deck_names = list(saved_decks.keys())
    print(f"\nSelect deck for Player {player}:")
    print("  0: Random")
    for i, name in enumerate(deck_names, 1):
        print(f"  {i}: {name}")

    while True:
        raw = input(f"Player {player} deck [0]: ").strip()
        if raw == "":
            choice = 0
        else:
            try:
                choice = int(raw)
            except ValueError:
                print("Please enter a valid number.")
                continue

        if choice == 0:
            print(f"Player {player}: Random deck")
            return None
        elif 1 <= choice <= len(deck_names):
            name = deck_names[choice - 1]
            print(f"Player {player}: {name}")
            return saved_decks[name]
        else:
            print(f"Please enter a number between 0 and {len(deck_names)}.")


def main():
    print("=== Super Hard Card Game - AI Simulation ===\n")

    # Load saved decks
    saved_decks = load_saved_decks()
    if saved_decks:
        print(f"Loaded {len(saved_decks)} saved deck(s) from {DECKS_SAVE_FILE}.")
    else:
        print(f"No saved decks found ({DECKS_SAVE_FILE} not found or empty). Using random decks.\n")

    # Deck selection
    deck1_recipe = None
    deck2_recipe = None

    if saved_decks:
        deck1_recipe = ask_deck_selection(1, saved_decks)
        deck2_recipe = ask_deck_selection(2, saved_decks)

    print()

    # Simulation parameters
    num_games = ask_int("Number of games to simulate", default=100)
    cuets_player = ask_int("CUETS for player turn", default=6)
    cuets_opp = ask_int("CUETS for opponent turn", default=3)
    usm_player = ask_int("Unique States Max for player turn", default=300)
    usm_opp = ask_int("Unique States Max for opponent turn", default=60)

    # Describe setup
    deck1_label = "Random" if deck1_recipe is None else "Custom"
    deck2_label = "Random" if deck2_recipe is None else "Custom"
    print(f"\nSimulating {num_games} games...")
    print(f"  Player 1 deck: {deck1_label}")
    print(f"  Player 2 deck: {deck2_label}")
    print(f"  CUETS: player={cuets_player}, opp={cuets_opp}")
    print(f"  Unique States Max: player={usm_player}, opp={usm_opp}")
    print("=" * 50)

    results = simulate_games(
        num_games,
        deck1_recipe=deck1_recipe,
        deck2_recipe=deck2_recipe,
        cuets_player_turn=cuets_player,
        cuets_opp_turn=cuets_opp,
        usm_player_turn=usm_player,
        usm_opp_turn=usm_opp,
    )

    print("=" * 50)
    print("Results:")
    print(f"  Total games: {results['total_games']}")
    print(f"  Player 1 wins: {results['player1_wins']} ({results['player1_winrate']:.2f}%)")
    print(f"  Player 2 wins: {results['player2_wins']} ({results['player2_winrate']:.2f}%)")
    print(f"  Draws: {results['draws']} ({results['draw_rate']:.2f}%)")


if __name__ == '__main__':
    main()
