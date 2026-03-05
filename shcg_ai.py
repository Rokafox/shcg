"""
Chess-like AI Player for Super Hard Card Game.
Uses minimax with alpha-beta pruning to calculate optimal moves.
Since all information is open (hands, decks, fields), this is a perfect information game.
"""
import copy
import datetime
import itertools
import os
import shcg_core_cards
import shcg_core_error
import random
from typing import TYPE_CHECKING, List, Tuple, Any, Optional
from shcg_ai_evaluator import Evaluator
from shcg_core_gamestate import SHCGGameState


# AI constants
DEFAULT_AI_ACTION_DELAY_MS = 600
SINGLE_ACTION_SEQ_MAX_LENGTH = 30


def find_card_by_id(card_list: List[shcg_core_cards.Card], unique_id) -> Optional[shcg_core_cards.Card]:
    """Find a card in a list by its unique_id."""
    for card in card_list:
        if str(card.unique_id) == str(unique_id):
            return card
    return None


def find_card_in_zones(state, unique_id, player: int) -> Optional[shcg_core_cards.Card]:
    """
    Find a card by unique_id across all zones for both players.
    """
    all_cards = (
        state.fields[player] + state.fields[3 - player] +
        state.hands[player] + state.hands[3 - player] +
        state.decks[player] + state.decks[3 - player] +
        state.graveyard[player] + state.graveyard[3 - player] +
        state.banished[player] + state.banished[3 - player]
    )
    return find_card_by_id(all_cards, unique_id)


def find_card_by_void_id(card_list: List[shcg_core_cards.Card], void_id) -> Optional[shcg_core_cards.Card]:
    for card in card_list:
        if str(card.void_id) == str(void_id):
            return card
    return None


def find_card_in_zones_by_void_id(state, void_id, player: int) -> Optional[shcg_core_cards.Card]:
    all_cards = (
        state.fields[player] + state.fields[3 - player] +
        state.hands[player] + state.hands[3 - player] +
        state.decks[player] + state.decks[3 - player] +
        state.graveyard[player] + state.graveyard[3 - player] +
        state.banished[player] + state.banished[3 - player]
    )
    return find_card_by_void_id(all_cards, void_id)


class MoveGenerator:
    """
    Generates all possible moves/actions from a game state.
    """

    @staticmethod
    def _get_targets_for_selection_type(sel_type: str, state: SHCGGameState, player: int) -> list:
        """Get list of valid targets for a given selection type."""
        match sel_type:
            case "field":
                return [f for f in state.fields[player] if isinstance(f, shcg_core_cards.Follower)]
            case "field_opponent":
                return [f for f in state.fields[3 - player] if isinstance(f, shcg_core_cards.Follower)]
            case "field_both":
                return [f for f in state.fields[player] + state.fields[3 - player] if isinstance(f, shcg_core_cards.Follower)]
            case "hand":
                return list(state.hands[player])
            case "hand_follower":
                return [c for c in state.hands[player] if isinstance(c, shcg_core_cards.Follower)]
            case "hand_spell":
                return [c for c in state.hands[player] if isinstance(c, shcg_core_cards.Spell)]
            case "hand_follower_aiteru":
                return [c for c in state.hands[player] if c.type == 'follower' and c.cost <= len([x for x in state.hands[player] if x.type == 'follower'])]
            case "hand_opponent":
                return list(state.hands[3 - player])
            case "hand_opponent_follower":
                return [c for c in state.hands[3 - player] if isinstance(c, shcg_core_cards.Follower)]
            case "hand_opp_f_rush":
                return [c for c in state.hands[3 - player] if isinstance(c, shcg_core_cards.Follower) and (c.ability_rush or c.ability_super_rush)]
            case "field_c":
                return list(state.fields[player])
            case "field_opponent_c":
                return list(state.fields[3 - player])
            case "field_both_c":
                return list(state.fields[player] + state.fields[3 - player])
            case _:
                raise shcg_core_error.TimeError(f"Unknown selection type: {sel_type}") 

    @staticmethod
    def get_playable_cards(state: SHCGGameState, player: int) -> List[Tuple]:
        """
        Get all playable cards with their targets and effect choice, if any.
        Returns list of (card, targets_list, effect_choice, multi_targets) tuples.
        targets_list is a list of selected cards (one per step) or None.
        multi_targets is independent and can co-exist.
        """
        playable = []
        hand = state.hands[player]
        foxtail = state.foxtail[player]
        field_count = len(state.fields[player])

        for card in hand:
            if card.cost > foxtail:
                continue
            if card.type != 'spell' and field_count >= 5:
                continue
            if not card.ai_meet_play_condition(state, player):
                continue
            # o0: card, o1: targets list, o2: effect choice, o3: multi targets
            o0 = card
            o1_possible_values = [None]  # list-of-targets selection combos
            o2_possible_values = [None]  # effect choices
            o3_possible_values = [None]  # multi selection target combos

            # Handle card selection list (each element is one selection step)
            if card.request_card_selection_on_play:
                step_options = []
                for sel_type in card.request_card_selection_on_play:
                    targets = MoveGenerator._get_targets_for_selection_type(sel_type, state, player)
                    if targets:
                        step_options.append(targets)
                    else:
                        step_options.append([None])
                # Cartesian product of all steps: each combo is a tuple of one target per step
                # example step_options = [[A, B], [C, D]] -> o1_possible_values = [[A, C], [A, D], [B, C], [B, D]]
                # another_example: step_options = [[A, B, C, D, E], [None]] -> o1_possible_values = [[A, None], [B, None], [C, None], [D, None], [E, None]]
                o1_possible_values = [list(combo) for combo in itertools.product(*step_options)]

            # Handle multi-card selection on play (up to N targets, independent from per-step)
            if card.request_multi_card_selection_on_play[0]:
                sel_type, max_count = card.request_multi_card_selection_on_play
                multi_targets = MoveGenerator._get_targets_for_selection_type(sel_type, state, player)
                if multi_targets:
                    combos = []
                    # example: multi_targets = [A, B, C], max_count = 2 -> combos = [[A], [B], [C], [A, B], [A, C], [B, C]]
                    # another_example: multi_targets = [A, B, C], max_count = 5 -> combos = [[A], [B], [C], [A, B], [A, C], [B, C], [A, B, C]] (since max_count > len(multi_targets), we can select all)
                    for count in range(1, min(max_count, len(multi_targets)) + 1):
                        for combo in itertools.combinations(multi_targets, count):
                            combos.append(list(combo))
                    o3_possible_values = combos

            # Handle effect choice options
            if card.request_effect_choose_option:
                o2_possible_values = card.request_effect_choose_option

            # Combine: cartesian product of targets list, effect choices, and multi targets
            for targets_list, effect_choice, multi_target in itertools.product(o1_possible_values, o2_possible_values, o3_possible_values):
                playable.append((o0, targets_list, effect_choice, multi_target))

        return playable

    @staticmethod
    def get_possible_attacks(state: SHCGGameState, player: int) -> List[Tuple[shcg_core_cards.Follower, shcg_core_cards.Follower | str]]:
        """
        Get all possible attacks.
        Returns list of (attacker, target) tuples. Target is Follower or "leader".
        """
        attacks = []
        opponent = 3 - player

        # check if opponent has any followers with ability_protect
        # if so, only those followers can be attacked
        protect_exists = any([c.ability_protect for c in state.fields[opponent] if isinstance(c, shcg_core_cards.Follower)])
        for follower in state.fields[player]:
            if follower.type != 'follower':
                continue
            if not follower.can_attack_this_turn or follower.attack_ability <= 0:
                continue

            if protect_exists:
                # Can only attack followers with ability_protect
                for target in state.fields[opponent]:
                    if target.type == 'follower' and target.ability_protect:
                        attacks.append((follower, target))
            else:
                # Can attack opponent followers
                for target in state.fields[opponent]:
                    if target.type == 'follower':
                        attacks.append((follower, target))

                # Can attack leader if attack_ability >= 2
                if follower.attack_ability >= 2:
                    attacks.append((follower, "leader"))

        return attacks

    @staticmethod
    def get_enhanceable_followers(state: SHCGGameState, player: int) -> List[Tuple]:
        """Get all followers that can be enhanced, with optional targets list, effect choice and multi targets.
        Returns list of (follower, targets_list, effect_choice, multi_targets) tuples."""
        if state.enhance_used_this_turn[player] >= state.max_enhance_allowed_per_turn[player]:
            return []
        if state.foxtail[player] < 1:
            return []

        enhanceable = []
        for follower in state.fields[player]:
            if follower.type == 'follower' and hasattr(follower, 'can_enhance') and follower.can_enhance:
                # Build targets list options (per-step selection, now a list)
                target_list_options = [None]
                if follower.request_card_selection_on_enhance:
                    step_options = []
                    for sel_type in follower.request_card_selection_on_enhance:
                        targets = MoveGenerator._get_targets_for_selection_type(sel_type, state, player)
                        if targets:
                            step_options.append(targets)
                        else:
                            step_options.append([None])
                    target_list_options = [list(combo) for combo in itertools.product(*step_options)]

                # Build list of multi-card target options
                multi_target_options = [None]
                if follower.request_multi_card_selection_on_enhance[0]:
                    sel_type, max_count = follower.request_multi_card_selection_on_enhance
                    multi_targets = MoveGenerator._get_targets_for_selection_type(sel_type, state, player)
                    if multi_targets:
                        combos = []
                        for count in range(1, min(max_count, len(multi_targets)) + 1):
                            for combo in itertools.combinations(multi_targets, count):
                                combos.append(list(combo))
                        multi_target_options = combos

                # Build list of effect choice options
                effect_options = follower.request_effect_choose_option_e if follower.request_effect_choose_option_e else [None]

                # Cartesian product of targets list, effect choices, and multi targets
                for targets_list, effect_choice, multi_target in itertools.product(target_list_options, effect_options, multi_target_options):
                    enhanceable.append((follower, targets_list, effect_choice, multi_target))
        return enhanceable

    @staticmethod
    def can_draw_card(state: SHCGGameState, player: int) -> bool:
        """Check if the player can draw a card."""
        return (state.foxtail[player] >= 1 and
                len(state.hands[player]) < 9 and
                len(state.decks[player]) > 0)


class BruteForceAI:
    """
    Not intelligent at all.
    """
    def __init__(self, player_number: int, cuets_player_turn: int, cuets_opp_turn: int, unique_states_max_player_turn: int,
                 unique_states_max_opp_turn: int):
        self.player_number = player_number
        self.endturnstate_evaluated = 0
        self.endturnstate_evaluated_additional = 0
        self.loss_endturnstate_avoided = 0
        self.best_actions: List[Tuple[str, Any]] = []
        self.continuous_unique_endturnstates_req_player_turn = cuets_player_turn # CUETS
        self.continuous_unique_endturnstates_req_opp_turn = cuets_opp_turn
        self.unique_states_max_player_turn = unique_states_max_player_turn
        self.unique_states_max_opp_turn = unique_states_max_opp_turn

    def get_best_turn_actions(self, game_state: SHCGGameState) -> List[Tuple]:
        """
        Calculate and return the best sequence of actions for this turn.
        Written and Verified by Rokafox on 2026/02/05
        """
        # print(f"{self.continuous_unique_endturnstates_req_player_turn}, {self.continuous_unique_endturnstates_req_opp_turn}, {self.unique_states_max_player_turn}, {self.unique_states_max_opp_turn}")
        self.endturnstate_evaluated = 0
        self.endturnstate_evaluated_additional = 0
        self.loss_endturnstate_avoided = 0

        # Find all possible turn action sequences and evaluate them
        best_score = float('-inf')
        best_actions = []

        # Generate and evaluate possible action sequences
        all_sequences = self._generate_random_turn_sequences(game_state, self.player_number, 
                                                             self.continuous_unique_endturnstates_req_player_turn, 
                                                             self.unique_states_max_player_turn)

        # rare case: all_sequences is empty, meaning no action is possible, just end turn.
        if not all_sequences:
            self.best_actions = [('end_turn',)]
            return self.best_actions

        for actions in all_sequences:
            # Apply actions to a copy of the state
            test_state = copy.deepcopy(game_state)
            for action in actions:
                apply_action(test_state, self.player_number, action, False, False, True)

            if not test_state.concluded:
                test_state.end_turn(False, False)
                score = Evaluator.evaluate_new(test_state, self.player_number, only_care_about_winorlose=False) # Basic evaluation
            else:
                score = (float('inf') if test_state.winner == self.player_number else float('-inf') if test_state.winner == 3 - self.player_number else 0.0)

            # Advanced evaluation: simulate opponent's turn
            # If opponent scores inf for any seq, its a loss for us and set score to -inf.
            # This part can be skipped if the player is already winning (score == inf)
            # or losing (score == -inf) as checked in True basic_lethal_check or draw (score == 0.0)
            # hp <= 12 threshold as lethal line
            if score not in (float("inf"), float("-inf"), 0.0) and test_state.hp[self.player_number] <= 12:
                opponent_sequences = self._generate_random_turn_sequences(test_state, 3 - self.player_number, 
                                                                          self.continuous_unique_endturnstates_req_opp_turn, 
                                                                          self.unique_states_max_opp_turn)
                for single_opp_seq in opponent_sequences:
                    opp_test_state = copy.deepcopy(test_state)
                    for opp_action in single_opp_seq:
                        apply_action(opp_test_state, test_state.current_player, opp_action, False, False, True)

                    if not opp_test_state.concluded:
                        # End opponent's turn
                        opp_test_state.end_turn(False, False)
                        # No basic lethal check. Only matters if opponent can score infinity here
                        opp_score = Evaluator.evaluate_new(opp_test_state, 3 - self.player_number, only_care_about_winorlose=True)
                    else:
                        opp_score = (float('inf') if opp_test_state.winner == 3 - self.player_number else 0.0) # dont care about other scores
                    self.endturnstate_evaluated_additional += 1

                    if opp_score == float('inf'):
                        # Opponent can win, so this is a loss for us
                        score = float('-inf')
                        break
                    else:
                        pass
            else:
                pass
                # print("Advanced evaluation skipped due to definitive score.")

            self.endturnstate_evaluated += 1

            if score == float('-inf'):
                self.loss_endturnstate_avoided += 1

            if score > best_score:
                best_score = score
                best_actions = actions

            # No need for more if infinite score
            if best_score == float('inf'):
                break

        # Add end_turn action
        best_actions.append(('end_turn',))
        self.best_actions = best_actions

        return best_actions


    def _generate_random_turn_sequences(self, state: SHCGGameState, player: int,
                                        min_continuous_visited_state_req: int, max_unique_states: int
                                        ) -> List[List[Tuple]]:
        """
        Generate random reasonable action sequences for a turn.
        min_continuous_visited_state_req: Stop If the end result same state is visited this many times continuously.
        This value should be high enough to allow many more thorough explorations.
        Only terminal sequences are accepted (foxtail=0 or no more actions possible)
        Verified by Rokafox on 2026/03/02
        """
        bundle_of_all_action_sequences = []
        visited_states = set()
        continuous_visited_state_count = 0
        current_state = copy.deepcopy(state) # the original environment
        single_action_seq = []
        all_roads_lose = 0

        while continuous_visited_state_count < min_continuous_visited_state_req and len(visited_states) < max_unique_states:
            # do: generate single action sequences until requirement is met
            # single_action_seq too long? Maybe a infinite loop.
            if len(single_action_seq) > SINGLE_ACTION_SEQ_MAX_LENGTH:
                print("Action sequence too long. Resetting.")
                next_possible_actions = [] # force stop and reset
            elif current_state.concluded:
                # if the game is already concluded, no more action is possible, stop and reset
                if current_state.winner == player:
                    # already winning, add this single action sequence to the beginning of the bundle, since it is the best possible outcome.
                    if single_action_seq:
                        bundle_of_all_action_sequences.insert(0, single_action_seq)
                    break
                else:
                    if all_roads_lose >= max_unique_states:
                        return []
                    # obvious mistake during your turn, troll.
                    current_state = copy.deepcopy(state)
                    single_action_seq = []
                    # WARNING: in rare cases, every move leads to a loss, change this if this is possible.
                    all_roads_lose += 1
                    continue
            else:
                next_possible_actions: list[tuple] = self._get_all_actions(current_state, player)

            if not next_possible_actions: # if terminal state
                # hash, compare, if in visited_states, increase continuous_visited_state_count
                # else reset continuous_visited_state_count
                state_hash = current_state.compute_state_hash()
                if state_hash in visited_states:
                    continuous_visited_state_count += 1
                else:
                    visited_states.add(state_hash)
                    continuous_visited_state_count = 0
                    # 2026-02-05: No need to add the action sequence if exact same state is reached,
                    # stop. This single action sequence is concluded.
                    if single_action_seq:
                        bundle_of_all_action_sequences.append(single_action_seq)
                    else:
                        # no action is possible, meaning it is already terminal state
                        pass
                # either way, reset for finding next single action sequence
                current_state = copy.deepcopy(state)
                single_action_seq = []
                continue
            else: # should continue
                pass 

            action = random.choice(next_possible_actions)
            apply_action(current_state, player, action, False, False, True)
            single_action_seq.append(action)

        return bundle_of_all_action_sequences

    def _get_all_actions(self, state: SHCGGameState, player: int) -> List[Tuple]:
        """
        Get all possible actions from current state.
        Other than draw, action[1] is the card/follower template (with unique_id).
        """
        actions = []

        # Play cards
        for card, target, effect_choice, multi_targets in MoveGenerator.get_playable_cards(state, player):
            actions.append(('play', card, target, effect_choice, multi_targets))

        # Attacks
        for attacker, target in MoveGenerator.get_possible_attacks(state, player):
            actions.append(('attack', attacker, target))

        # Enhance
        for follower, target, effect_choice, multi_targets in MoveGenerator.get_enhanceable_followers(state, player):
            actions.append(('enhance', follower, target, effect_choice, multi_targets))

        # Draw
        if MoveGenerator.can_draw_card(state, player):
            actions.append(('draw',))

        # Not Attack
        # If there is only attack left in actions, it is a terminal state. The AI have a small chance to not attack. 
        # Sometimes attack may not be the best move. Maybe 30%?
        # Added on 2026-02-21 by Rokafox
        if all([a[0] == 'attack' for a in actions]):
            if random.random() < 0.3:
                actions.clear()

        return actions


def apply_action(state: SHCGGameState, player: int, action: Tuple,
                 ui_draw: bool, ui_set_text: bool, is_ai_player: bool) -> list[Tuple]:
    """
    Apply an action to a game state.
    """
    try:
        return _apply_action_impl(state, player, action, ui_draw, ui_set_text, is_ai_player)
    except Exception as e:
        try:
            error_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "games_error")
            os.makedirs(error_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            save_path = os.path.join(error_dir, f"error_{timestamp}.json")
            state_string = state.serialize_to_string()
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(state_string)
            print(f"[apply_action] Error saved to {save_path}: {e}")
        except Exception as save_err:
            print(f"[apply_action] Could not save error state: {save_err}")
        raise


def _apply_action_impl(state: SHCGGameState, player: int, action: Tuple,
                       ui_draw: bool, ui_set_text: bool, is_ai_player: bool) -> list[Tuple]:
    action_type = action[0]

    if action_type == 'play':
        card, targets_template, effect_choice = action[1], action[2], action[3]
        multi_targets_template = action[4] if len(action) > 4 else None
        if card.is_generated:
            actual_card = find_card_by_void_id(state.hands[player], card.void_id)
        else:
            actual_card = find_card_by_id(state.hands[player], card.unique_id)
        if actual_card is None:
            raise shcg_core_error.CardNotFoundError(f"Card to play not found in hand: {card} with void_id {card.void_id} and unique_id {card.unique_id}")

        # Resolve targets list (one per selection step)
        actual_targets = None
        if targets_template is not None:
            actual_targets = []
            for t in targets_template:
                if t is None:
                    actual_targets.append(None)
                elif t.is_generated:
                    at = find_card_in_zones_by_void_id(state, t.void_id, player)
                    if at is None:
                        raise shcg_core_error.CardNotFoundError(f"Target for card play not found: {t}")
                    actual_targets.append(at)
                else:
                    at = find_card_in_zones(state, t.unique_id, player)
                    if at is None:
                        raise shcg_core_error.CardNotFoundError(f"Target for card play not found: {t}")
                    actual_targets.append(at)

        # Resolve multi targets
        actual_multi_targets = None
        if multi_targets_template is not None:
            actual_multi_targets = []
            for t in multi_targets_template:
                if t.is_generated:
                    at = find_card_in_zones_by_void_id(state, t.void_id, player)
                else:
                    at = find_card_in_zones(state, t.unique_id, player)
                if at is None:
                    raise shcg_core_error.CardNotFoundError(f"Multi-target for card play not found: {t}")
                actual_multi_targets.append(at)

        state.play_card(player, actual_card, ui_draw, ui_set_text, actual_targets, is_ai_player, effect_choice,
                        additional_multi_targets=actual_multi_targets)
        return [('play', actual_card)]

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
            raise shcg_core_error.CardNotFoundError(f"Attacker not found on field: {attacker}")

        if target == "leader":
            actual_target = "leader"
        else:
            if target.is_generated:
                actual_target = find_card_by_void_id(state.fields[3 - player], target.void_id)
            else:
                actual_target = find_card_by_id(state.fields[3 - player], target.unique_id)
            if actual_target is None:
                raise shcg_core_error.CardNotFoundError(f"Attack target not found on field: {target}")

        state.follower_attack(player, actual_attacker, actual_target, ui_draw, ui_set_text)
        return [('attack', actual_attacker, actual_target)]

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
            raise shcg_core_error.CardNotFoundError(f"Follower to enhance not found on field: {follower}")

        # Resolve targets list (one per selection step)
        actual_targets = None
        if targets_template is not None:
            actual_targets = []
            for t in targets_template:
                if t is None:
                    actual_targets.append(None)
                elif t.is_generated:
                    at = find_card_in_zones_by_void_id(state, t.void_id, player)
                    if at is None:
                        raise shcg_core_error.CardNotFoundError(f"Target for card enhance not found: {t}")
                    actual_targets.append(at)
                else:
                    at = find_card_in_zones(state, t.unique_id, player)
                    if at is None:
                        raise shcg_core_error.CardNotFoundError(f"Target for card enhance not found: {t}")
                    actual_targets.append(at)

        # Resolve multi targets
        actual_multi_targets = None
        if multi_targets_template is not None:
            actual_multi_targets = []
            for t in multi_targets_template:
                if t.is_generated:
                    at = find_card_in_zones_by_void_id(state, t.void_id, player)
                else:
                    at = find_card_in_zones(state, t.unique_id, player)
                if at is None:
                    raise shcg_core_error.CardNotFoundError(f"Multi-target for card enhance not found: {t}")
                actual_multi_targets.append(at)

        state.on_card_enhanced(player, actual_follower, actual_targets, is_ai_player, ui_set_text, ui_draw,
                                effect_choice=effect_choice,
                                additional_multi_targets=actual_multi_targets)
        return [('enhance', actual_follower)]

    elif action_type == 'draw':
        state.draw_card_with_foxtail(player, ui_draw, ui_set_text)
        return [('draw',)]
    else:
        return []


class BruteForceAIPlayer:
    def __init__(self, player_number: int, cuets_player_turn: int, cuets_opp_turn: int, unique_states_max_player_turn: int, unique_states_max_opp_turn: int):
        self.player_number = player_number
        self.brute_force_ai = BruteForceAI(player_number, cuets_player_turn, cuets_opp_turn, unique_states_max_player_turn, unique_states_max_opp_turn)
        self.pending_actions: List[Tuple] = []
        self.action_index = 0

    def clear_pending_actions(self):
        """Clear any pending actions."""
        self.pending_actions = []
        self.action_index = 0

    def take_turn(self, game_state: SHCGGameState, ui_draw: bool, ui_set_text: bool,
                  text_box=None) -> list:
        """
        Execute one action of the AI's turn.
        Returns a list with the action taken, or empty list if turn should end.
        """
        player = self.player_number

        # If we don't have pending actions, calculate them
        if not self.pending_actions or self.action_index >= len(self.pending_actions):
            self.pending_actions = self.brute_force_ai.get_best_turn_actions(game_state)
            self.action_index = 0
            if text_box and ui_set_text:
                text_box.append_html_text(f"AI Player {player} calculated {len(self.pending_actions)} actions and evaluated {self.brute_force_ai.endturnstate_evaluated} unique end-turn states.\n")
                text_box.append_html_text(f"Additional {self.brute_force_ai.endturnstate_evaluated_additional} unique end-turn states were evaluated for simulating opponent turn.\n")
                text_box.append_html_text(f"Avoided {self.brute_force_ai.loss_endturnstate_avoided} losing unique end-turn states.\n")

        if self.action_index >= len(self.pending_actions):
            self.pending_actions = []
            self.action_index = 0
            return []

        action = self.pending_actions[self.action_index]
        self.action_index += 1

        return apply_action(game_state, player, action, ui_draw, ui_set_text, True)
    

class BruteForceAIManager:
    """Manages Brute Force AI players for the game."""

    def __init__(self, cuets_player_turn: int, cuets_opp_turn: int, unique_states_max_player_turn: int, unique_states_max_opp_turn: int):
        self.ai_players: dict[int, BruteForceAIPlayer | None] = {1: None, 2: None}
        self.ai_enabled: dict[int, bool] = {1: False, 2: False}
        self.ai_action_delay: int = DEFAULT_AI_ACTION_DELAY_MS
        self.last_ai_action_time: int = 0
        self.cuets_player_turn = cuets_player_turn
        self.cuets_opp_turn = cuets_opp_turn
        self.unique_states_max_player_turn = unique_states_max_player_turn
        self.unique_states_max_opp_turn = unique_states_max_opp_turn

    def ai_clear_pending_actions(self):
        """Clear pending actions for a specific AI player."""
        for ai_player in self.ai_players.values():
            if ai_player is not None:
                ai_player.clear_pending_actions()

    def set_new_cuets(self, cuets_player_turn: int, cuets_opp_turn: int):
        """Set new CUETS values for all AI players."""
        self.cuets_player_turn = cuets_player_turn
        self.cuets_opp_turn = cuets_opp_turn
        for player, ai_player in self.ai_players.items():
            if ai_player is not None:
                ai_player.minimax_ai.continuous_unique_endturnstates_req_player_turn = cuets_player_turn
                ai_player.minimax_ai.continuous_unique_endturnstates_req_opp_turn = cuets_opp_turn

    def set_new_unique_states_max(self, unique_states_max_player_turn: int, unique_states_max_opp_turn: int):
        """Set new unique states max values for all AI players."""
        self.unique_states_max_player_turn = unique_states_max_player_turn
        self.unique_states_max_opp_turn = unique_states_max_opp_turn
        for player, ai_player in self.ai_players.items():
            if ai_player is not None:
                ai_player.minimax_ai.unique_states_max_player_turn = unique_states_max_player_turn
                ai_player.minimax_ai.unique_states_max_opp_turn = unique_states_max_opp_turn

    def enable_ai(self, player: int, enabled: bool = True):
        """Enable or disable AI for a player."""
        self.ai_enabled[player] = enabled
        if enabled and self.ai_players[player] is None:
            self.ai_players[player] = BruteForceAIPlayer(player, self.cuets_player_turn, self.cuets_opp_turn, 
                                                      self.unique_states_max_player_turn, self.unique_states_max_opp_turn)
        elif not enabled:
            self.ai_players[player] = None

    def is_ai_turn(self, game_state: 'SHCGGameState') -> bool:
        """Check if current player is controlled by AI."""
        return self.ai_enabled.get(game_state.current_player, False)

    def get_current_ai(self, game_state: 'SHCGGameState') -> BruteForceAIPlayer | None:
        """Get the AI player for the current turn."""
        if self.is_ai_turn(game_state):
            return self.ai_players[game_state.current_player]
        return None
