"""
Chess-like AI Player for Super Hard Card Game.
Uses minimax with alpha-beta pruning to calculate optimal moves.
Since all information is open (hands, decks, fields), this is a perfect information game.
"""
import cards
import copy
from typing import TYPE_CHECKING, List, Tuple, Any, Optional
if TYPE_CHECKING:
    from super_hard_card_game import SHCGGameState


class GameStateSnapshot:
    """
    A lightweight, copyable snapshot of game state for simulation.
    Does not include any UI elements.
    """
    def __init__(self):
        self.current_player: int = 1
        self.turn: int = 1
        self.concluded: bool = False
        self.winner: Optional[int] = None
        self.decks: dict[int, list] = {1: [], 2: []}
        self.hands: dict[int, list] = {1: [], 2: []}
        self.fields: dict[int, list] = {1: [], 2: []}
        self.hp: dict[int, int] = {1: 20, 2: 20}
        self.foxtail: dict[int, int] = {1: 9, 2: 9}
        self.enhance_used_this_turn: dict[int, int] = {1: 0, 2: 0}
        self.max_enhance_allowed_per_turn: dict[int, int] = {1: 1, 2: 1}

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
        snap.foxtail = {1: game_state.foxtail[1], 2: game_state.foxtail[2]}
        snap.enhance_used_this_turn = {
            1: game_state.enhance_used_this_turn[1],
            2: game_state.enhance_used_this_turn[2]
        }
        snap.max_enhance_allowed_per_turn = {
            1: game_state.max_enhance_allowed_per_turn[1],
            2: game_state.max_enhance_allowed_per_turn[2]
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
        new_snap.foxtail = {1: self.foxtail[1], 2: self.foxtail[2]}
        new_snap.enhance_used_this_turn = {
            1: self.enhance_used_this_turn[1],
            2: self.enhance_used_this_turn[2]
        }
        new_snap.max_enhance_allowed_per_turn = {
            1: self.max_enhance_allowed_per_turn[1],
            2: self.max_enhance_allowed_per_turn[2]
        }

        for player in [1, 2]:
            new_snap.decks[player] = [_copy_card(c) for c in self.decks[player]]
            new_snap.hands[player] = [_copy_card(c) for c in self.hands[player]]
            new_snap.fields[player] = [_copy_card(c) for c in self.fields[player]]

        return new_snap


def _copy_card(card: cards.Card) -> cards.Card:
    """Create a deep copy of a card."""
    if isinstance(card, cards.Follower):
        # Create new instance of the same class
        new_card = card.__class__.__new__(card.__class__)
        new_card.name = card.name
        new_card.cost = card.cost
        new_card.type = card.type
        new_card.description = card.description
        new_card.effect_description = getattr(card, 'effect_description', '')
        new_card.request_card_selection_on_play = getattr(card, 'request_card_selection_on_play', '')
        new_card.request_card_selection_on_play_amount = getattr(card, 'request_card_selection_on_play_amount', 0)
        # Follower specific
        new_card.description_e = getattr(card, 'description_e', '')
        new_card.attack = card.attack
        new_card.hp = card.hp
        new_card.max_hp = card.max_hp
        new_card.can_enhance = card.can_enhance
        new_card.is_enhanced = card.is_enhanced
        new_card.summoned_this_turn = card.summoned_this_turn
        new_card.enhanced_this_turn = card.enhanced_this_turn
        new_card.attack_ability = card.attack_ability
        new_card.how_many_attacks_max_of_turn = card.how_many_attacks_max_of_turn
        new_card.how_many_attacks_done_of_turn = card.how_many_attacks_done_of_turn
        new_card.can_attack_this_turn = card.can_attack_this_turn
        return new_card
    else:
        # For spells and amulets, create a simple copy
        new_card = card.__class__.__new__(card.__class__)
        new_card.name = card.name
        new_card.cost = card.cost
        new_card.type = card.type
        new_card.description = getattr(card, 'description', '')
        new_card.effect_description = getattr(card, 'effect_description', '')
        new_card.request_card_selection_on_play = getattr(card, 'request_card_selection_on_play', '')
        new_card.request_card_selection_on_play_amount = getattr(card, 'request_card_selection_on_play_amount', 0)
        return new_card


class GameSimulator:
    """
    Simulates game actions on a GameStateSnapshot without UI.
    """

    @staticmethod
    def play_card(state: GameStateSnapshot, player: int, card: cards.Card,
                  target: Optional[cards.Card] = None) -> bool:
        """Play a card from hand. Returns True if successful."""
        if len(state.fields[player]) >= 5 and card.type != 'spell':
            return False
        if state.foxtail[player] < card.cost:
            return False
        if card not in state.hands[player]:
            return False

        state.foxtail[player] -= card.cost
        state.hands[player].remove(card)

        # Apply on-play effects
        if hasattr(card, 'request_card_selection_on_play') and card.request_card_selection_on_play == "field":
            if target is not None and hasattr(card, 'on_play_effect'):
                card.on_play_effect(player, target)

        if card.type == 'follower':
            state.fields[player].append(card)
        elif card.type == 'amulet':
            state.fields[player].append(card)
        # Spells don't go to field

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
            target.hp -= attacker.attack
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
            state.hp[opponent] -= attacker.attack
            if state.hp[opponent] <= 0:
                state.concluded = True
                state.winner = player

            attacker.after_attack_effect()

        return True

    @staticmethod
    def enhance_follower(state: GameStateSnapshot, player: int,
                         follower: cards.Follower) -> bool:
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

        # Apply enhance effect
        follower.on_enhance_effect(player)

        return True

    @staticmethod
    def draw_card(state: GameStateSnapshot, player: int) -> bool:
        """Draw a card using foxtail. Returns True if successful."""
        if not state.decks[player] or len(state.hands[player]) >= 9:
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
        state.current_player = state.opponent
        state.foxtail[state.current_player] = 9

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
    def get_playable_cards(state: GameStateSnapshot, player: int) -> List[Tuple[cards.Card, Optional[cards.Card]]]:
        """
        Get all playable cards with their targets.
        Returns list of (card, target) tuples. Target is None for non-targeting cards.
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

            # Handle targeting cards
            if hasattr(card, 'request_card_selection_on_play') and card.request_card_selection_on_play == "field":
                # Needs a target on field
                targets = [f for f in state.fields[player] if f.type == 'follower']
                if targets:
                    for target in targets:
                        playable.append((card, target))
                # If no targets, can't play
            else:
                playable.append((card, None))

        return playable

    @staticmethod
    def get_possible_attacks(state: GameStateSnapshot, player: int) -> List[Tuple[cards.Follower, Any]]:
        """
        Get all possible attacks.
        Returns list of (attacker, target) tuples. Target is Follower or "leader".
        """
        attacks = []
        opponent = 3 - player

        for follower in state.fields[player]:
            if follower.type != 'follower':
                continue
            if not follower.can_attack_this_turn or follower.attack_ability <= 0:
                continue

            # Can attack opponent followers
            for target in state.fields[opponent]:
                if target.type == 'follower':
                    attacks.append((follower, target))

            # Can attack leader if attack_ability >= 2
            if follower.attack_ability >= 2:
                attacks.append((follower, "leader"))

        return attacks

    @staticmethod
    def get_enhanceable_followers(state: GameStateSnapshot, player: int) -> List[cards.Follower]:
        """Get all followers that can be enhanced."""
        if state.enhance_used_this_turn[player] >= state.max_enhance_allowed_per_turn[player]:
            return []
        if state.foxtail[player] < 1:
            return []

        enhanceable = []
        for follower in state.fields[player]:
            if follower.type == 'follower' and hasattr(follower, 'can_enhance') and follower.can_enhance:
                enhanceable.append(follower)
        return enhanceable

    @staticmethod
    def can_draw_card(state: GameStateSnapshot, player: int) -> bool:
        """Check if the player can draw a card."""
        return (state.foxtail[player] >= 1 and
                len(state.hands[player]) < 9 and
                len(state.decks[player]) > 0)


class Evaluator:
    """
    Evaluates game states from a player's perspective.
    """

    # Weight constants for evaluation
    HP_WEIGHT = 2.0
    FIELD_POWER_WEIGHT = 1.0
    HAND_SIZE_WEIGHT = 1.0 # Every card in hand is worth 1 pt

    @staticmethod
    def evaluate(state: GameStateSnapshot, player: int) -> float:
        """
        Evaluate the game state from player's perspective.
        Positive = player is winning, Negative = opponent is winning.
        Returns infinity for wins, -infinity for losses.
        """
        opponent = 3 - player

        # Check for game end
        if state.concluded:
            if state.winner == player:
                return float('inf')
            elif state.winner == opponent:
                return float('-inf')
            else:
                return 0.0  # Draw

        score = 0.0

        own_hp_value = state.hp[player]
        opp_hp_value = state.hp[opponent]
        score += (own_hp_value - opp_hp_value) * Evaluator.HP_WEIGHT

        # Field power (total attack + hp of followers)
        own_field_power = sum(f.attack + f.hp for f in state.fields[player] if f.type == 'follower')
        opp_field_power = sum(f.attack + f.hp for f in state.fields[opponent] if f.type == 'follower')
        score += (own_field_power - opp_field_power) * Evaluator.FIELD_POWER_WEIGHT

        # Hand size
        score += len(state.hands[player])

        return score


class MinimaxAI:
    """
    Chess-like AI using minimax with alpha-beta pruning.
    Calculates optimal moves by looking ahead several turns.
    """

    def __init__(self, player_number: int, max_depth: int = 2):
        """
        Initialize the AI.

        Args:
            player_number: Which player this AI controls (1 or 2)
            max_depth: How many turns to look ahead (1 = end of opponent's next turn)
        """
        self.player_number = player_number
        self.max_depth = max_depth
        self.nodes_evaluated = 0
        self.best_actions: List[Tuple[str, Any]] = []

    def get_best_turn_actions(self, game_state: 'SHCGGameState') -> List[Tuple[str, Any]]:
        """
        Calculate and return the best sequence of actions for this turn.

        Returns a list of action tuples:
        - ('play', card, target)
        - ('attack', attacker, target)
        - ('enhance', follower)
        - ('draw',)
        - ('end_turn',)
        """
        self.nodes_evaluated = 0
        state = GameStateSnapshot.from_game_state(game_state)

        # Find all possible turn action sequences and evaluate them
        best_score = float('-inf')
        best_actions = []

        # Generate and evaluate all possible action sequences
        all_sequences = self._generate_turn_sequences(state, self.player_number, max_actions=10)

        for actions in all_sequences:
            # Apply actions to a copy of the state
            test_state = state.copy()
            valid = True
            for action in actions:
                if not self._apply_action(test_state, self.player_number, action):
                    valid = False
                    break

            if not valid:
                continue

            # End the turn
            GameSimulator.end_turn(test_state)

            # Evaluate using minimax for remaining depth
            if self.max_depth > 1:
                score = self._minimax(test_state, self.max_depth - 1, False,
                                      float('-inf'), float('inf'))
            else:
                score = Evaluator.evaluate(test_state, self.player_number)

            self.nodes_evaluated += 1

            if score > best_score:
                best_score = score
                best_actions = actions

        # Add end_turn action
        best_actions.append(('end_turn',))
        self.best_actions = best_actions

        return best_actions

    def _generate_turn_sequences(self, state: GameStateSnapshot, player: int,
                                  max_actions: int = 10) -> List[List[Tuple]]:
        """
        Generate all reasonable action sequences for a turn.
        Uses iterative deepening to find good sequences without exhaustive search.
        """
        sequences = [[]]  # Start with empty sequence (do nothing)

        # Use BFS to generate action sequences
        queue = [(state.copy(), [])]
        visited_states = set()

        while queue and len(sequences) < 500:  # Limit total sequences
            current_state, current_actions = queue.pop(0)

            if len(current_actions) >= max_actions:
                continue

            # Generate state hash for deduplication
            state_hash = self._state_hash(current_state)
            if state_hash in visited_states:
                continue
            visited_states.add(state_hash)

            # Try all possible next actions
            next_actions = self._get_all_actions(current_state, player)

            for action in next_actions:
                new_state = current_state.copy()
                if self._apply_action(new_state, player, action):
                    new_sequence = current_actions + [action]
                    sequences.append(new_sequence)

                    if not new_state.concluded:
                        queue.append((new_state, new_sequence))

        return sequences

    def _state_hash(self, state: GameStateSnapshot) -> str:
        """Create a hash of the game state for deduplication."""
        parts = [
            str(state.hp[1]), str(state.hp[2]),
            str(state.foxtail[1]), str(state.foxtail[2]),
            str(state.enhance_used_this_turn[1]), str(state.enhance_used_this_turn[2]),
            str(len(state.hands[1])), str(len(state.hands[2])),
        ]

        # Hash field states
        for player in [1, 2]:
            field_str = ",".join(f"{f.name}:{f.attack}:{f.hp}:{f.can_attack_this_turn}:{f.attack_ability}"
                                 for f in state.fields[player] if f.type == 'follower')
            parts.append(field_str)

        return "|".join(parts)

    def _get_all_actions(self, state: GameStateSnapshot, player: int) -> List[Tuple]:
        """Get all possible actions from current state."""
        actions = []

        # Play cards
        for card, target in MoveGenerator.get_playable_cards(state, player):
            actions.append(('play', card, target))

        # Attacks
        for attacker, target in MoveGenerator.get_possible_attacks(state, player):
            actions.append(('attack', attacker, target))

        # Enhance
        for follower in MoveGenerator.get_enhanceable_followers(state, player):
            actions.append(('enhance', follower))

        # Draw (limit to avoid spam)
        if MoveGenerator.can_draw_card(state, player):
            actions.append(('draw',))

        return actions

    def _apply_action(self, state: GameStateSnapshot, player: int, action: Tuple) -> bool:
        """Apply an action to the state. Returns True if successful."""
        action_type = action[0]

        if action_type == 'play':
            card, target = action[1], action[2]
            # Find the actual card in the state's hand
            actual_card = None
            for c in state.hands[player]:
                if c.name == card.name and c.cost == card.cost:
                    actual_card = c
                    break
            if actual_card is None:
                return False

            # Find actual target if needed
            actual_target = None
            if target is not None:
                for f in state.fields[player]:
                    if f.name == target.name and f.attack == target.attack and f.hp == target.hp:
                        actual_target = f
                        break

            return GameSimulator.play_card(state, player, actual_card, actual_target)

        elif action_type == 'attack':
            attacker, target = action[1], action[2]
            # Find actual attacker
            actual_attacker = None
            for f in state.fields[player]:
                if (f.name == attacker.name and f.attack == attacker.attack and
                    f.hp == attacker.hp and f.can_attack_this_turn):
                    actual_attacker = f
                    break
            if actual_attacker is None:
                return False

            # Find actual target
            if target == "leader":
                actual_target = "leader"
            else:
                actual_target = None
                opponent = 3 - player
                for f in state.fields[opponent]:
                    if f.name == target.name and f.attack == target.attack and f.hp == target.hp:
                        actual_target = f
                        break
                if actual_target is None:
                    return False

            return GameSimulator.follower_attack(state, player, actual_attacker, actual_target)

        elif action_type == 'enhance':
            follower = action[1]
            # Find actual follower
            actual_follower = None
            for f in state.fields[player]:
                if (f.name == follower.name and f.attack == follower.attack and
                    f.hp == follower.hp and hasattr(f, 'can_enhance') and f.can_enhance):
                    actual_follower = f
                    break
            if actual_follower is None:
                return False

            return GameSimulator.enhance_follower(state, player, actual_follower)

        elif action_type == 'draw':
            return GameSimulator.draw_card(state, player)

        return False

    def _minimax(self, state: GameStateSnapshot, depth: int, is_maximizing: bool,
                 alpha: float, beta: float) -> float:
        """
        Minimax with alpha-beta pruning.

        Args:
            state: Current game state
            depth: Remaining depth to search
            is_maximizing: True if it's the AI's turn
            alpha: Best score for maximizing player
            beta: Best score for minimizing player

        Returns:
            Evaluation score
        """
        self.nodes_evaluated += 1

        # Terminal conditions
        if state.concluded:
            return Evaluator.evaluate(state, self.player_number)

        if depth <= 0:
            return Evaluator.evaluate(state, self.player_number)

        current_player = state.current_player

        if is_maximizing:
            # AI's turn - maximize score
            max_eval = float('-inf')

            # Generate all possible turn sequences
            sequences = self._generate_turn_sequences(state, current_player, max_actions=8)

            for actions in sequences:  # Limit for performance
                test_state = state.copy()
                for action in actions:
                    self._apply_action(test_state, current_player, action)

                GameSimulator.end_turn(test_state)

                if test_state.concluded:
                    eval_score = Evaluator.evaluate(test_state, self.player_number)
                else:
                    eval_score = self._minimax(test_state, depth - 1, False, alpha, beta)

                max_eval = max(max_eval, eval_score)
                alpha = max(alpha, eval_score)

                if beta <= alpha:
                    break  # Beta cutoff

            return max_eval
        else:
            # Opponent's turn - minimize score
            min_eval = float('inf')

            # Generate all possible turn sequences for opponent
            sequences = self._generate_turn_sequences(state, current_player, max_actions=8)

            for actions in sequences:  # Limit for performance
                test_state = state.copy()
                for action in actions:
                    self._apply_action(test_state, current_player, action)

                GameSimulator.end_turn(test_state)

                if test_state.concluded:
                    eval_score = Evaluator.evaluate(test_state, self.player_number)
                else:
                    eval_score = self._minimax(test_state, depth - 1, True, alpha, beta)

                min_eval = min(min_eval, eval_score)
                beta = min(beta, eval_score)

                if beta <= alpha:
                    break  # Alpha cutoff

            return min_eval


class MinimaxAIPlayer:
    """
    Wrapper class that provides the same interface as the original AIPlayer
    but uses minimax for decision making.
    """

    def __init__(self, player_number: int, depth: int = 2):
        self.player_number = player_number
        self.minimax_ai = MinimaxAI(player_number, max_depth=depth)
        self.pending_actions: List[Tuple] = []
        self.action_index = 0

    def clear_pending_actions(self):
        """Clear any pending actions."""
        self.pending_actions = []
        self.action_index = 0

    def take_turn(self, game_state: 'SHCGGameState', ui_draw: bool, ui_set_text: bool,
                  update_dropdown_func=None, text_box=None) -> list:
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
                text_box.append_html_text(f"AI Player {player} calculated {len(self.pending_actions)} actions (evaluated {self.minimax_ai.nodes_evaluated} positions).\n")

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
            card_template, target_template = action[1], action[2]

            # Find the actual card in hand
            actual_card = None
            for c in game_state.hands[player]:
                if c.name == card_template.name and c.cost == card_template.cost:
                    actual_card = c
                    break

            if actual_card is None:
                return self.take_turn(game_state, ui_draw, ui_set_text, update_dropdown_func, text_box)

            # Find actual target if needed
            actual_target = None
            if target_template is not None:
                for f in game_state.fields[player]:
                    if f.type == 'follower' and f.name == target_template.name:
                        actual_target = f
                        break

            game_state.play_card(player, actual_card, ui_draw, ui_set_text, ai_target=actual_target)
            return [('play', actual_card)]

        elif action_type == 'attack':
            attacker_template, target_template = action[1], action[2]

            # Find actual attacker
            actual_attacker = None
            for f in game_state.fields[player]:
                if (f.type == 'follower' and f.name == attacker_template.name and
                    f.can_attack_this_turn):
                    actual_attacker = f
                    break

            if actual_attacker is None:
                return self.take_turn(game_state, ui_draw, ui_set_text, update_dropdown_func, text_box)

            # Find actual target
            if target_template == "leader":
                actual_target = "leader"
            else:
                actual_target = None
                opponent = 3 - player
                for f in game_state.fields[opponent]:
                    if f.type == 'follower' and f.name == target_template.name:
                        actual_target = f
                        break

                if actual_target is None:
                    return self.take_turn(game_state, ui_draw, ui_set_text, update_dropdown_func, text_box)

            game_state.follower_attack(player, actual_attacker, actual_target, ui_draw, ui_set_text)
            return [('attack', actual_attacker, actual_target)]

        elif action_type == 'enhance':
            follower_template = action[1]

            # Find actual follower
            actual_follower = None
            for f in game_state.fields[player]:
                if (f.type == 'follower' and f.name == follower_template.name and
                    hasattr(f, 'can_enhance') and f.can_enhance):
                    actual_follower = f
                    break

            if actual_follower is None:
                return self.take_turn(game_state, ui_draw, ui_set_text, update_dropdown_func, text_box)

            actual_follower.on_enhance_effect(player)
            game_state.enhance_used_this_turn[player] += 1
            game_state.use_foxtail(player, 1, ui_draw, ui_set_text)
            if ui_draw:
                game_state.draw_field_ui(player)
            if ui_set_text and text_box:
                text_box.append_html_text(f"AI Player {player} enhanced {actual_follower}.\n")
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
        self.ai_action_delay: int = 600  # milliseconds between AI actions
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
