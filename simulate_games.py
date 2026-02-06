"""
AI vs AI Game Simulation Script for Super Hard Card Game.
Simulates multiple games between two AI players and reports win rates.
"""
import random
import argparse
import cards
from ai_player_new import (
    GameStateSnapshot,
    GameSimulator,
    MinimaxAI,
    MAX_FOXTAIL,
)


def create_random_deck() -> list[cards.Card]:
    """Create a random deck using the default card types."""
    card_types = cards.all_card_types
    return [random.choice(card_types)() for _ in range(40)]


def create_game_state() -> GameStateSnapshot:
    """Create a new game state with random decks."""
    state = GameStateSnapshot()
    state.decks[1] = create_random_deck()
    state.decks[2] = create_random_deck()
    state.current_player = 2  # Player 2 goes first (as in the original game)
    return state


def simulate_single_game(ai1: MinimaxAI, ai2: MinimaxAI, max_turns: int = 200) -> int | None:
    """
    Simulate a single game between two AIs.

    Returns:
        1 if player 1 wins, 2 if player 2 wins, None if draw
    """
    state = create_game_state()
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
    """Get the best actions from the AI for the current state."""
    ai.nodes_evaluated = 0

    # Generate and evaluate all possible action sequences
    best_score = float('-inf')
    best_actions = []

    all_sequences = ai._generate_turn_sequences(state, ai.player_number)

    for actions in all_sequences:
        test_state = state.copy()
        valid = True
        for action in actions:
            if not ai._apply_action(test_state, ai.player_number, action):
                valid = False
                break

        if not valid:
            continue

        GameSimulator.end_turn(test_state)
        score = ai._evaluate_state(test_state) if hasattr(ai, '_evaluate_state') else evaluate_state(test_state, ai.player_number)

        ai.nodes_evaluated += 1

        if score > best_score:
            best_score = score
            best_actions = actions

    best_actions.append(('end_turn',))
    return best_actions


def evaluate_state(state: GameStateSnapshot, player: int) -> float:
    """Evaluate the game state from player's perspective."""
    from ai_player_new import Evaluator
    return Evaluator.evaluate(state, player)


def apply_action(state: GameStateSnapshot, player: int, action: tuple) -> bool:
    """Apply an action to the state."""
    from ai_player_new import _find_card_by_id, _find_card_in_zones

    action_type = action[0]

    if action_type == 'play':
        card, target = action[1], action[2]
        actual_card = _find_card_by_id(state.hands[player], card.unique_id)
        if actual_card is None:
            return False

        actual_target = None
        if target is not None:
            actual_target = _find_card_in_zones(state, target.unique_id, player)

        return GameSimulator.play_card(state, player, actual_card, actual_target)

    elif action_type == 'attack':
        attacker, target = action[1], action[2]
        actual_attacker = next(
            (f for f in state.fields[player]
             if f.unique_id == attacker.unique_id and f.can_attack_this_turn),
            None
        )
        if actual_attacker is None:
            return False

        if target == "leader":
            actual_target = "leader"
        else:
            actual_target = _find_card_by_id(state.fields[3 - player], target.unique_id)
            if actual_target is None:
                return False

        return GameSimulator.follower_attack(state, player, actual_attacker, actual_target)

    elif action_type == 'enhance':
        follower, extra_target = action[1], action[2]
        actual_follower = next(
            (f for f in state.fields[player]
             if f.unique_id == follower.unique_id and f.can_enhance),
            None
        )
        if actual_follower is None:
            return False

        actual_target = None
        if extra_target is not None:
            actual_target = _find_card_in_zones(state, extra_target.unique_id, player)

        return GameSimulator.enhance_follower(state, player, actual_follower, actual_target)

    elif action_type == 'draw':
        return GameSimulator.draw_card(state, player)

    return False


def simulate_games(num_games: int, ai_depth: int = 1) -> dict:
    """
    Simulate multiple games and return statistics.

    Args:
        num_games: Number of games to simulate
        ai_depth: Depth for minimax AI (default 1)

    Returns:
        Dictionary with win counts and rates
    """
    import sys

    ai1 = MinimaxAI(player_number=1, max_depth=ai_depth)
    ai2 = MinimaxAI(player_number=2, max_depth=ai_depth)

    wins = {1: 0, 2: 0, None: 0}  # None = draw

    last_progress = -1

    for i in range(num_games):
        # Print progress every 1%
        progress = int((i + 1) / num_games * 100)
        if progress > last_progress:
            print(f"Progress: {progress}% ({i + 1}/{num_games} games)")
            sys.stdout.flush()
            last_progress = progress

        winner = simulate_single_game(ai1, ai2)
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


def main():
    parser = argparse.ArgumentParser(description='Simulate AI vs AI games for Super Hard Card Game')
    parser.add_argument('num_games', type=int, help='Number of games to simulate')
    parser.add_argument('--depth', type=int, default=1, help='AI depth (default: 1)')
    parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducibility')

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        print(f"Random seed set to: {args.seed}")

    print(f"Simulating {args.num_games} games with AI depth {args.depth}...")
    print("=" * 50)

    results = simulate_games(args.num_games, args.depth)

    print("=" * 50)
    print("Results:")
    print(f"  Total games: {results['total_games']}")
    print(f"  Player 1 wins: {results['player1_wins']} ({results['player1_winrate']:.2f}%)")
    print(f"  Player 2 wins: {results['player2_wins']} ({results['player2_winrate']:.2f}%)")
    print(f"  Draws: {results['draws']} ({results['draw_rate']:.2f}%)")


if __name__ == '__main__':
    main()
