"""
AI vs AI Game Simulation Script for Super Hard Card Game.

Automatically loads all saved decks, includes random deck(s),
simulates round-robin matchups, and generates a detailed report.
"""

import copy
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import permutations
from pathlib import Path
from typing import Callable

import shcg_core_cards
from shcg_ai_evaluator import Evaluator
from shcg_ai import BruteForceAI, apply_action as ai_apply_action
from shcg_core_gamestate import SHCGGameState
from shcg_core_error import AIError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DECKS_SAVE_FILE = Path("saved_decks.json")
DEFAULT_EVAL_METHOD = "evaluate_new"
ALT_EVAL_METHOD = "evaluate"
DECK_SIZE = 45
MAX_COPIES_PER_CARD = 3
CARDS_PER_RANDOM_TYPE = 3
RANDOM_TYPE_COUNT = 15

EvalFunc = Callable[[SHCGGameState, int, bool], float]

# ---------------------------------------------------------------------------
# Data classes for cleaner stat tracking
# ---------------------------------------------------------------------------


@dataclass
class WinLossDrawRecord:
    """Tracks wins, losses, and draws."""

    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def total(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def winrate(self) -> float:
        return (self.wins / self.total * 100) if self.total > 0 else 0.0

    def record_result(self, outcome: str) -> None:
        """Record a 'win', 'loss', or 'draw'."""
        if outcome == "win":
            self.wins += 1
        elif outcome == "loss":
            self.losses += 1
        elif outcome == "draw":
            self.draws += 1

    def __str__(self) -> str:
        return f"{self.wins}W / {self.losses}L / {self.draws}D  ({self.winrate:.1f}%)"


@dataclass
class MatchupResult:
    """Statistics for a single deck matchup."""

    p1_wins: int = 0
    p2_wins: int = 0
    draws: int = 0
    turns: list[int] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.p1_wins + self.p2_wins + self.draws

    @property
    def p1_winrate(self) -> float:
        return (self.p1_wins / self.total * 100) if self.total > 0 else 0.0

    @property
    def avg_turns(self) -> float:
        return (sum(self.turns) / len(self.turns)) if self.turns else 0.0

    def record(self, winner: int | None, turn_count: int) -> None:
        if winner == 1:
            self.p1_wins += 1
        elif winner == 2:
            self.p2_wins += 1
        else:
            self.draws += 1
        self.turns.append(turn_count)


@dataclass
class EvalMatchupResult:
    """Statistics for evaluator-comparison matchups."""

    wins_by_method: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    draws: int = 0
    turns: list[int] = field(default_factory=list)

    def record(self, winning_method: str | None, turn_count: int) -> None:
        if winning_method is None:
            self.draws += 1
        else:
            self.wins_by_method[winning_method] += 1
        self.turns.append(turn_count)


@dataclass
class SeatStats:
    """Tracks wins/games broken down by player seat (P1 vs P2)."""

    games_as_p1: int = 0
    games_as_p2: int = 0
    wins_as_p1: int = 0
    wins_as_p2: int = 0

    @property
    def p1_winrate(self) -> float:
        return (self.wins_as_p1 / self.games_as_p1 * 100) if self.games_as_p1 > 0 else 0.0

    @property
    def p2_winrate(self) -> float:
        return (self.wins_as_p2 / self.games_as_p2 * 100) if self.games_as_p2 > 0 else 0.0


# ---------------------------------------------------------------------------
# Card name registry (cached)
# ---------------------------------------------------------------------------

_VALID_CARD_NAMES: set[str] | None = None


def _get_valid_card_names() -> set[str]:
    global _VALID_CARD_NAMES
    if _VALID_CARD_NAMES is None:
        _VALID_CARD_NAMES = {card_type().name for card_type in shcg_core_cards.all_card_types}
    return _VALID_CARD_NAMES


# ---------------------------------------------------------------------------
# Evaluator resolution
# ---------------------------------------------------------------------------


def resolve_evaluator_method(method_name: str) -> EvalFunc:
    """Resolve evaluator method by name and validate it is callable."""
    method = getattr(Evaluator, method_name, None)
    if not callable(method):
        raise AIError(f"Evaluator method '{method_name}' not found or not callable.")
    return method


# ---------------------------------------------------------------------------
# Deck validation / building
# ---------------------------------------------------------------------------


def validate_deck_recipe(recipe: dict[str, int]) -> tuple[bool, str]:
    """Validate deck recipe: exactly 45 cards total, max 3 copies per card."""
    valid_names = _get_valid_card_names()

    for card_name, count in recipe.items():
        if card_name not in valid_names:
            return False, f"unknown card '{card_name}'"
        if not isinstance(count, int) or count < 0:
            return False, f"invalid count for '{card_name}'"
        if count > MAX_COPIES_PER_CARD:
            return False, f"too many copies for '{card_name}' ({count} > {MAX_COPIES_PER_CARD})"

    total = sum(recipe.values())
    if total != DECK_SIZE:
        return False, f"deck must contain exactly {DECK_SIZE} cards (got {total})"

    return True, ""


def load_saved_decks() -> dict[str, dict[str, int]]:
    """Load saved decks from JSON file. Returns empty dict if file not found."""
    if not DECKS_SAVE_FILE.exists():
        return {}

    try:
        data = json.loads(DECKS_SAVE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    raw_decks = data.get("saved_decks")
    if not isinstance(raw_decks, dict):
        return {}

    valid_decks: dict[str, dict[str, int]] = {}
    for name, recipe in raw_decks.items():
        if not isinstance(recipe, dict):
            print(f"  Skipping deck '{name}': invalid recipe format")
            continue
        ok, reason = validate_deck_recipe(recipe)
        if not ok:
            print(f"  Skipping deck '{name}': {reason}")
            continue
        valid_decks[name] = recipe

    return valid_decks


def build_deck_from_recipe(recipe: dict[str, int]) -> list[shcg_core_cards.Card]:
    """Build a shuffled list of Card instances from a deck recipe."""
    ok, reason = validate_deck_recipe(recipe)
    if not ok:
        raise ValueError(f"Invalid deck recipe: {reason}")

    name_to_type = {ct().name: ct for ct in shcg_core_cards.all_card_types}
    deck = [
        name_to_type[name]()
        for name, count in recipe.items()
        for _ in range(count)
    ]
    random.shuffle(deck)
    return deck


def create_random_deck() -> list[shcg_core_cards.Card]:
    """Create a random deck: 15 random card types × 3 copies each."""
    selected = random.sample(shcg_core_cards.all_card_types, RANDOM_TYPE_COUNT)
    deck = [ct() for ct in selected for _ in range(CARDS_PER_RANDOM_TYPE)]
    random.shuffle(deck)
    return deck


def create_deck(recipe: dict[str, int] | None) -> list[shcg_core_cards.Card]:
    """Create a deck from a recipe, or a random deck if recipe is None."""
    return build_deck_from_recipe(recipe) if recipe is not None else create_random_deck()


def get_card_names_from_deck(deck: list[shcg_core_cards.Card]) -> set[str]:
    """Get unique card type names from a deck."""
    return {card.name for card in deck}


# ---------------------------------------------------------------------------
# Game simulation
# ---------------------------------------------------------------------------


def create_initial_state(
    deck1: list[shcg_core_cards.Card],
    deck2: list[shcg_core_cards.Card],
) -> SHCGGameState:
    """Create a new game state with pre-built decks."""
    state = SHCGGameState(current_player=2)  # Player 2 goes first
    state.decks[1] = deck1
    state.decks[2] = deck2
    return state


def get_ai_actions(
    ai: BruteForceAI,
    state: SHCGGameState,
    evaluate_method: EvalFunc,
) -> list[tuple]:
    """
    Get the best actions from the AI for the current state using a pluggable evaluator.

    Mirrors BruteForceAI.get_best_turn_actions() but accepts a custom evaluate_method
    so the evaluator-comparison mode can inject different scoring functions.
    """
    ai.endturnstate_evaluated = 0
    ai.endturnstate_evaluated_additional = 0
    ai.loss_endturnstate_avoided = 0

    best_score = float("-inf")
    best_actions: list[tuple] = []

    all_sequences = ai._generate_random_turn_sequences(
        state,
        ai.player_number,
        ai.continuous_unique_endturnstates_req_player_turn,
        ai.unique_states_max_player_turn,
    )

    for actions in all_sequences:
        test_state = copy.deepcopy(state)
        for action in actions:
            ai_apply_action(test_state, ai.player_number, action, False, False, True)

        test_state.end_turn(False, False)
        score = evaluate_method(test_state, ai.player_number, only_care_about_winorlose=False)

        # Lookahead: simulate opponent's response
        if score not in (float("inf"), float("-inf"), 0.0):
            opp_sequences = ai._generate_random_turn_sequences(
                test_state,
                3 - ai.player_number,
                ai.continuous_unique_endturnstates_req_opp_turn,
                ai.unique_states_max_opp_turn,
            )
            for opp_actions in opp_sequences:
                opp_state = copy.deepcopy(test_state)
                for opp_action in opp_actions:
                    ai_apply_action(opp_state, 3 - ai.player_number, opp_action, False, False, True)

                opp_state.end_turn(False, False)
                opp_score = evaluate_method(
                    opp_state, 3 - ai.player_number, only_care_about_winorlose=True
                )
                ai.endturnstate_evaluated_additional += 1

                if opp_score == float("inf"):
                    score = float("-inf")
                    ai.loss_endturnstate_avoided += 1
                    break

        ai.endturnstate_evaluated += 1

        if score > best_score:
            best_score = score
            best_actions = actions

        if best_score == float("inf"):
            break

    best_actions.append(("end_turn",))
    return best_actions


def _run_game_loop(
    state: SHCGGameState,
    ais: dict[int, BruteForceAI],
    get_eval: Callable[[int], EvalFunc],
    max_turns: int = 200,
    card_play_count: dict[str, int] | None = None,
) -> tuple[int | None, int]:
    """Core game loop shared by both simulation modes."""
    while not state.concluded and state.turn <= max_turns:
        current = state.current_player
        actions = get_ai_actions(ais[current], state, get_eval(current))

        for action in actions:
            if action[0] == "end_turn":
                break
            # Track actual card plays (not AI lookahead)
            if card_play_count is not None and action[0] == "play":
                card_name = action[1].name
                card_play_count[card_name] = card_play_count.get(card_name, 0) + 1
            ai_apply_action(state, current, action, False, False, True)
            if state.concluded:
                break

        if not state.concluded:
            state.end_turn(False, False)

    return state.winner, state.turn


def simulate_single_game(
    ai1: BruteForceAI,
    ai2: BruteForceAI,
    deck1: list[shcg_core_cards.Card],
    deck2: list[shcg_core_cards.Card],
    evaluate_method: EvalFunc,
    max_turns: int = 200,
    card_play_count: dict[str, int] | None = None,
) -> tuple[int | None, int]:
    """Simulate a single game between two AIs using the same evaluator."""
    state = create_initial_state(deck1, deck2)
    return _run_game_loop(
        state, {1: ai1, 2: ai2}, lambda _: evaluate_method, max_turns,
        card_play_count=card_play_count,
    )


def simulate_game_with_methods(
    ai1: BruteForceAI,
    ai2: BruteForceAI,
    deck1: list[shcg_core_cards.Card],
    deck2: list[shcg_core_cards.Card],
    eval_by_player: dict[int, EvalFunc],
    max_turns: int = 200,
) -> tuple[int | None, int]:
    """Simulate a single game where each player uses a different evaluator."""
    state = create_initial_state(deck1, deck2)
    return _run_game_loop(state, {1: ai1, 2: ai2}, lambda p: eval_by_player[p], max_turns)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def ask_int(prompt: str, default: int | None = None) -> int:
    """Ask the user for an integer value."""
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if raw == "" and default is not None:
            return default
        try:
            return int(raw)
        except ValueError:
            print("Please enter a valid integer.")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Ask the user for a yes/no value."""
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{hint}]: ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please enter y or n.")


def ask_choice(prompt: str, options: list[str], default: int = 1) -> int:
    """Ask the user to choose from a numbered list. Returns 1-based index."""
    print(prompt)
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")
    while True:
        raw = input(f"Choice [{default}]: ").strip()
        if raw == "":
            return default
        try:
            val = int(raw)
            if 1 <= val <= len(options):
                return val
            print(f"Please enter a number between 1 and {len(options)}.")
        except ValueError:
            print("Please enter a valid number.")


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------


class ProgressTracker:
    """Simple percentage-based progress printer."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self._last_pct = -1

    def tick(self) -> None:
        self.done += 1
        pct = int(self.done / self.total * 100)
        if pct > self._last_pct:
            print(f"  Progress: {pct}% ({self.done}/{self.total} games)")
            sys.stdout.flush()
            self._last_pct = pct


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

SEPARATOR = "=" * 60
THIN_SEP = "-" * 60


def _pct(n: int, total: int) -> float:
    return (n / total * 100) if total > 0 else 0.0


def print_report(
    deck_names: list[str],
    matchup_results: dict[tuple[str, str], MatchupResult],
    deck_stats: dict[str, WinLossDrawRecord],
    player_stats: dict[int | None, int],
    card_stats: dict[str, WinLossDrawRecord],
    card_play_count: dict[str, int],
    all_turns: list[int],
    total_games: int,
    num_games_per_matchup: int,
) -> None:
    """Print the full simulation report."""

    print(f"\n{SEPARATOR}")
    print("              SIMULATION REPORT")
    print(SEPARATOR)
    print(f"  Decks: {', '.join(deck_names)}")
    print(f"  Matchups: {len(matchup_results)}")
    print(f"  Games per matchup: {num_games_per_matchup}")
    print(f"  Total games: {total_games}")

    # --- Matchup Results ---
    print(f"\n{THIN_SEP}")
    print(" MATCHUP RESULTS")
    print(THIN_SEP)
    for (d1, d2), mr in matchup_results.items():
        print(
            f"  {d1} (P1) vs {d2} (P2): "
            f"{mr.p1_wins}W / {mr.p2_wins}L / {mr.draws}D  "
            f"(P1 winrate: {mr.p1_winrate:.1f}%)"
        )

    # --- Deck Winrate ---
    print(f"\n{THIN_SEP}")
    print(" DECK WINRATE")
    print(THIN_SEP)
    pad = max(len(n) for n in deck_names)
    for name in deck_names:
        print(f"  {name:<{pad}}: {deck_stats[name]}")

    # --- Player Position Winrate ---
    print(f"\n{THIN_SEP}")
    print(" PLAYER POSITION WINRATE")
    print(THIN_SEP)
    p1w, p2w, draws = player_stats[1], player_stats[2], player_stats[None]
    print(f"  Player 1 (26HP, goes 2nd): {p1w} wins ({_pct(p1w, total_games):.1f}%)")
    print(f"  Player 2 (20HP, goes 1st): {p2w} wins ({_pct(p2w, total_games):.1f}%)")
    print(f"  Draws: {draws} ({_pct(draws, total_games):.1f}%)")

    # --- Card Winrate ---
    print(f"\n{THIN_SEP}")
    print(" CARD WINRATE (by deck inclusion)")
    print(THIN_SEP)
    sorted_cards = sorted(
        card_stats.items(),
        key=lambda item: (item[1].winrate, item[1].total),
        reverse=True,
    )
    card_pad = max((len(n) for n, _ in sorted_cards), default=0)
    for name, record in sorted_cards:
        plays = card_play_count.get(name, 0)
        print(f"  {name:<{card_pad}}: {record}  (played {plays} times)")

    # --- Average Turn Count ---
    print(f"\n{THIN_SEP}")
    print(" AVERAGE TURN COUNT")
    print(THIN_SEP)
    avg = sum(all_turns) / len(all_turns) if all_turns else 0
    print(f"  Overall: {avg:.1f} turns")
    for (d1, d2), mr in matchup_results.items():
        if mr.turns:
            print(f"  {d1} vs {d2}: {mr.avg_turns:.1f} turns")

    print(SEPARATOR)


def print_evaluator_comparison_report(
    deck_names: list[str],
    matchup_results: dict[tuple[str, str], EvalMatchupResult],
    method_stats: dict[str, WinLossDrawRecord],
    seat_stats: dict[str, SeatStats],
    all_turns: list[int],
    total_games: int,
    num_games_per_matchup: int,
) -> None:
    """Print evaluator comparison report."""

    print(f"\n{SEPARATOR}")
    print("     EVALUATOR COMPARISON REPORT")
    print(SEPARATOR)
    print(f"  Decks: {', '.join(deck_names)}")
    print(f"  Matchups: {len(matchup_results)}")
    print(f"  Games per matchup: {num_games_per_matchup}")
    print(f"  Total games: {total_games}")

    print(f"\n{THIN_SEP}")
    print(" OVERALL RESULTS")
    print(THIN_SEP)
    for name, record in method_stats.items():
        print(f"  {name}: {record}")

    print(f"\n{THIN_SEP}")
    print(" PLAYER POSITION")
    print(THIN_SEP)
    for name, ss in seat_stats.items():
        print(
            f"  {name}: "
            f"P1 {ss.wins_as_p1}W/{ss.games_as_p1}G ({ss.p1_winrate:.1f}%), "
            f"P2 {ss.wins_as_p2}W/{ss.games_as_p2}G ({ss.p2_winrate:.1f}%)"
        )

    print(f"\n{THIN_SEP}")
    print(" MATCHUP RESULTS")
    print(THIN_SEP)
    for (d1, d2), mr in matchup_results.items():
        dw = mr.wins_by_method.get(DEFAULT_EVAL_METHOD, 0)
        aw = mr.wins_by_method.get(ALT_EVAL_METHOD, 0)
        total = dw + aw + mr.draws
        print(
            f"  {d1} vs {d2}: "
            f"{DEFAULT_EVAL_METHOD} {dw}W ({_pct(dw, total):.1f}%), "
            f"{ALT_EVAL_METHOD} {aw}W ({_pct(aw, total):.1f}%), "
            f"Draw {mr.draws}"
        )

    print(SEPARATOR)


# ---------------------------------------------------------------------------
# AI factory
# ---------------------------------------------------------------------------


def create_ai_pair(
    cuets_player: int,
    cuets_opp: int,
    usm_player: int,
    usm_opp: int,
) -> tuple[BruteForceAI, BruteForceAI]:
    """Create a pair of BruteForceAI players with the given parameters."""
    kwargs = dict(
        cuets_player_turn=cuets_player,
        cuets_opp_turn=cuets_opp,
        unique_states_max_player_turn=usm_player,
        unique_states_max_opp_turn=usm_opp,
    )
    return BruteForceAI(player_number=1, **kwargs), BruteForceAI(player_number=2, **kwargs)


# ----------------------------------------------------
# Simulation runners
# ---------------------------------------------------------------------------


def run_evaluator_comparison(
    ai1: BruteForceAI,
    ai2: BruteForceAI,
    deck_names: list[str],
    deck_pool: dict[str, dict[str, int] | None],
    matchups: list[tuple[str, str]],
    num_games: int,
    total_games: int,
) -> None:
    """Run evaluator-comparison mode and print the report."""
    try:
        eval_methods = {
            DEFAULT_EVAL_METHOD: resolve_evaluator_method(DEFAULT_EVAL_METHOD),
            ALT_EVAL_METHOD: resolve_evaluator_method(ALT_EVAL_METHOD),
        }
    except AIError as exc:
        print(f"Error: {exc}")
        print("Please implement both evaluator methods on Evaluator with the same signature.")
        return

    print(f"Comparison mode: {DEFAULT_EVAL_METHOD} vs {ALT_EVAL_METHOD}")

    matchup_results: dict[tuple[str, str], EvalMatchupResult] = {}
    method_stats = {name: WinLossDrawRecord() for name in eval_methods}
    seat_stats = {name: SeatStats() for name in eval_methods}
    all_turns: list[int] = []
    progress = ProgressTracker(total_games)

    for deck1_name, deck2_name in matchups:
        mr = EvalMatchupResult()

        for game_idx in range(num_games):
            deck1 = create_deck(deck_pool[deck1_name])
            deck2 = create_deck(deck_pool[deck2_name])

            # Alternate seat assignments each game
            if game_idx % 2 == 0:
                method_by_player = {1: DEFAULT_EVAL_METHOD, 2: ALT_EVAL_METHOD}
            else:
                method_by_player = {1: ALT_EVAL_METHOD, 2: DEFAULT_EVAL_METHOD}

            eval_by_player = {p: eval_methods[m] for p, m in method_by_player.items()}

            for p, m in method_by_player.items():
                ss = seat_stats[m]
                if p == 1:
                    ss.games_as_p1 += 1
                else:
                    ss.games_as_p2 += 1

            winner, turn_count = simulate_game_with_methods(
                ai1, ai2, deck1, deck2, eval_by_player,
            )
            all_turns.append(turn_count)

            if winner is None:
                winning_method = None
                for m in eval_methods:
                    method_stats[m].record_result("draw")
            else:
                winning_method = method_by_player[winner]
                losing_method = method_by_player[3 - winner]
                method_stats[winning_method].record_result("win")
                method_stats[losing_method].record_result("loss")
                ss = seat_stats[winning_method]
                if winner == 1:
                    ss.wins_as_p1 += 1
                else:
                    ss.wins_as_p2 += 1

            mr.record(winning_method, turn_count)
            progress.tick()

        matchup_results[(deck1_name, deck2_name)] = mr

    print_evaluator_comparison_report(
        deck_names, matchup_results, method_stats, seat_stats,
        all_turns, total_games, num_games,
    )


def run_standard_simulation(
    ai1: BruteForceAI,
    ai2: BruteForceAI,
    deck_names: list[str],
    deck_pool: dict[str, dict[str, int] | None],
    matchups: list[tuple[str, str]],
    num_games: int,
    total_games: int,
) -> None:
    """Run standard simulation mode and print the report."""
    try:
        evaluate_method = resolve_evaluator_method(DEFAULT_EVAL_METHOD)
    except AIError as exc:
        print(f"Error: {exc}")
        return

    print(f"Using evaluator: {DEFAULT_EVAL_METHOD}")

    matchup_results: dict[tuple[str, str], MatchupResult] = {}
    deck_stats = {name: WinLossDrawRecord() for name in deck_names}
    player_stats: dict[int | None, int] = {1: 0, 2: 0, None: 0}
    card_stats: dict[str, WinLossDrawRecord] = defaultdict(WinLossDrawRecord)
    card_play_count: dict[str, int] = defaultdict(int)
    all_turns: list[int] = []
    progress = ProgressTracker(total_games)

    for deck1_name, deck2_name in matchups:
        mr = MatchupResult()

        for _ in range(num_games):
            deck1 = create_deck(deck_pool[deck1_name])
            deck2 = create_deck(deck_pool[deck2_name])
            deck1_cards = get_card_names_from_deck(deck1)
            deck2_cards = get_card_names_from_deck(deck2)

            winner, turn_count = simulate_single_game(
                ai1, ai2, deck1, deck2, evaluate_method,
                card_play_count=card_play_count,
            )

            all_turns.append(turn_count)
            mr.record(winner, turn_count)
            player_stats[winner] += 1

            # Update deck and card stats
            _record_deck_and_card_stats(
                winner, deck1_name, deck2_name,
                deck1_cards, deck2_cards,
                deck_stats, card_stats,
            )
            progress.tick()

        matchup_results[(deck1_name, deck2_name)] = mr

    print_report(
        deck_names, matchup_results, deck_stats, player_stats,
        dict(card_stats), dict(card_play_count), all_turns, total_games, num_games,
    )


def _record_deck_and_card_stats(
    winner: int | None,
    deck1_name: str,
    deck2_name: str,
    deck1_cards: set[str],
    deck2_cards: set[str],
    deck_stats: dict[str, WinLossDrawRecord],
    card_stats: dict[str, WinLossDrawRecord],
) -> None:
    """Update deck-level and card-level win/loss/draw statistics."""
    outcomes = {
        1: ("win", "loss"),
        2: ("loss", "win"),
        None: ("draw", "draw"),
    }
    d1_outcome, d2_outcome = outcomes[winner]

    deck_stats[deck1_name].record_result(d1_outcome)
    deck_stats[deck2_name].record_result(d2_outcome)

    for name in deck1_cards:
        card_stats[name].record_result(d1_outcome)
    for name in deck2_cards:
        card_stats[name].record_result(d2_outcome)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Super Hard Card Game - AI Simulation ===\n")

    # Load saved decks
    saved_decks = load_saved_decks()

    deck_pool: dict[str, dict[str, int] | None] = {}
    if saved_decks:
        deck_pool.update(saved_decks)
        print(f"Loaded {len(saved_decks)} saved deck(s).")

        if len(saved_decks) >= 2:
            if ask_yes_no("Include a Random deck?", default=False):
                deck_pool["Random"] = None
                print("Added 1 Random deck.")
        else:
            # Only 1 saved deck — need at least 2 for matchups
            deck_pool["Random"] = None
            print("Added 1 Random deck (need at least 2 decks for matchups).")
    else:
        deck_pool["Random 1"] = None
        deck_pool["Random 2"] = None
        print("No saved decks found. Using 2 Random decks.")

    deck_names = list(deck_pool.keys())
    print(f"Decks: {', '.join(deck_names)}\n")

    # Matchup mode selection
    if len(deck_names) >= 3:
        mode_choice = ask_choice(
            "Matchup mode:",
            ["Round-robin (all vs all)", "One deck vs all others"],
            default=1,
        )
    else:
        mode_choice = 1  # Only round-robin makes sense with 2 decks

    focus_deck: str | None = None
    if mode_choice == 2:
        focus_idx = ask_choice(
            "Select the focus deck:",
            deck_names,
            default=1,
        )
        focus_deck = deck_names[focus_idx - 1]
        print(f"Focus deck: {focus_deck}")

    # Simulation parameters
    num_games = ask_int("Number of games per matchup", default=100)
    cuets_player = ask_int("CUETS for player turn", default=6)
    cuets_opp = ask_int("CUETS for opponent turn", default=3)
    usm_player = ask_int("Unique States Max for player turn", default=100)
    usm_opp = ask_int("Unique States Max for opponent turn", default=20)
    compare_evaluators = ask_yes_no(
        f"Compare evaluators ({DEFAULT_EVAL_METHOD} vs {ALT_EVAL_METHOD})",
        default=False,
    )

    # Generate matchups based on mode
    if focus_deck is not None:
        # One deck vs all others (both seat orders)
        others = [n for n in deck_names if n != focus_deck]
        matchups = []
        for other in others:
            matchups.append((focus_deck, other))
            matchups.append((other, focus_deck))
    else:
        # Round-robin: all ordered pairs (i, j) where i ≠ j
        matchups = [(a, b) for a, b in permutations(deck_names, 2)]

    total_games = len(matchups) * num_games

    print(f"\nMatchups: {len(matchups)}")
    for d1, d2 in matchups:
        print(f"  {d1} (P1) vs {d2} (P2)")
    print(f"Total games: {total_games}")
    print(SEPARATOR)

    ai1, ai2 = create_ai_pair(cuets_player, cuets_opp, usm_player, usm_opp)

    if compare_evaluators:
        run_evaluator_comparison(
            ai1, ai2, deck_names, deck_pool, matchups, num_games, total_games,
        )
    else:
        run_standard_simulation(
            ai1, ai2, deck_names, deck_pool, matchups, num_games, total_games,
        )


if __name__ == "__main__":
    main()
