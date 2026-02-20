"""
AI vs AI Game Simulation Script for Super Hard Card Game.
Automatically loads all saved decks, includes random deck(s),
simulates round-robin matchups, and generates a detailed report.
"""
import random
import json
import os
import sys
from collections import defaultdict
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


def get_card_names_from_deck(deck: list[cards.Card]) -> set[str]:
    """Get unique card type names from a deck."""
    return set(card.name for card in deck)


def create_game_state_with_decks(
    deck1: list[cards.Card],
    deck2: list[cards.Card],
) -> GameStateSnapshot:
    """Create a new game state with pre-built decks."""
    state = GameStateSnapshot()
    state.decks[1] = deck1
    state.decks[2] = deck2
    state.current_player = 2  # Player 2 goes first (as in the original game)
    return state


def simulate_single_game(
    ai1: MinimaxAI,
    ai2: MinimaxAI,
    deck1: list[cards.Card],
    deck2: list[cards.Card],
    max_turns: int = 200,
) -> tuple[int | None, int]:
    """
    Simulate a single game between two AIs with pre-built decks.

    Returns:
        (winner, turn_count) where winner is 1, 2, or None (draw)
    """
    state = create_game_state_with_decks(deck1, deck2)
    ais = {1: ai1, 2: ai2}

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

    return state.winner, state.turn


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
        card, targets_template, effect_choice = action[1], action[2], action[3]
        multi_targets_template = action[4] if len(action) > 4 else None
        if card.is_generated:
            actual_card = _find_card_by_void_id(state.hands[player], card.void_id)
        else:
            actual_card = _find_card_by_id(state.hands[player], card.unique_id)
        if actual_card is None:
            raise CardNotFoundError(f"Card to play not found in hand: {card}")

        # Resolve targets list (one per selection step)
        actual_targets = None
        if targets_template is not None:
            actual_targets = []
            for t in targets_template:
                if t is None:
                    actual_targets.append(None)
                elif t.is_generated:
                    at = _find_card_in_zones_by_void_id(state, t.void_id, player)
                    if at is None:
                        raise CardNotFoundError(f"Target for card play not found: {t}")
                    actual_targets.append(at)
                else:
                    at = _find_card_in_zones(state, t.unique_id, player)
                    if at is None:
                        raise CardNotFoundError(f"Target for card play not found: {t}")
                    actual_targets.append(at)

        # Resolve multi targets
        actual_multi_targets = None
        if multi_targets_template is not None:
            actual_multi_targets = []
            for t in multi_targets_template:
                if t.is_generated:
                    at = _find_card_in_zones_by_void_id(state, t.void_id, player)
                else:
                    at = _find_card_in_zones(state, t.unique_id, player)
                if at is None:
                    raise CardNotFoundError(f"Multi-target for card play not found: {t}")
                actual_multi_targets.append(at)

        return GameSimulator.play_card(state, player, actual_card, actual_targets, effect_choice,
                                       multi_targets=actual_multi_targets)

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
        follower, targets_template, effect_choice = action[1], action[2], action[3]
        multi_targets_template = action[4] if len(action) > 4 else None
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

        # Resolve targets list (one per selection step)
        actual_targets = None
        if targets_template is not None:
            actual_targets = []
            for t in targets_template:
                if t is None:
                    actual_targets.append(None)
                elif t.is_generated:
                    at = _find_card_in_zones_by_void_id(state, t.void_id, player)
                    if at is None:
                        raise CardNotFoundError(f"Target for card enhance not found: {t}")
                    actual_targets.append(at)
                else:
                    at = _find_card_in_zones(state, t.unique_id, player)
                    if at is None:
                        raise CardNotFoundError(f"Target for card enhance not found: {t}")
                    actual_targets.append(at)

        # Resolve multi targets
        actual_multi_targets = None
        if multi_targets_template is not None:
            actual_multi_targets = []
            for t in multi_targets_template:
                if t.is_generated:
                    at = _find_card_in_zones_by_void_id(state, t.void_id, player)
                else:
                    at = _find_card_in_zones(state, t.unique_id, player)
                if at is None:
                    raise CardNotFoundError(f"Multi-target for card enhance not found: {t}")
                actual_multi_targets.append(at)

        return GameSimulator.enhance_follower(state, player, actual_follower, actual_targets,
                                              effect_choice=effect_choice,
                                              multi_targets=actual_multi_targets)

    elif action_type == 'draw':
        return GameSimulator.draw_card(state, player)

    return False


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


def print_report(
    deck_names: list[str],
    deck_pool: dict[str, dict[str, int] | None],
    matchup_results: dict[tuple[str, str], dict],
    deck_stats: dict[str, dict[str, int]],
    player_stats: dict[int | None, int],
    card_stats: dict[str, dict[str, int]],
    all_turns: list[int],
    total_games: int,
    num_games_per_matchup: int,
):
    """Print the full simulation report."""
    sep = "=" * 60
    thin_sep = "-" * 60

    print(f"\n{sep}")
    print("              SIMULATION REPORT")
    print(sep)
    print(f"  Decks: {', '.join(deck_names)}")
    print(f"  Matchups: {len(matchup_results)}")
    print(f"  Games per matchup: {num_games_per_matchup}")
    print(f"  Total games: {total_games}")

    # --- Matchup Results ---
    print(f"\n{thin_sep}")
    print(" MATCHUP RESULTS")
    print(thin_sep)
    for (d1, d2), stats in matchup_results.items():
        w = stats['p1_wins']
        l = stats['p2_wins']
        d = stats['draws']
        total = w + l + d
        wr = w / total * 100 if total > 0 else 0
        print(f"  {d1} (P1) vs {d2} (P2): {w}W / {l}L / {d}D  (P1 winrate: {wr:.1f}%)")

    # --- Deck Winrate ---
    print(f"\n{thin_sep}")
    print(" DECK WINRATE")
    print(thin_sep)
    # Find longest deck name for alignment
    max_name_len = max(len(name) for name in deck_names)
    for name in deck_names:
        s = deck_stats[name]
        total = s['wins'] + s['losses'] + s['draws']
        wr = s['wins'] / total * 100 if total > 0 else 0
        label = name.ljust(max_name_len)
        print(f"  {label}: {s['wins']}W / {s['losses']}L / {s['draws']}D  ({wr:.1f}%)")

    # --- Player Position Winrate ---
    print(f"\n{thin_sep}")
    print(" PLAYER POSITION WINRATE")
    print(thin_sep)
    p1w = player_stats[1]
    p2w = player_stats[2]
    draws = player_stats[None]
    print(f"  Player 1 (26HP, goes 2nd): {p1w} wins ({p1w / total_games * 100:.1f}%)")
    print(f"  Player 2 (20HP, goes 1st): {p2w} wins ({p2w / total_games * 100:.1f}%)")
    print(f"  Draws: {draws} ({draws / total_games * 100:.1f}%)")

    # --- Card Winrate ---
    print(f"\n{thin_sep}")
    print(" CARD WINRATE (by deck inclusion)")
    print(thin_sep)
    # Sort by winrate descending, then by total games descending
    sorted_cards = sorted(
        card_stats.items(),
        key=lambda x: (
            x[1]['wins'] / max(x[1]['wins'] + x[1]['losses'] + x[1]['draws'], 1),
            x[1]['wins'] + x[1]['losses'] + x[1]['draws'],
        ),
        reverse=True,
    )
    max_card_name_len = max(len(name) for name, _ in sorted_cards) if sorted_cards else 0
    for card_name, s in sorted_cards:
        total = s['wins'] + s['losses'] + s['draws']
        wr = s['wins'] / total * 100 if total > 0 else 0
        label = card_name.ljust(max_card_name_len)
        print(f"  {label}: {s['wins']}W / {s['losses']}L / {s['draws']}D  ({wr:.1f}%)")

    # --- Average Turn Count ---
    print(f"\n{thin_sep}")
    print(" AVERAGE TURN COUNT")
    print(thin_sep)
    avg = sum(all_turns) / len(all_turns) if all_turns else 0
    print(f"  Overall: {avg:.1f} turns")
    for (d1, d2), stats in matchup_results.items():
        if stats['turns']:
            mavg = sum(stats['turns']) / len(stats['turns'])
            print(f"  {d1} vs {d2}: {mavg:.1f} turns")

    print(sep)


def main():
    print("=== Super Hard Card Game - AI Simulation ===\n")

    # Load saved decks
    saved_decks = load_saved_decks()

    # Build deck pool: name -> recipe (None = random)
    deck_pool: dict[str, dict[str, int] | None] = {}

    if saved_decks:
        for name, recipe in saved_decks.items():
            deck_pool[name] = recipe
        deck_pool["Random"] = None
        print(f"Loaded {len(saved_decks)} saved deck(s). Added 1 Random deck.")
    else:
        deck_pool["Random 1"] = None
        deck_pool["Random 2"] = None
        print("No saved decks found. Using 2 Random decks.")

    deck_names = list(deck_pool.keys())
    print(f"Decks: {', '.join(deck_names)}\n")

    # Simulation parameters
    num_games = ask_int("Number of games per matchup", default=100)
    cuets_player = ask_int("CUETS for player turn", default=6)
    cuets_opp = ask_int("CUETS for opponent turn", default=3)
    usm_player = ask_int("Unique States Max for player turn", default=300)
    usm_opp = ask_int("Unique States Max for opponent turn", default=60)

    # Generate matchups: all ordered pairs (i, j) where i != j
    matchups = []
    for i, name1 in enumerate(deck_names):
        for j, name2 in enumerate(deck_names):
            if i != j:
                matchups.append((name1, name2))

    total_games = len(matchups) * num_games

    print(f"\nMatchups: {len(matchups)}")
    for d1, d2 in matchups:
        print(f"  {d1} (P1) vs {d2} (P2)")
    print(f"Total games: {total_games}")
    print("=" * 60)

    # Create AIs
    ai1 = MinimaxAI(
        player_number=1,
        cuets_player_turn=cuets_player,
        cuets_opp_turn=cuets_opp,
        unique_states_max_player_turn=usm_player,
        unique_states_max_opp_turn=usm_opp,
    )
    ai2 = MinimaxAI(
        player_number=2,
        cuets_player_turn=cuets_player,
        cuets_opp_turn=cuets_opp,
        unique_states_max_player_turn=usm_player,
        unique_states_max_opp_turn=usm_opp,
    )

    # Tracking stats
    matchup_results: dict[tuple[str, str], dict] = {}
    deck_stats = {name: {'wins': 0, 'losses': 0, 'draws': 0} for name in deck_names}
    player_stats: dict[int | None, int] = {1: 0, 2: 0, None: 0}
    card_stats: dict[str, dict[str, int]] = defaultdict(lambda: {'wins': 0, 'losses': 0, 'draws': 0})
    all_turns: list[int] = []

    games_done = 0
    last_progress = -1

    for deck1_name, deck2_name in matchups:
        deck1_recipe = deck_pool[deck1_name]
        deck2_recipe = deck_pool[deck2_name]

        m_stats = {'p1_wins': 0, 'p2_wins': 0, 'draws': 0, 'turns': []}

        for _ in range(num_games):
            # Build decks (random decks get fresh composition each game)
            deck1 = create_deck(deck1_recipe)
            deck2 = create_deck(deck2_recipe)
            deck1_cards = get_card_names_from_deck(deck1)
            deck2_cards = get_card_names_from_deck(deck2)

            # Simulate game
            winner, turn_count = simulate_single_game(ai1, ai2, deck1, deck2)

            # Track turn count
            all_turns.append(turn_count)
            m_stats['turns'].append(turn_count)

            # Track player position wins
            player_stats[winner] += 1

            # Track matchup results
            if winner == 1:
                m_stats['p1_wins'] += 1
            elif winner == 2:
                m_stats['p2_wins'] += 1
            else:
                m_stats['draws'] += 1

            # Track deck winrate
            if winner == 1:
                deck_stats[deck1_name]['wins'] += 1
                deck_stats[deck2_name]['losses'] += 1
            elif winner == 2:
                deck_stats[deck2_name]['wins'] += 1
                deck_stats[deck1_name]['losses'] += 1
            else:
                deck_stats[deck1_name]['draws'] += 1
                deck_stats[deck2_name]['draws'] += 1

            # Track card winrate (each deck counted separately)
            if winner == 1:
                for card_name in deck1_cards:
                    card_stats[card_name]['wins'] += 1
                for card_name in deck2_cards:
                    card_stats[card_name]['losses'] += 1
            elif winner == 2:
                for card_name in deck2_cards:
                    card_stats[card_name]['wins'] += 1
                for card_name in deck1_cards:
                    card_stats[card_name]['losses'] += 1
            else:
                for card_name in deck1_cards:
                    card_stats[card_name]['draws'] += 1
                for card_name in deck2_cards:
                    card_stats[card_name]['draws'] += 1

            # Progress
            games_done += 1
            progress = int(games_done / total_games * 100)
            if progress > last_progress:
                print(f"Progress: {progress}% ({games_done}/{total_games} games)")
                sys.stdout.flush()
                last_progress = progress

        matchup_results[(deck1_name, deck2_name)] = m_stats

    # Print report
    print_report(
        deck_names,
        deck_pool,
        matchup_results,
        deck_stats,
        player_stats,
        dict(card_stats),
        all_turns,
        total_games,
        num_games,
    )


if __name__ == '__main__':
    main()
