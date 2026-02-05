"""
Chess-like AI Player for Super Hard Card Game.
Uses minimax with alpha-beta pruning to calculate optimal moves.
Since all information is open (hands, decks, fields), this is a perfect information game.
"""
import itertools
import cards
from typing import TYPE_CHECKING, List, Tuple, Any, Optional
if TYPE_CHECKING:
    from super_hard_card_game import SHCGGameState

# Game constants
MAX_FIELD_SIZE = 5
MAX_HAND_SIZE = 9
MAX_FOXTAIL = 9
DEFAULT_HP_F = 20
DEFAULT_HP_S = 24
DEFAULT_MAX_ENHANCE_PER_TURN = 1

# AI constants
MAX_ACTION_SEQUENCES = 99999
MAX_ACTIONS_PER_TURN = 100
DEFAULT_AI_ACTION_DELAY_MS = 600


class AIError(Exception):
    """Base exception for AI-related errors."""
    pass


class CardNotFoundError(AIError):
    """Raised when a card cannot be found in the expected location."""
    pass


def _find_card_by_id(card_list: List[cards.Card], unique_id) -> Optional[cards.Card]:
    """Find a card in a list by its unique_id."""
    for card in card_list:
        if card.unique_id == unique_id:
            return card
    return None


def _find_card_in_zones(state, unique_id, player: int) -> Optional[cards.Card]:
    """Find a card by unique_id across all zones (fields and hands) for both players.
    Works with both GameStateSnapshot and SHCGGameState since they share the same structure.
    """
    all_cards = (
        state.fields[player] + state.fields[3 - player] +
        state.hands[player] + state.hands[3 - player]
    )
    return _find_card_by_id(all_cards, unique_id)


def _find_card_by_void_id(card_list: List[cards.Card], void_id) -> Optional[cards.Card]:
    for card in card_list:
        if card.void_id == void_id:
            return card
    return None


def _find_card_in_zones_by_void_id(state, void_id, player: int) -> Optional[cards.Card]:
    all_cards = (
        state.fields[player] + state.fields[3 - player] +
        state.hands[player] + state.hands[3 - player]
    )
    return _find_card_by_void_id(all_cards, void_id)



class GameStateSnapshot:
    """
    A lightweight, copyable snapshot of game state for simulation.
    Does not include any UI elements.
    """
    def __init__(self):
        # WARNING: Make sure to also modify from_game_state and copy methods when adding new attributes
        # Also _state_hash
        self.current_player: int = 2
        self.turn: int = 1
        self.concluded: bool = False
        self.winner: Optional[int] = None
        self.decks: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.hands: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.fields: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.hp: dict[int, int] = {1: DEFAULT_HP_S, 2: DEFAULT_HP_F}
        self.max_hp: dict[int, int] = {1: DEFAULT_HP_S, 2: DEFAULT_HP_F}
        self.foxtail: dict[int, int] = {1: MAX_FOXTAIL, 2: MAX_FOXTAIL}
        self.enhance_used_this_turn: dict[int, int] = {1: 0, 2: 0}
        self.max_enhance_allowed_per_turn: dict[int, int] = {1: DEFAULT_MAX_ENHANCE_PER_TURN, 2: DEFAULT_MAX_ENHANCE_PER_TURN}
        self.amount_card_generated_from_void: dict[int, int] = {1: 0, 2: 0} 

    @property
    def opponent(self) -> int:
        return 3 - self.current_player

    @staticmethod
    def from_game_state(game_state: 'SHCGGameState') -> 'GameStateSnapshot':
        """Create a snapshot from the actual game state."""
        snap = GameStateSnapshot()
        snap.current_player = game_state.current_player
        snap.turn = game_state.turn
        snap.concluded = game_state.concluded
        snap.hp = {1: game_state.hp[1], 2: game_state.hp[2]}
        snap.max_hp = {1: game_state.max_hp[1], 2: game_state.max_hp[2]}
        snap.foxtail = {1: game_state.foxtail[1], 2: game_state.foxtail[2]}
        snap.enhance_used_this_turn = {
            1: game_state.enhance_used_this_turn[1],
            2: game_state.enhance_used_this_turn[2]
        }
        snap.max_enhance_allowed_per_turn = {
            1: game_state.max_enhance_allowed_per_turn[1],
            2: game_state.max_enhance_allowed_per_turn[2]
        }
        snap.amount_card_generated_from_void = {
            1: game_state.amount_card_generated_from_void[1],
            2: game_state.amount_card_generated_from_void[2]
        }

        # Deep copy cards
        for player in [1, 2]:
            snap.decks[player] = [_copy_card(c) for c in game_state.decks[player]]
            snap.hands[player] = [_copy_card(c) for c in game_state.hands[player]]
            snap.fields[player] = [_copy_card(c) for c in game_state.fields[player]]

        return snap

    def copy(self) -> 'GameStateSnapshot':
        """Create a deep copy of this snapshot."""
        new_snap = GameStateSnapshot()
        new_snap.current_player = self.current_player
        new_snap.turn = self.turn
        new_snap.concluded = self.concluded
        new_snap.winner = self.winner
        new_snap.hp = {1: self.hp[1], 2: self.hp[2]}
        new_snap.max_hp = {1: self.max_hp[1], 2: self.max_hp[2]}
        new_snap.foxtail = {1: self.foxtail[1], 2: self.foxtail[2]}
        new_snap.enhance_used_this_turn = {
            1: self.enhance_used_this_turn[1],
            2: self.enhance_used_this_turn[2]
        }
        new_snap.max_enhance_allowed_per_turn = {
            1: self.max_enhance_allowed_per_turn[1],
            2: self.max_enhance_allowed_per_turn[2]
        }
        new_snap.amount_card_generated_from_void = {
            1: self.amount_card_generated_from_void[1],
            2: self.amount_card_generated_from_void[2]
        }

        for player in [1, 2]:
            new_snap.decks[player] = [_copy_card(c) for c in self.decks[player]]
            new_snap.hands[player] = [_copy_card(c) for c in self.hands[player]]
            new_snap.fields[player] = [_copy_card(c) for c in self.fields[player]]

        return new_snap

    def player_take_damage(self, player: int, amount: int, *args, **_kwargs) -> bool:
        """Apply damage to a player. Returns True if player is defeated."""
        assert amount >= 0
        self.hp[player] -= amount
        if self.hp[player] <= 0:
            self.winner = 3 - player
            self.concluded = True
            return True
        return False

    def player_heal(self, player: int, amount: int, *args, **_kwargs):
        """Heal a player, but not beyond max HP."""
        assert amount >= 0
        self.hp[player] = min(self.hp[player] + amount, self.max_hp[player])



def _copy_card(card: cards.Card) -> cards.Card:
    """Create a deep copy of a card."""
    # Create new instance of the same class without running __init__
    new_card = card.__class__.__new__(card.__class__)

    # Common attributes copied for all card types
    common_attrs = [
        'name', 'cost', 'original_cost', 'type', 'unique_id', 'is_generated',
        'void_id', 'description', 'effect_description', 'request_card_selection_on_play', 'request_effect_choose_option',
    ]
    for attr in common_attrs:
        if hasattr(card, attr):
            setattr(new_card, attr, getattr(card, attr))
        else:
            raise AIError(f"Card {card} missing expected attribute {attr} during copy.")

    # Follower-specific attributes
    if isinstance(card, cards.Follower):
        follower_attrs = [
            'description_e', 'attack', 'hp', 'max_hp', 'can_enhance', 'is_enhanced',
            'summoned_this_turn', 'enhanced_this_turn', 'request_card_selection_on_enhance',
            'attack_ability', 'how_many_attacks_max_of_turn', 'how_many_attacks_done_of_turn',
            'can_attack_this_turn', 'ability_rush', 'ability_super_rush', 'ability_protect', 'ability_drain'
        ]
        for attr in follower_attrs:
            if hasattr(card, attr):
                setattr(new_card, attr, getattr(card, attr))
            else:
                raise AIError(f"Follower {card} missing expected attribute {attr} during copy.")

    return new_card


class GameSimulator:
    """
    Simulates game actions on a GameStateSnapshot without UI.
    """

    @staticmethod
    def play_card(state: GameStateSnapshot, player: int, card: cards.Card,
                  target: Optional[cards.Card] = None, effect_choice: str | None = None) -> bool:
        """Play a card from hand. Returns True if successful."""
        if len(state.fields[player]) >= MAX_FIELD_SIZE and card.type != 'spell':
            return False
        if state.foxtail[player] < card.cost:
            return False
        if card not in state.hands[player]:
            return False

        state.foxtail[player] -= card.cost
        state.hands[player].remove(card)

        card.on_play_effect(state, False, False, None, target, effect_choice)

        if isinstance(card, cards.Follower):
            state.fields[player].append(card)
            card.on_summon_effect()
        elif isinstance(card, cards.Amulet):
            state.fields[player].append(card)
        elif isinstance(card, cards.Spell):
            pass

        return True

    @staticmethod
    def follower_attack(state: GameStateSnapshot, player: int,
                        attacker: cards.Follower, target) -> bool:
        """Execute an attack. Target can be a Follower or "leader". Returns True if successful."""
        if attacker.attack_ability <= 0 or not attacker.can_attack_this_turn:
            return False
        if attacker not in state.fields[player]:
            return False

        opponent = 3 - player

        if isinstance(target, cards.Follower):
            if target not in state.fields[opponent]:
                return False

            # Combat
            target_hp_before = target.hp
            target.hp -= attacker.attack
            target_hp_changed = target_hp_before - target.hp
            # drain ability
            if attacker.ability_drain and target_hp_changed > 0:
                state.player_heal(player, target_hp_changed)
            attacker.hp -= target.attack

            # Remove dead followers
            if target.hp <= 0:
                state.fields[opponent].remove(target)
            if attacker.hp <= 0:
                state.fields[player].remove(attacker)
            else:
                attacker.after_attack_effect()

        elif target == "leader":
            if attacker.attack_ability < 2:
                return False
            state.player_take_damage(opponent, attacker.attack, ui_draw=False, ui_set_text=False)
            # drain ability
            if attacker.ability_drain and attacker.attack > 0:
                state.player_heal(player, attacker.attack)
            attacker.after_attack_effect()

        return True

    @staticmethod
    def enhance_follower(state: GameStateSnapshot, player: int,
                         follower: cards.Follower, extra_target: Optional[cards.Card] = None) -> bool:
        """Enhance a follower. Returns True if successful."""
        if state.enhance_used_this_turn[player] >= state.max_enhance_allowed_per_turn[player]:
            return False
        if state.foxtail[player] < 1:
            return False
        if not hasattr(follower, 'can_enhance') or not follower.can_enhance:
            return False
        if follower not in state.fields[player]:
            return False

        state.foxtail[player] -= 1
        state.enhance_used_this_turn[player] += 1

        if follower.request_card_selection_on_enhance:
            follower.on_enhance_effect(state, False, False, None, selected_card_for_effect=extra_target)
        else:
            follower.on_enhance_effect(state, False, False, None, None)

        return True

    @staticmethod
    def draw_card(state: GameStateSnapshot, player: int) -> bool:
        """Draw a card using foxtail. Returns True if successful."""
        if not state.decks[player] or len(state.hands[player]) >= MAX_HAND_SIZE:
            return False
        if state.foxtail[player] < 1:
            return False

        state.foxtail[player] -= 1
        drawn_card = state.decks[player].pop()
        state.hands[player].append(drawn_card)
        return True

    @staticmethod
    def end_turn(state: GameStateSnapshot):
        """End the current turn and start the opponent's turn."""
        for c in state.fields[state.current_player].copy():
            c.end_of_turn_on_field_effect(state, False, False, None)

        state.current_player = state.opponent
        state.foxtail[state.current_player] = MAX_FOXTAIL

        # Apply start of turn effects to current player's followers
        for card in state.fields[state.current_player]:
            card.start_of_turn_on_field_effect(state.current_player)

        state.enhance_used_this_turn = {1: 0, 2: 0}
        state.turn += 1
        
        # Check for draw (both decks empty)
        if not state.decks[1] and not state.decks[2]:
            state.concluded = True
            state.winner = None


class MoveGenerator:
    """
    Generates all possible moves/actions from a game state.
    """

    @staticmethod
    def get_playable_cards(state: GameStateSnapshot, player: int) -> List[Tuple[cards.Card, cards.Follower | None, str | None]]:
        """
        Get all playable cards with their targets and effect choice, if any.
        WARNING: Can only target followers on the field for now.
        """
        playable = []
        hand = state.hands[player]
        foxtail = state.foxtail[player]
        field_count = len(state.fields[player])

        for card in hand:
            if card.cost > foxtail:
                continue
            if card.type != 'spell' and field_count >= MAX_FIELD_SIZE:
                continue
            # object in tuple
            o0 = card
            o1_possible_values = [None]
            o2_possible_values = [None]

            # Handle targeting cards
            # if select, no option to not select as part of game mechanics
            if card.request_card_selection_on_play == "field":
                targets = [f for f in state.fields[player] if isinstance(f, cards.Follower)]
                if targets:
                    o1_possible_values = targets

            elif card.request_card_selection_on_play == "field_opponent":
                targets = [f for f in state.fields[3 - player] if isinstance(f, cards.Follower)]
                if targets:
                    o1_possible_values = targets

            elif card.request_card_selection_on_play == "field_both":
                targets = [f for f in state.fields[player] + state.fields[3 - player] if isinstance(f, cards.Follower)]
                if targets:
                    o1_possible_values = targets
            
            # Handle effect choice options
            if card.request_effect_choose_option:
                o2_possible_values = card.request_effect_choose_option

            # Combine possible targets and effect choices
            for target, effect_choice in itertools.product(o1_possible_values, o2_possible_values):
                playable.append((o0, target, effect_choice))

        return playable

    @staticmethod
    def get_possible_attacks(state: GameStateSnapshot, player: int) -> List[Tuple[cards.Follower, cards.Follower | str]]:
        """
        Get all possible attacks.
        Returns list of (attacker, target) tuples. Target is Follower or "leader".
        """
        attacks = []
        opponent = 3 - player

        # check if opponent has any followers with ability_protect
        # if so, only those followers can be attacked
        protect_exists = any([c.ability_protect for c in state.fields[opponent]])
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
    def get_enhanceable_followers(state: GameStateSnapshot, player: int) -> List[Tuple[cards.Follower, cards.Follower | None]]:
        """Get all followers that can be enhanced."""
        if state.enhance_used_this_turn[player] >= state.max_enhance_allowed_per_turn[player]:
            return []
        if state.foxtail[player] < 1:
            return []

        enhanceable = []
        for follower in state.fields[player]:
            if follower.type == 'follower' and hasattr(follower, 'can_enhance') and follower.can_enhance:
                if follower.request_card_selection_on_enhance == "field_opponent":
                    targets = [f for f in state.fields[3 - player] if f.type == 'follower']
                    if targets:
                        for target in targets:
                            enhanceable.append((follower, target))
                    else:
                        enhanceable.append((follower, None))
                elif follower.request_card_selection_on_enhance == "field":
                    targets = [f for f in state.fields[player] if f.type == 'follower']
                    if targets:
                        for target in targets:
                            enhanceable.append((follower, target))
                    else:
                        enhanceable.append((follower, None))
                elif follower.request_card_selection_on_enhance == "field_both":
                    targets = [f for f in state.fields[player] + state.fields[3 - player] if f.type == 'follower']
                    if targets:
                        for target in targets:
                            enhanceable.append((follower, target))
                    else:
                        enhanceable.append((follower, None))
                else:
                    enhanceable.append((follower, None))
        return enhanceable

    @staticmethod
    def can_draw_card(state: GameStateSnapshot, player: int) -> bool:
        """Check if the player can draw a card."""
        return (state.foxtail[player] >= 1 and
                len(state.hands[player]) < MAX_HAND_SIZE and
                len(state.decks[player]) > 0)


class Evaluator:
    """
    Evaluates game states from a player's perspective.
    """

    # Weight constants for evaluation
    HP_WEIGHT = 2.0
    FIELD_POWER_WEIGHT = 1.0
    HAND_SIZE_WEIGHT = 2.0 # Could be 4.0, but should prefer board presence more
    DECK_SIZE_WEIGHT = 0.1

    @staticmethod
    def evaluate(state: GameStateSnapshot, player: int, only_care_about_winorlose: bool) -> float:
        """
        Evaluate the game state from player's perspective.
        Returns infinity for wins, -infinity for losses.
        2026/02/05 Removed basic_lethal_check parameter, add only_care_about_winorlose.
        Written and Verified by Rokafox on 2026/02/05
        """
        # NOTE: this method is called after the player's turn ends
        opponent = 3 - player

        # Check for game end
        if state.concluded:
            if state.winner == player:
                return float('inf')
            elif state.winner == opponent:
                return float('-inf')
            else:
                return 0.0  # 
            
        # Useful when simulating the last turn, for either of the players
        # for example at depth 1, care about score on your turn, but not on opponent turn (last turn)
        # for performance reasons, depth > 1 is not considered.
        if only_care_about_winorlose:
            return 0.0

        score = 100.0 # Base score

        own_hp_value = state.hp[player]
        opp_hp_value = state.hp[opponent]
        score += (own_hp_value - opp_hp_value) * Evaluator.HP_WEIGHT

        # Field power (total attack + hp of followers)
        own_field_power = 0
        for f in state.fields[player]:
            if isinstance(f, cards.Follower):
                own_field_power += f.attack + f.hp
                # 守護 (.ability_protect) 者のHPの100%を追加ボーナスとして加算
                if f.ability_protect:
                    own_field_power += f.hp
                # drain 者の攻撃力の100%を追加ボーナスとして加算
                if f.ability_drain:
                    own_field_power += f.attack
        opp_field_power = 0
        for f in state.fields[opponent]:
            if isinstance(f, cards.Follower):
                opp_field_power += f.attack + f.hp
                if f.ability_protect:
                    opp_field_power += f.hp
                if f.ability_drain:
                    opp_field_power += f.attack
        score += (own_field_power - opp_field_power) * Evaluator.FIELD_POWER_WEIGHT
        # Hand size
        score += (len(state.hands[player]) - len(state.hands[opponent])) * Evaluator.HAND_SIZE_WEIGHT
        # Deck size
        score += (len(state.decks[player]) - len(state.decks[opponent])) * Evaluator.DECK_SIZE_WEIGHT

        return score


class MinimaxAI:
    """
    Not minimax at all.
    """
    def __init__(self, player_number: int):
        self.player_number = player_number
        self.endturnstate_evaluated = 0
        self.endturnstate_evaluated_additional = 0
        self.loss_endturnstate_avoided = 0
        self.best_actions: List[Tuple[str, Any]] = []

    def get_best_turn_actions(self, game_state: 'SHCGGameState') -> List[Tuple]:
        """
        Calculate and return the best sequence of actions for this turn.
        Written and Verified by Rokafox on 2026/02/05
        """
        self.endturnstate_evaluated = 0
        self.endturnstate_evaluated_additional = 0
        self.loss_endturnstate_avoided = 0
        state = GameStateSnapshot.from_game_state(game_state)

        # Find all possible turn action sequences and evaluate them
        best_score = float('-inf')
        best_actions = []

        # Generate and evaluate possible action sequences
        all_sequences = self._generate_random_turn_sequences(state, self.player_number, min_continuous_visited_state_req=6)

        for actions in all_sequences:
            # Apply actions to a copy of the state
            test_state = state.copy()
            for action in actions:
                if not self._apply_action(test_state, self.player_number, action):
                    raise AIError("Invalid action sequence generated.")

            GameSimulator.end_turn(test_state)
            score = Evaluator.evaluate(test_state, self.player_number, only_care_about_winorlose=False) # Basic evaluation

            # Advanced evaluation: simulate opponent's turn
            # If opponent scores inf for any seq, its a loss for us and set score to -inf.
            # This part can be skipped if the player is already winning (score == inf)
            # or losing (score == -inf) as checked in True basic_lethal_check or draw (score == 0.0)
            if not score == float('inf') and not score == float('-inf') and not score == 0.0:
                opponent_sequences = self._generate_random_turn_sequences(test_state, 3 - self.player_number, min_continuous_visited_state_req=3)
                for single_opp_seq in opponent_sequences:
                    opp_test_state = test_state.copy()
                    for opp_action in single_opp_seq:
                        if not self._apply_action(opp_test_state, test_state.current_player, opp_action):
                            raise AIError("Invalid opponent action sequence generated.")

                    # End opponent's turn
                    GameSimulator.end_turn(opp_test_state)
                    # No basic lethal check. Only matters if opponent can score infinity here
                    opp_score = Evaluator.evaluate(opp_test_state, 3 - self.player_number, only_care_about_winorlose=True)
                    self.endturnstate_evaluated_additional += 1

                    if opp_score == float('inf'):
                        # Opponent can win, so this is a loss for us
                        score = float('-inf')
                        self.loss_endturnstate_avoided += 1
                        break
                    else:
                        pass
            else:
                pass
                # print("Advanced evaluation skipped due to definitive score.")

            self.endturnstate_evaluated += 1

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


    def _state_hash(self, state: GameStateSnapshot) -> str:
        """
        Create a hash of the game state for deduplication.
        Written and Verified by Rokafox on 2026/02/04
        """
        parts = [
            str(state.hp[1]), str(state.hp[2]),
            str(state.max_hp[1]), str(state.max_hp[2]),
            str(state.foxtail[1]), str(state.foxtail[2]),
            str(state.enhance_used_this_turn[1]), str(state.enhance_used_this_turn[2]),
            str(state.max_enhance_allowed_per_turn[1]), str(state.max_enhance_allowed_per_turn[2]),
            str(state.amount_card_generated_from_void[1]), str(state.amount_card_generated_from_void[2]),
        ]

        # Hash field states
        for player in [1, 2]:
            # follower cards
            field_str_follower = []
            for f in state.fields[player]:
                if f.type == 'follower':
                    field_str_follower.append(
                        f"{f.name}:{f.attack}:{f.max_hp}:{f.hp}:{f.can_attack_this_turn}:"
                        f"{f.attack_ability}:{f.can_enhance}:{f.is_enhanced}:"
                        f"{f.how_many_attacks_max_of_turn}:{f.how_many_attacks_done_of_turn}:"
                        f"{f.ability_rush}:{f.ability_super_rush}:"
                        f"{f.ability_protect}:{f.ability_drain}"
                    )
            field_str_follower = ",".join(field_str_follower)
            # amulet cards
            field_str_amulet = ",".join(f"{f.name}" for f in state.fields[player] if f.type == 'amulet')
            # combine
            parts.append(f"F{player}:" + field_str_follower)
            parts.append(f"A{player}:" + field_str_amulet)

        # hand states, name and cost
        for player in [1, 2]:
            hand_str = ",".join(f"{c.name}:{c.cost}" for c in state.hands[player])
            parts.append(f"H{player}:" + hand_str)

        # deck states, name and cost
        for player in [1, 2]:
            deck_str = ",".join(f"{c.name}:{c.cost}" for c in state.decks[player])
            parts.append(f"D{player}:" + deck_str)

        return "|".join(parts)

    def _generate_random_turn_sequences(self, state: GameStateSnapshot, player: int,
                                        min_continuous_visited_state_req: int,
                                        ) -> List[List[Tuple]]:
        """
        Generate random reasonable action sequences for a turn.
        min_continuous_visited_state_req: Stop If the end result same state is visited this many times continuously.
        This value should be high enough to allow many more thorough explorations.
        Only terminal sequences are accepted (foxtail=0 or no more actions possible)
        Written and Verified by Rokafox on 2026/02/04
        """
        import random
        bundle_of_all_action_sequences = []
        visited_states = set()
        continuous_visited_state_count = 0
        current_state = state.copy() # the original environment
        single_action_seq = []

        while continuous_visited_state_count < min_continuous_visited_state_req: # requirement
            # do: generate single action sequences until requirement is met
            next_possible_actions: list[tuple] = self._get_all_actions(current_state, player)

            if not next_possible_actions or current_state.foxtail[player] == 0: # if terminal state
                # hash, compare, if in visited_states, increase continuous_visited_state_count
                # else reset continuous_visited_state_count
                state_hash = self._state_hash(current_state)
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
                current_state = state.copy()
                single_action_seq = []
                continue
            else: # should continue
                pass 

            action = random.choice(next_possible_actions)
            if self._apply_action(current_state, player, action): # apply action
                single_action_seq.append(action)
            else: # action not valid? Make no sense
                raise AIError("Invalid action sequence generated.")

        return bundle_of_all_action_sequences

    def _get_all_actions(self, state: GameStateSnapshot, player: int) -> List[Tuple]:
        """
        Get all possible actions from current state.
        Other than draw, action[1] is the card/follower template (with unique_id).
        """
        actions = []

        # Play cards
        for card, target, effect_choice in MoveGenerator.get_playable_cards(state, player):
            actions.append(('play', card, target, effect_choice))

        # Attacks
        for attacker, target in MoveGenerator.get_possible_attacks(state, player):
            actions.append(('attack', attacker, target))

        # Enhance
        for follower, target in MoveGenerator.get_enhanceable_followers(state, player):
            actions.append(('enhance', follower, target))

        # Draw
        if MoveGenerator.can_draw_card(state, player):
            actions.append(('draw',))

        return actions

    def _apply_action(self, state: GameStateSnapshot, player: int, action: Tuple) -> bool:
        """Apply an action to the state. Returns True if successful."""
        action_type = action[0]

        if action_type == 'play':
            card, target, effect_choice = action[1], action[2], action[3]
            if card.is_generated:
                actual_card = _find_card_by_void_id(state.hands[player], card.void_id)
            else:
                actual_card = _find_card_by_id(state.hands[player], card.unique_id)
            if actual_card is None:
                raise CardNotFoundError(f"Card to play not found in hand: {card} with void_id {card.void_id} and unique_id {card.unique_id}") 

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
            follower, extra_target = action[1], action[2]
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
                    raise CardNotFoundError(f"Extra target for card enhance not found: {extra_target}")

            return GameSimulator.enhance_follower(state, player, actual_follower, actual_target)

        elif action_type == 'draw':
            return GameSimulator.draw_card(state, player)

        return False


class MinimaxAIPlayer:
    """
    Wrapper class that provides the same interface as the original AIPlayer
    but uses minimax for decision making.
    """

    def __init__(self, player_number: int, depth: int = 1):
        self.player_number = player_number
        self.minimax_ai = MinimaxAI(player_number)
        self.pending_actions: List[Tuple] = []
        self.action_index = 0

    def clear_pending_actions(self):
        """Clear any pending actions."""
        self.pending_actions = []
        self.action_index = 0

    def take_turn(self, game_state: 'SHCGGameState', ui_draw: bool, ui_set_text: bool,
                  text_box=None) -> list:
        """
        Execute one action of the AI's turn.
        Returns a list with the action taken, or empty list if turn should end.
        """
        player = self.player_number

        # If we don't have pending actions, calculate them
        if not self.pending_actions or self.action_index >= len(self.pending_actions):
            self.pending_actions = self.minimax_ai.get_best_turn_actions(game_state)
            self.action_index = 0
            if text_box and ui_set_text:
                text_box.append_html_text(f"AI Player {player} calculated {len(self.pending_actions)} actions and evaluated {self.minimax_ai.endturnstate_evaluated} unique end-turn states.\n")
                text_box.append_html_text(f"Additional {self.minimax_ai.endturnstate_evaluated_additional} unique end-turn states were evaluated for simulating opponent turn.\n")
                text_box.append_html_text(f"Avoided {self.minimax_ai.loss_endturnstate_avoided} losing unique end-turn states.\n")

        if self.action_index >= len(self.pending_actions):
            self.pending_actions = []
            self.action_index = 0
            return []

        action = self.pending_actions[self.action_index]
        self.action_index += 1

        action_type = action[0]

        if action_type == 'end_turn':
            self.pending_actions = []
            self.action_index = 0
            return []

        elif action_type == 'play':
            card_template, target_template, effect_choice = action[1], action[2], action[3]

            if card_template.is_generated:
                actual_card = _find_card_by_void_id(game_state.hands[player], card_template.void_id)
            else:
                actual_card = _find_card_by_id(game_state.hands[player], card_template.unique_id)
            if actual_card is None:
                raise CardNotFoundError("Card to play not found in hand")

            actual_target = None
            if target_template is not None:
                if target_template.is_generated:
                    actual_target = _find_card_in_zones_by_void_id(game_state, target_template.void_id, player)
                else:
                    actual_target = _find_card_in_zones(game_state, target_template.unique_id, player)
                if actual_target is None:
                    raise CardNotFoundError("Target for card play not found")

            game_state.play_card(player, actual_card, ui_draw, ui_set_text, additional_target=actual_target, is_ai_player=True,
                                 effect_choice=effect_choice)
            return [('play', actual_card)]

        elif action_type == 'attack':
            attacker_template, target_template = action[1], action[2]

            if attacker_template.is_generated:
                actual_attacker = next(
                    (f for f in game_state.fields[player]
                     if f.void_id == attacker_template.void_id),
                    None
                )
            else:
                actual_attacker = next(
                    (f for f in game_state.fields[player]
                    if f.type == 'follower' and f.unique_id == attacker_template.unique_id),
                    None
                )
            if actual_attacker is None:
                raise CardNotFoundError("Attacker not found on field")

            if target_template == "leader":
                actual_target = "leader"
            else:
                if target_template.is_generated:
                    actual_target = next(
                        (f for f in game_state.fields[3 - player]
                         if f.void_id == target_template.void_id),
                        None
                    )
                else:
                    actual_target = next(
                        (f for f in game_state.fields[3 - player]
                        if f.type == 'follower' and f.unique_id == target_template.unique_id),
                        None
                    )
                if actual_target is None:
                    raise CardNotFoundError("Attack target not found on field")

            game_state.follower_attack(player, actual_attacker, actual_target, ui_draw, ui_set_text)
            return [('attack', actual_attacker, actual_target)]

        elif action_type == 'enhance':
            follower_template, target_template = action[1], action[2]

            actual_follower = next(
                (f for f in game_state.fields[player]
                 if f.type == 'follower' and f.unique_id == follower_template.unique_id and f.can_enhance),
                None
            )
            if actual_follower is None:
                raise CardNotFoundError("Follower to enhance not found on field")

            actual_target = None
            if target_template is not None:
                actual_target = _find_card_in_zones(game_state, target_template.unique_id, player)
                if actual_target is None:
                    raise CardNotFoundError("Target for enhance not found")

            game_state.on_card_enhanced(player, actual_follower, actual_target, is_ai_player=True, ui_set_text=ui_set_text, ui_draw=ui_draw)

            return [('enhance', actual_follower)]

        elif action_type == 'draw':
            game_state.draw_card_with_foxtail(player, ui_draw, ui_set_text)
            return [('draw',)]

        return []


class MinimaxAIManager:
    """Manages Minimax AI players for the game."""

    def __init__(self, depth: int = 2):
        self.depth = depth
        self.ai_players: dict[int, MinimaxAIPlayer | None] = {1: None, 2: None}
        self.ai_enabled: dict[int, bool] = {1: False, 2: False}
        self.ai_action_delay: int = DEFAULT_AI_ACTION_DELAY_MS
        self.last_ai_action_time: int = 0

    def ai_clear_pending_actions(self):
        """Clear pending actions for a specific AI player."""
        for ai_player in self.ai_players.values():
            if ai_player is not None:
                ai_player.clear_pending_actions()

    def enable_ai(self, player: int, enabled: bool = True):
        """Enable or disable AI for a player."""
        self.ai_enabled[player] = enabled
        if enabled and self.ai_players[player] is None:
            self.ai_players[player] = MinimaxAIPlayer(player, depth=self.depth)
        elif not enabled:
            self.ai_players[player] = None

    def is_ai_turn(self, game_state: 'SHCGGameState') -> bool:
        """Check if current player is controlled by AI."""
        return self.ai_enabled.get(game_state.current_player, False)

    def get_current_ai(self, game_state: 'SHCGGameState') -> MinimaxAIPlayer | None:
        """Get the AI player for the current turn."""
        if self.is_ai_turn(game_state):
            return self.ai_players[game_state.current_player]
        return None
