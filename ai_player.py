"""
AI Player module for Super Hard Card Game.
Provides intelligent decision-making for computer-controlled players.
"""
import cards
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from super_hard_card_game import SHCGGameState


class AIPlayer:
    """
    AI player that makes intelligent decisions based on game state evaluation.
    """

    def __init__(self, player_number: int):
        self.player_number = player_number

    def evaluate_card_value(self, card: cards.Card) -> float:
        """Evaluate the value of a card based on its stats and cost."""
        if card.type == 'follower':
            # Base value is stats per cost
            stat_total = card.attack + card.hp
            cost = max(card.cost, 1)  # Avoid division by zero
            value = stat_total / cost

            # Bonus for enhancement capability
            if hasattr(card, 'can_enhance') and card.can_enhance:
                value += 0.5

            # Bonus for special effects (like Gabriel)
            if hasattr(card, 'request_card_selection_on_play') and card.request_card_selection_on_play:
                value += 1.0

            return value
        elif card.type == 'spell':
            return 2.0  # Base spell value
        elif card.type == 'amulet':
            return 1.5  # Base amulet value
        return 1.0

    def evaluate_board_state(self, game_state: 'SHCGGameState') -> float:
        """
        Evaluate the current board state from this AI's perspective.
        Positive = AI is winning, Negative = opponent is winning.
        """
        player = self.player_number
        opponent = 3 - player

        score = 0.0

        # HP difference (more important when low)
        hp_diff = game_state.hp[player] - game_state.hp[opponent]
        score += hp_diff * 2

        # Field presence
        own_field_value = sum(f.attack + f.hp for f in game_state.fields[player] if f.type == 'follower')
        opp_field_value = sum(f.attack + f.hp for f in game_state.fields[opponent] if f.type == 'follower')
        score += (own_field_value - opp_field_value) * 1.5

        # Hand size advantage
        hand_diff = len(game_state.hands[player]) - len(game_state.hands[opponent])
        score += hand_diff * 0.5

        return score

    def get_best_play_card(self, game_state: 'SHCGGameState') -> cards.Card | None:
        """Find the best card to play from hand."""
        player = self.player_number
        hand = game_state.hands[player]
        foxtail = game_state.foxtail[player]
        field_count = len(game_state.fields[player])

        playable_cards = []
        for card in hand:
            # Check if we can afford it
            if card.cost > foxtail:
                continue
            # Check field space for non-spells
            if card.type != 'spell' and field_count >= 5:
                continue
            # For Gabriel-like cards, need a target on field
            if hasattr(card, 'request_card_selection_on_play') and card.request_card_selection_on_play == "field":
                if not any(c.type == 'follower' for c in game_state.fields[player]):
                    continue
            playable_cards.append(card)

        if not playable_cards:
            return None

        # Sort by value and cost efficiency
        # Prefer playing higher cost cards when we have the resources
        def card_priority(c):
            value = self.evaluate_card_value(c)
            # Bonus for using more foxtails efficiently
            efficiency_bonus = c.cost / 9.0  # Prefer using foxtails
            return value + efficiency_bonus

        playable_cards.sort(key=card_priority, reverse=True)
        return playable_cards[0]

    def get_best_attack_target(self, game_state: 'SHCGGameState', attacker: cards.Follower) -> cards.Follower | str | None:
        """
        Find the best target for an attacker.
        Returns a Follower, "leader", or None if shouldn't attack.
        """
        player = self.player_number
        opponent = 3 - player

        opp_followers = [f for f in game_state.fields[opponent] if f.type == 'follower']

        # Check if we have lethal on the leader
        if attacker.attack_ability >= 2:
            total_damage = attacker.attack
            for f in game_state.fields[player]:
                if f != attacker and f.type == 'follower' and f.can_attack_this_turn and f.attack_ability >= 2:
                    total_damage += f.attack
            if total_damage >= game_state.hp[opponent]:
                return "leader"  # Go for lethal

        # Look for favorable trades
        best_trade = None
        best_trade_value = -float('inf')

        for target in opp_followers:
            # Can we kill it?
            kills_target = attacker.attack >= target.hp
            # Will we survive?
            survives = attacker.hp > target.attack

            if kills_target and survives:
                # Great trade - kill without dying
                trade_value = (target.attack + target.hp) - 0  # We gain their value, lose nothing
                if trade_value > best_trade_value:
                    best_trade_value = trade_value
                    best_trade = target
            elif kills_target:
                # Even trade - both die
                trade_value = (target.attack + target.hp) - (attacker.attack + attacker.hp)
                # Only trade if we're killing something more valuable
                if trade_value > 0 and trade_value > best_trade_value:
                    best_trade_value = trade_value
                    best_trade = target

        if best_trade:
            return best_trade

        # If no good trades and can attack leader, go face
        if attacker.attack_ability >= 2 and not opp_followers:
            return "leader"

        # If we're significantly ahead on board, go face
        if attacker.attack_ability >= 2:
            own_power = sum(f.attack for f in game_state.fields[player] if f.type == 'follower')
            opp_power = sum(f.attack for f in opp_followers)
            if own_power > opp_power * 1.5:
                return "leader"

        return None

    def should_enhance(self, game_state: 'SHCGGameState', follower: cards.Follower) -> bool:
        """Determine if we should enhance a follower."""
        player = self.player_number

        # Check if enhance is available this turn
        if game_state.enhance_used_this_turn[player] >= game_state.max_enhance_allowed_per_turn[player]:
            return False

        # Check if follower can be enhanced
        if not hasattr(follower, 'can_enhance') or not follower.can_enhance:
            return False

        # Need at least 1 foxtail
        if game_state.foxtail[player] < 1:
            return False

        # Prefer enhancing followers that can attack this turn or next
        # Enhancing gives +2/+2 and advances attack ability

        # High priority: follower with low stats that could trade up after enhance
        current_stats = follower.attack + follower.hp
        if current_stats <= 6:  # Low cost followers benefit most
            return True

        # Also enhance if we have spare foxtails at end of turn
        if game_state.foxtail[player] >= 3:
            return True

        return False

    def get_best_follower_to_enhance(self, game_state: 'SHCGGameState') -> cards.Follower | None:
        """Find the best follower to enhance."""
        player = self.player_number

        if game_state.enhance_used_this_turn[player] >= game_state.max_enhance_allowed_per_turn[player]:
            return None

        if game_state.foxtail[player] < 1:
            return None

        enhanceable = [f for f in game_state.fields[player]
                       if f.type == 'follower' and hasattr(f, 'can_enhance') and f.can_enhance]

        if not enhanceable:
            return None

        # Prioritize followers that can attack or are about to attack
        def enhance_priority(f):
            priority = 0
            # Prefer followers that can attack this turn (enhance gives attack ability)
            if f.can_attack_this_turn or f.attack_ability >= 1:
                priority += 2
            # Prefer lower stat followers (bigger relative boost)
            priority += (10 - (f.attack + f.hp)) / 10
            return priority

        enhanceable.sort(key=enhance_priority, reverse=True)
        return enhanceable[0]

    def should_draw_card(self, game_state: 'SHCGGameState') -> bool:
        """Determine if we should spend foxtail to draw a card."""
        player = self.player_number

        # Can't draw if deck is empty or hand is full
        if not game_state.decks[player] or len(game_state.hands[player]) >= 9:
            return False

        # Need at least 1 foxtail
        if game_state.foxtail[player] < 1:
            return False

        # Draw if hand is small and we have spare foxtails
        if len(game_state.hands[player]) <= 2 and game_state.foxtail[player] >= 2:
            return True

        # Draw at end of turn if we have leftover foxtails
        # (This will be checked after other actions)
        if game_state.foxtail[player] >= 2 and len(game_state.hands[player]) <= 5:
            return True

        return False

    def get_gabriel_target(self, game_state: 'SHCGGameState') -> cards.Follower | None:
        """Find the best target for Gabriel's effect."""
        player = self.player_number
        followers = [f for f in game_state.fields[player] if f.type == 'follower']

        if not followers:
            return None

        # Prioritize followers that can attack soon
        def target_priority(f):
            priority = 0
            if f.can_attack_this_turn:
                priority += 3
            if f.attack_ability >= 1:
                priority += 2
            # Prefer buffing followers with high base attack
            priority += f.attack / 10
            return priority

        followers.sort(key=target_priority, reverse=True)
        return followers[0]

    def take_turn(self, game_state: 'SHCGGameState', ui_draw: bool, ui_set_text: bool,
                  update_dropdown_func=None, text_box=None) -> list:
        """
        Execute the AI's turn. Returns a list of actions taken.
        This method should be called repeatedly until it returns an empty list or "end_turn".
        """
        player = self.player_number
        actions = []

        # Phase 1: Play cards
        card_to_play = self.get_best_play_card(game_state)
        if card_to_play:
            ai_target = None
            # For Gabriel-like cards, find the best target
            if hasattr(card_to_play, 'request_card_selection_on_play') and card_to_play.request_card_selection_on_play == "field":
                ai_target = self.get_gabriel_target(game_state)

            game_state.play_card(player, card_to_play, ui_draw, ui_set_text, ai_target=ai_target)
            actions.append(('play', card_to_play))
            return actions  # Return after each action for UI update

        # Phase 2: Enhance followers
        follower_to_enhance = self.get_best_follower_to_enhance(game_state)
        if follower_to_enhance and self.should_enhance(game_state, follower_to_enhance):
            follower_to_enhance.on_enhance_effect(player)
            game_state.enhance_used_this_turn[player] += 1
            game_state.use_foxtail(player, 1, ui_draw, ui_set_text)
            if ui_draw:
                game_state.draw_field_ui(player)
            if ui_set_text and text_box:
                text_box.append_html_text(f"AI Player {player} enhanced {follower_to_enhance}.\n")
            actions.append(('enhance', follower_to_enhance))
            return actions

        # Phase 3: Attack with followers
        for follower in game_state.fields[player][:]:  # Copy list since it may change
            if follower.type != 'follower':
                continue
            if not follower.can_attack_this_turn or follower.attack_ability <= 0:
                continue

            target = self.get_best_attack_target(game_state, follower)
            if target:
                game_state.follower_attack(player, follower, target, ui_draw, ui_set_text)
                actions.append(('attack', follower, target))
                if game_state.concluded:
                    return actions
                return actions  # Return after each action for UI update

        # Phase 4: Draw cards with leftover foxtails
        if self.should_draw_card(game_state):
            game_state.draw_card_with_foxtail(player, ui_draw, ui_set_text)
            actions.append(('draw',))
            return actions

        # No more actions - end turn
        return []


class AIManager:
    """Manages AI players for the game."""

    def __init__(self):
        self.ai_players: dict[int, AIPlayer | None] = {1: None, 2: None}
        self.ai_enabled: dict[int, bool] = {1: False, 2: False}
        self.ai_action_delay: int = 500  # milliseconds between AI actions
        self.last_ai_action_time: int = 0

    def enable_ai(self, player: int, enabled: bool = True):
        """Enable or disable AI for a player."""
        self.ai_enabled[player] = enabled
        if enabled and self.ai_players[player] is None:
            self.ai_players[player] = AIPlayer(player)
        elif not enabled:
            self.ai_players[player] = None

    def is_ai_turn(self, game_state: 'SHCGGameState') -> bool:
        """Check if current player is controlled by AI."""
        return self.ai_enabled.get(game_state.current_player, False)

    def get_current_ai(self, game_state: 'SHCGGameState') -> AIPlayer | None:
        """Get the AI player for the current turn."""
        if self.is_ai_turn(game_state):
            return self.ai_players[game_state.current_player]
        return None
