"""
Chess-like AI Player for Super Hard Card Game.
Uses minimax with alpha-beta pruning to calculate optimal moves.
Since all information is open (hands, decks, fields), this is a perfect information game.
"""
import datetime
import json
import uuid
import itertools
import cards
import shcg_error
import random
from typing import TYPE_CHECKING, List, Tuple, Any, Optional
from ai_player_evaluator import Evaluator
if TYPE_CHECKING:
    from super_hard_card_game import SHCGGameState

# Game constants
MAX_FIELD_SIZE = 5
MAX_HAND_SIZE = 9
MAX_FOXTAIL = 9
DEFAULT_HP_F = 20
DEFAULT_HP_S = 26
DEFAULT_MAX_ENHANCE_PER_TURN = 1

# AI constants
DEFAULT_AI_ACTION_DELAY_MS = 600
SINGLE_ACTION_SEQ_MAX_LENGTH = 30


def _find_card_by_id(card_list: List[cards.Card], unique_id) -> Optional[cards.Card]:
    """Find a card in a list by its unique_id."""
    for card in card_list:
        if card.unique_id == unique_id:
            return card
    return None


def _find_card_in_zones(state, unique_id, player: int) -> Optional[cards.Card]:
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
    return _find_card_by_id(all_cards, unique_id)


def _find_card_by_void_id(card_list: List[cards.Card], void_id) -> Optional[cards.Card]:
    for card in card_list:
        if card.void_id == void_id:
            return card
    return None


def _find_card_in_zones_by_void_id(state, void_id, player: int) -> Optional[cards.Card]:
    all_cards = (
        state.fields[player] + state.fields[3 - player] +
        state.hands[player] + state.hands[3 - player] +
        state.decks[player] + state.decks[3 - player] +
        state.graveyard[player] + state.graveyard[3 - player] +
        state.banished[player] + state.banished[3 - player]
    )
    return _find_card_by_void_id(all_cards, void_id)



class GameStateSnapshot:
    """
    A lightweight, copyable snapshot of game state for simulation.
    Does not include any UI elements.
    """
    def __init__(self):
        # WARNING: Make sure to also modify from_game_state, copy, and serialize_to_string/load_from_string
        # methods when adding new attributes
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
        self.hidden_cards: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.graveyard: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.banished: dict[int, list[cards.Card]] = {1: [], 2: []}

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
            snap.hidden_cards[player] = [_copy_card(c) for c in game_state.hidden_cards[player]]
            snap.graveyard[player] = [_copy_card(c) for c in game_state.graveyard[player]]
            snap.banished[player] = [_copy_card(c) for c in game_state.banished[player]]

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
            new_snap.hidden_cards[player] = [_copy_card(c) for c in self.hidden_cards[player]]
            new_snap.graveyard[player] = [_copy_card(c) for c in self.graveyard[player]]
            new_snap.banished[player] = [_copy_card(c) for c in self.banished[player]]

        return new_snap

    def serialize_to_string(self) -> str:
        """Serialize the entire game state to a JSON string. Can be restored with load_from_string."""
        def serialize_zone(card_list):
            return [_serialize_card(c) for c in card_list]

        data = {
            'current_player': self.current_player,
            'turn': self.turn,
            'concluded': self.concluded,
            'winner': self.winner,
            'hp': {str(k): v for k, v in self.hp.items()},
            'max_hp': {str(k): v for k, v in self.max_hp.items()},
            'foxtail': {str(k): v for k, v in self.foxtail.items()},
            'enhance_used_this_turn': {str(k): v for k, v in self.enhance_used_this_turn.items()},
            'max_enhance_allowed_per_turn': {str(k): v for k, v in self.max_enhance_allowed_per_turn.items()},
            'amount_card_generated_from_void': {str(k): v for k, v in self.amount_card_generated_from_void.items()},
            'decks': {str(k): serialize_zone(v) for k, v in self.decks.items()},
            'hands': {str(k): serialize_zone(v) for k, v in self.hands.items()},
            'fields': {str(k): serialize_zone(v) for k, v in self.fields.items()},
            'hidden_cards': {str(k): serialize_zone(v) for k, v in self.hidden_cards.items()},
            'graveyard': {str(k): serialize_zone(v) for k, v in self.graveyard.items()},
            'banished': {str(k): serialize_zone(v) for k, v in self.banished.items()},
        }
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def load_from_string(s: str) -> 'GameStateSnapshot':
        """Restore a GameStateSnapshot from a JSON string produced by serialize_to_string."""
        data = json.loads(s)

        def deserialize_zone(card_dicts):
            return [_deserialize_card(d) for d in card_dicts]

        snap = GameStateSnapshot()
        snap.current_player = data['current_player']
        snap.turn = data['turn']
        snap.concluded = data['concluded']
        snap.winner = data['winner']
        snap.hp = {int(k): v for k, v in data['hp'].items()}
        snap.max_hp = {int(k): v for k, v in data['max_hp'].items()}
        snap.foxtail = {int(k): v for k, v in data['foxtail'].items()}
        snap.enhance_used_this_turn = {int(k): v for k, v in data['enhance_used_this_turn'].items()}
        snap.max_enhance_allowed_per_turn = {int(k): v for k, v in data['max_enhance_allowed_per_turn'].items()}
        snap.amount_card_generated_from_void = {int(k): v for k, v in data['amount_card_generated_from_void'].items()}

        for player_str in ['1', '2']:
            p = int(player_str)
            snap.decks[p] = deserialize_zone(data['decks'][player_str])
            snap.hands[p] = deserialize_zone(data['hands'][player_str])
            snap.fields[p] = deserialize_zone(data['fields'][player_str])
            snap.hidden_cards[p] = deserialize_zone(data['hidden_cards'][player_str])
            snap.graveyard[p] = deserialize_zone(data['graveyard'][player_str])
            snap.banished[p] = deserialize_zone(data['banished'][player_str])

        return snap

    def player_take_damage(self, player: int, amount: int, *args, **_kwargs) -> bool:
        """Apply damage to a player. Returns True if player is defeated."""
        assert amount >= 0
        if 'is_follower_attack' in _kwargs:
            is_follower_attack = _kwargs['is_follower_attack']
        else:
            is_follower_attack = False
        if not is_follower_attack:
            for c in self.fields[player]:
                if isinstance(c, cards.神弓の座天使リリエル):
                    return False
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

    def draw_card_by_effect(self, player, num_cards, *args, **_kwargs):
        """
        draw num_cards cards by card effect.
        """
        for _ in range(num_cards):
            if self.decks[player] and len(self.hands[player]) < MAX_HAND_SIZE:
                drawn_card = self.decks[player].pop()
                self.hands[player].append(drawn_card)

    def add_foxtail(self, player, amount, *args, **_kwargs):
        # add amount of foxtail for player (capped at MAX_FOXTAIL)
        assert amount >= 0
        if amount == 0 or self.foxtail[player] >= MAX_FOXTAIL:
            return
        self.foxtail[player] = min(MAX_FOXTAIL, self.foxtail[player] + amount)


def _copy_card(card: cards.Card) -> cards.Card:
    """Create a deep copy of a card."""
    # Create new instance of the same class without running __init__
    new_card = card.__class__.__new__(card.__class__)

    # Common attributes copied for all card types
    common_attrs = [
        'name', 'cost', 'original_cost', 'type', 'unique_id', 'is_generated',
        'void_id', 'description', 'effect_description', 'request_card_selection_on_play', 'request_multi_card_selection_on_play',
        'request_effect_choose_option', 'extra_effect_list'
    ]
    # Mutable list attributes that may be modified during simulation (e.g., extra_effect_list
    # is appended to by 茨の森's effect_when_other_follower_summon). These must be shallow-copied
    # to avoid shared references between the original and the copy corrupting the base state
    # across simulation rounds.
    list_attrs = {'request_card_selection_on_play', 'request_effect_choose_option', 'extra_effect_list'}
    for attr in common_attrs:
        if hasattr(card, attr):
            val = getattr(card, attr)
            if attr in list_attrs:
                val = list(val)
            setattr(new_card, attr, val)
        else:
            raise shcg_error.TimeError(f"Card {card} missing expected attribute {attr} during copy.")

    # Follower-specific attributes
    if isinstance(card, cards.Follower):
        follower_attrs = [
            'description_e', 'attack', 'hp', 'max_hp', 'original_attack', 'original_max_hp', 'can_enhance', 'is_enhanced',
            'summoned_this_turn', 'enhanced_this_turn', 'request_card_selection_on_enhance', 'request_multi_card_selection_on_enhance', 'request_effect_choose_option_e',
            'attack_ability', 'how_many_attacks_max_of_turn', 'how_many_attacks_done_of_turn',
            'can_attack_this_turn', 'ability_rush', 'ability_super_rush', 'ability_protect', 'ability_drain',
            'ability_lethal'
        ]
        follower_list_attrs = {'request_card_selection_on_enhance', 'request_effect_choose_option_e'}
        for attr in follower_attrs:
            if hasattr(card, attr):
                val = getattr(card, attr)
                if attr in follower_list_attrs:
                    val = list(val)
                setattr(new_card, attr, val)
            else:
                raise shcg_error.TimeError(f"Follower {card} missing expected attribute {attr} during copy.")

    elif isinstance(card, cards.Amulet):
        amulet_attrs = [
            'counter_name', 'counter', 'counter_max', 'amulet_value_for_evaluate'
        ]
        for attr in amulet_attrs:
            if hasattr(card, attr):
                setattr(new_card, attr, getattr(card, attr))
            else:
                raise shcg_error.TimeError(f"Amulet {card} missing expected attribute {attr} during copy.")

    return new_card


def _serialize_card(card: cards.Card) -> dict:
    """Serialize a card to a JSON-compatible dict."""
    d = {
        'cls': card.__class__.__name__,
        'uid': str(card.unique_id),
        'vid': str(card.void_id),
        'gen': card.is_generated,
        'cost': card.cost,
        'ocost': card.original_cost,
        'exl': card.extra_effect_list
    }
    if isinstance(card, cards.Follower):
        d['t'] = 'follower'
        d['atk'] = card.attack
        d['hp'] = card.hp
        d['mhp'] = card.max_hp
        d['oatk'] = card.original_attack
        d['omhp'] = card.original_max_hp
        d['ce'] = card.can_enhance
        d['ie'] = card.is_enhanced
        d['st'] = card.summoned_this_turn
        d['et'] = card.enhanced_this_turn
        d['aa'] = card.attack_ability
        d['hamt'] = card.how_many_attacks_max_of_turn
        d['hadt'] = card.how_many_attacks_done_of_turn
        d['cat'] = card.can_attack_this_turn
        d['ar'] = card.ability_rush
        d['asr'] = card.ability_super_rush
        d['ap'] = card.ability_protect
        d['ad'] = card.ability_drain
        d['al'] = card.ability_lethal
    elif isinstance(card, cards.Amulet):
        d['t'] = 'amulet'
        d['cnt'] = card.counter
        d['cmax'] = card.counter_max
    elif isinstance(card, cards.Spell):
        d['t'] = 'spell'
    return d


def _deserialize_card(d: dict) -> cards.Card:
    """Deserialize a card from a dict."""
    cls_name = d['cls']
    if cls_name not in cards.card_class_by_name:
        raise ValueError(f"Unknown card class: {cls_name}")
    card_cls = cards.card_class_by_name[cls_name]
    card = card_cls()
    card.unique_id = uuid.UUID(d['uid'])
    card.void_id = uuid.UUID(d['vid'])
    card.is_generated = d['gen']
    card.cost = d['cost']
    card.original_cost = d['ocost']
    card.extra_effect_list = d['exl']

    if isinstance(card, cards.Follower):
        card.attack = d['atk']
        card.hp = d['hp']
        card.max_hp = d['mhp']
        card.original_attack = d['oatk']
        card.original_max_hp = d['omhp']
        card.can_enhance = d['ce']
        card.is_enhanced = d['ie']
        card.summoned_this_turn = d['st']
        card.enhanced_this_turn = d['et']
        card.attack_ability = d['aa']
        card.how_many_attacks_max_of_turn = d['hamt']
        card.how_many_attacks_done_of_turn = d['hadt']
        card.can_attack_this_turn = d['cat']
        card.ability_rush = d['ar']
        card.ability_super_rush = d['asr']
        card.ability_protect = d['ap']
        card.ability_drain = d['ad']
        card.ability_lethal = d['al']
    elif isinstance(card, cards.Amulet):
        card.counter = d['cnt']
        card.counter_max = d['cmax']

    return card


class GameSimulator:
    """
    Simulates game actions on a GameStateSnapshot without UI.
    """

    @staticmethod
    def play_card(state: GameStateSnapshot, player: int, card: cards.Card,
                  targets: list[cards.Card] | None = None, effect_choice: str | None = None,
                  multi_targets: list[cards.Card] | None = None) -> bool:
        """Play a card from hand. Returns True if successful.
        targets: list of selected cards (one per step in request_card_selection_on_play), or None.
        multi_targets: multi card selection (list[Card] or None).
        Both can co-exist on the same card.
        """
        if len(state.fields[player]) >= MAX_FIELD_SIZE and card.type != 'spell':
            return False
        if state.foxtail[player] < card.cost:
            return False
        if card not in state.hands[player]:
            return False

        state.foxtail[player] -= card.cost
        state.hands[player].remove(card)

        if "skip_on_play_effect" in card.extra_effect_list:
            pass
        else:
            card.on_play_effect(state, False, False, None, targets, effect_choice, multi_targets)

        if isinstance(card, cards.Follower):
            card.mv([card], "summon", state, draw_ui=False, set_text=False, the_actual_textbox=None, player=player)
        elif isinstance(card, cards.Amulet):
            state.fields[player].append(card)
        elif isinstance(card, cards.Spell):
            state.graveyard[player].append(card)
            # if has star pheonix in graveyard, summon it.
            if state.graveyard[player]:
                for c in state.graveyard[player].copy():
                    if isinstance(c, cards.スターフェニックス):
                        c.reset_stats()  # reset stats before summoning
                        c.mv(state.graveyard[player], "summon", state, draw_ui=False, set_text=False, the_actual_textbox=None, player=player)

        return True

    @staticmethod
    def follower_attack(state: GameStateSnapshot, player: int,
                        attacker: cards.Follower, target: cards.Follower | str) -> bool:
        """Execute an attack. Target can be a Follower or "leader". Returns True if successful."""
        if attacker.attack_ability <= 0 or not attacker.can_attack_this_turn:
            return False
        if attacker not in state.fields[player]:
            return False
        protect_exists = any([c.ability_protect for c in state.fields[3 - player] if isinstance(c, cards.Follower)])

        # attacker before attack effect
        attacker.before_attack_effect(state, False, False, None, target)

        opponent = 3 - player

        if isinstance(target, cards.Follower):
            if target not in state.fields[opponent]:
                return False
            if not target.ability_protect and protect_exists:
                return False

            # Combat
            target_hp_before = target.hp
            # target.hp -= attacker.attack
            target.take_damage(attacker.attack, state, False, False, None, attacker=attacker, is_battle_damage=True)
            target_hp_changed = target_hp_before - target.hp
            # drain ability
            if attacker.ability_drain and target_hp_changed > 0:
                state.player_heal(player, target_hp_changed)
            # attacker.hp -= target.attack
            attacker.take_damage(target.attack, state, False, False, None, attacker=attacker, is_battle_damage=True)
            attacker.after_attack_effect()

        elif target == "leader":
            if attacker.attack_ability < 2:
                return False
            if protect_exists:
                return False
            state.player_take_damage(opponent, attacker.attack, ui_draw=False, ui_set_text=False, is_follower_attack=True)
            # drain ability
            if attacker.ability_drain and attacker.attack > 0:
                state.player_heal(player, attacker.attack)
            attacker.after_attack_effect()

        return True

    @staticmethod
    def enhance_follower(state: GameStateSnapshot, player: int,
                         follower: cards.Follower, extra_targets: list[cards.Card] | None = None,
                         effect_choice: str | None = None,
                         multi_targets: list[cards.Card] | None = None) -> bool:
        """Enhance a follower. Returns True if successful.
        extra_targets: list of selected cards (one per step in request_card_selection_on_enhance), or None.
        """
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

        follower.on_enhance_effect(state, False, False, None, selected_card_for_effect=extra_targets,
                                    effect_choice=effect_choice,
                                    selected_cards_for_multi_effect=multi_targets)

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
            if "end_of_turn_destroy" in c.extra_effect_list and c in state.fields[state.current_player]:  # check if still on field after end of turn effect
                c.mv(state.fields[state.current_player], "destroy", state, False, False, None, player=state.current_player)

        state.current_player = state.opponent
        state.foxtail[state.current_player] = MAX_FOXTAIL

        # Apply start of turn effects to current player's followers
        for card in state.fields[state.current_player].copy():
            card.start_of_turn_on_field_effect(state, False, False, None)

        for card in itertools.chain(state.hands[state.current_player].copy(), state.graveyard[state.current_player].copy(), 
                                    state.banished[state.current_player].copy(), state.decks[state.current_player].copy()):
            card.start_of_turn_not_on_field_effect(state, False, False, None)

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
    def _get_targets_for_selection_type(sel_type: str, state: GameStateSnapshot, player: int) -> list:
        """Get list of valid targets for a given selection type."""
        match sel_type:
            case "field":
                return [f for f in state.fields[player] if isinstance(f, cards.Follower)]
            case "field_opponent":
                return [f for f in state.fields[3 - player] if isinstance(f, cards.Follower)]
            case "field_both":
                return [f for f in state.fields[player] + state.fields[3 - player] if isinstance(f, cards.Follower)]
            case "hand":
                return list(state.hands[player])
            case "hand_follower":
                return [c for c in state.hands[player] if isinstance(c, cards.Follower)]
            case "hand_spell":
                return [c for c in state.hands[player] if isinstance(c, cards.Spell)]
            case "hand_follower_aiteru":
                return [c for c in state.hands[player] if c.type == 'follower' and c.cost <= len([x for x in state.hands[player] if x.type == 'follower'])]
            case "hand_opponent":
                return list(state.hands[3 - player])
            case "field_c":
                return list(state.fields[player])
            case "field_opponent_c":
                return list(state.fields[3 - player])
            case "field_both_c":
                return list(state.fields[player] + state.fields[3 - player])
            case _:
                raise shcg_error.TimeError(f"Unknown selection type: {sel_type}") 

    @staticmethod
    def get_playable_cards(state: GameStateSnapshot, player: int) -> List[Tuple]:
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
            if card.type != 'spell' and field_count >= MAX_FIELD_SIZE:
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
    def get_possible_attacks(state: GameStateSnapshot, player: int) -> List[Tuple[cards.Follower, cards.Follower | str]]:
        """
        Get all possible attacks.
        Returns list of (attacker, target) tuples. Target is Follower or "leader".
        """
        attacks = []
        opponent = 3 - player

        # check if opponent has any followers with ability_protect
        # if so, only those followers can be attacked
        protect_exists = any([c.ability_protect for c in state.fields[opponent] if isinstance(c, cards.Follower)])
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
    def get_enhanceable_followers(state: GameStateSnapshot, player: int) -> List[Tuple]:
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
    def can_draw_card(state: GameStateSnapshot, player: int) -> bool:
        """Check if the player can draw a card."""
        return (state.foxtail[player] >= 1 and
                len(state.hands[player]) < MAX_HAND_SIZE and
                len(state.decks[player]) > 0)


class MinimaxAI:
    """
    Not minimax at all.
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

    def get_best_turn_actions(self, game_state: 'SHCGGameState') -> List[Tuple]:
        """
        Calculate and return the best sequence of actions for this turn.
        Written and Verified by Rokafox on 2026/02/05
        """
        # print(f"{self.continuous_unique_endturnstates_req_player_turn}, {self.continuous_unique_endturnstates_req_opp_turn}, {self.unique_states_max_player_turn}, {self.unique_states_max_opp_turn}")
        self.endturnstate_evaluated = 0
        self.endturnstate_evaluated_additional = 0
        self.loss_endturnstate_avoided = 0
        state = GameStateSnapshot.from_game_state(game_state)

        # Find all possible turn action sequences and evaluate them
        best_score = float('-inf')
        best_actions = []

        # Generate and evaluate possible action sequences
        all_sequences = self._generate_random_turn_sequences(state, self.player_number, 
                                                             self.continuous_unique_endturnstates_req_player_turn, 
                                                             self.unique_states_max_player_turn)

        for actions in all_sequences:
            # Apply actions to a copy of the state
            test_state = state.copy()
            for action in actions:
                if not self._apply_action(test_state, self.player_number, action):
                    raise shcg_error.AIError("Invalid action sequence generated.")

            GameSimulator.end_turn(test_state)
            score = Evaluator.evaluate_new(test_state, self.player_number, only_care_about_winorlose=False) # Basic evaluation

            # Advanced evaluation: simulate opponent's turn
            # If opponent scores inf for any seq, its a loss for us and set score to -inf.
            # This part can be skipped if the player is already winning (score == inf)
            # or losing (score == -inf) as checked in True basic_lethal_check or draw (score == 0.0)
            if not score == float('inf') and not score == float('-inf') and not score == 0.0:
                opponent_sequences = self._generate_random_turn_sequences(test_state, 3 - self.player_number, 
                                                                          self.continuous_unique_endturnstates_req_opp_turn, 
                                                                          self.unique_states_max_opp_turn)
                for single_opp_seq in opponent_sequences:
                    opp_test_state = test_state.copy()
                    for opp_action in single_opp_seq:
                        if not self._apply_action(opp_test_state, test_state.current_player, opp_action):
                            raise shcg_error.AIError("Invalid opponent action sequence generated.")

                    # End opponent's turn
                    GameSimulator.end_turn(opp_test_state)
                    # No basic lethal check. Only matters if opponent can score infinity here
                    opp_score = Evaluator.evaluate_new(opp_test_state, 3 - self.player_number, only_care_about_winorlose=True)
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


    def _generate_random_turn_sequences(self, state: GameStateSnapshot, player: int,
                                        min_continuous_visited_state_req: int, max_unique_states: int
                                        ) -> List[List[Tuple]]:
        """
        Generate random reasonable action sequences for a turn.
        min_continuous_visited_state_req: Stop If the end result same state is visited this many times continuously.
        This value should be high enough to allow many more thorough explorations.
        Only terminal sequences are accepted (foxtail=0 or no more actions possible)
        Written and Verified by Rokafox on 2026/02/04
        """
        bundle_of_all_action_sequences = []
        visited_states = set()
        continuous_visited_state_count = 0
        current_state = state.copy() # the original environment
        single_action_seq = []

        while continuous_visited_state_count < min_continuous_visited_state_req and len(visited_states) < max_unique_states:
            # do: generate single action sequences until requirement is met
            # single_action_seq too long? Maybe a infinite loop.
            if len(single_action_seq) > SINGLE_ACTION_SEQ_MAX_LENGTH:
                print("Action sequence too long. Resetting.")
                next_possible_actions = [] # force stop and reset
            else:
                next_possible_actions: list[tuple] = self._get_all_actions(current_state, player)

            if not next_possible_actions: # if terminal state
                # hash, compare, if in visited_states, increase continuous_visited_state_count
                # else reset continuous_visited_state_count
                state_hash = current_state.serialize_to_string()
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
                raise shcg_error.AIError("Invalid action sequence generated.")

        return bundle_of_all_action_sequences

    def _get_all_actions(self, state: GameStateSnapshot, player: int) -> List[Tuple]:
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

    def _apply_action(self, state: GameStateSnapshot, player: int, action: Tuple) -> bool:
        """Apply an action to the state. Returns True if successful."""
        action_type = action[0]

        if action_type == 'play':
            card, targets_template, effect_choice = action[1], action[2], action[3]
            multi_targets_template = action[4] if len(action) > 4 else None
            if card.is_generated:
                actual_card = _find_card_by_void_id(state.hands[player], card.void_id)
            else:
                actual_card = _find_card_by_id(state.hands[player], card.unique_id)
            if actual_card is None:
                # state_string = state.serialize_to_string()
                # save_path = f"error_state_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                # with open(save_path, "w", encoding="utf-8") as f:
                #     f.write(state_string)
                # print(f"Play, {card}, {targets_template}, {effect_choice}, {multi_targets_template}")
                raise shcg_error.CardNotFoundError(f"Card to play not found in hand: {card} with void_id {card.void_id} and unique_id {card.unique_id}")

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
                            raise shcg_error.CardNotFoundError(f"Target for card play not found: {t}")
                        actual_targets.append(at)
                    else:
                        at = _find_card_in_zones(state, t.unique_id, player)
                        if at is None:
                            raise shcg_error.CardNotFoundError(f"Target for card play not found: {t}")
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
                        raise shcg_error.CardNotFoundError(f"Multi-target for card play not found: {t}")
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
                raise shcg_error.CardNotFoundError(f"Attacker not found on field: {attacker}")

            if target == "leader":
                actual_target = "leader"
            else:
                actual_target = _find_card_by_id(state.fields[3 - player], target.unique_id)
                if actual_target is None:
                    # state_string = state.serialize_to_string()
                    # save_path = f"error_state_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    # with open(save_path, "w", encoding="utf-8") as f:
                    #     f.write(state_string)
                    # print(f"Attack, {attacker}, {target}")
                    raise shcg_error.CardNotFoundError(f"Attack target not found on field: {target}")

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
                # state_string = state.serialize_to_string()
                # save_path = f"error_state_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                # with open(save_path, "w", encoding="utf-8") as f:
                #     f.write(state_string)
                # print(f"Enhance, {follower}, {targets_template}, {effect_choice}, {multi_targets_template}")
                raise shcg_error.CardNotFoundError(f"Follower to enhance not found on field: {follower}")

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
                            raise shcg_error.CardNotFoundError(f"Target for card enhance not found: {t}")
                        actual_targets.append(at)
                    else:
                        at = _find_card_in_zones(state, t.unique_id, player)
                        if at is None:
                            raise shcg_error.CardNotFoundError(f"Target for card enhance not found: {t}")
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
                        raise shcg_error.CardNotFoundError(f"Multi-target for card enhance not found: {t}")
                    actual_multi_targets.append(at)

            return GameSimulator.enhance_follower(state, player, actual_follower, actual_targets,
                                                  effect_choice=effect_choice,
                                                  multi_targets=actual_multi_targets)

        elif action_type == 'draw':
            return GameSimulator.draw_card(state, player)

        return False


class MinimaxAIPlayer:
    """
    Wrapper class that provides the same interface as the original AIPlayer
    but uses minimax for decision making.
    """

    def __init__(self, player_number: int, cuets_player_turn: int, cuets_opp_turn: int, unique_states_max_player_turn: int, unique_states_max_opp_turn: int):
        self.player_number = player_number
        self.minimax_ai = MinimaxAI(player_number, cuets_player_turn, cuets_opp_turn, unique_states_max_player_turn, unique_states_max_opp_turn)
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
            card_template, targets_template, effect_choice = action[1], action[2], action[3]
            multi_targets_template = action[4] if len(action) > 4 else None

            if card_template.is_generated:
                actual_card = _find_card_by_void_id(game_state.hands[player], card_template.void_id)
            else:
                actual_card = _find_card_by_id(game_state.hands[player], card_template.unique_id)
            if actual_card is None:
                raise shcg_error.CardNotFoundError("Card to play not found in hand")

            # Resolve targets list (one per selection step)
            actual_targets = None
            if targets_template is not None:
                actual_targets = []
                for t in targets_template:
                    if t is None:
                        actual_targets.append(None)
                    elif t.is_generated:
                        at = _find_card_in_zones_by_void_id(game_state, t.void_id, player)
                        if at is None:
                            raise shcg_error.CardNotFoundError("Target for card play not found")
                        actual_targets.append(at)
                    else:
                        at = _find_card_in_zones(game_state, t.unique_id, player)
                        if at is None:
                            raise shcg_error.CardNotFoundError("Target for card play not found")
                        actual_targets.append(at)

            # Resolve multi targets
            actual_multi_targets = None
            if multi_targets_template is not None:
                actual_multi_targets = []
                for t in multi_targets_template:
                    if t.is_generated:
                        at = _find_card_in_zones_by_void_id(game_state, t.void_id, player)
                    else:
                        at = _find_card_in_zones(game_state, t.unique_id, player)
                    if at is None:
                        raise shcg_error.CardNotFoundError(f"Multi-target for card play not found: {t}")
                    actual_multi_targets.append(at)

            game_state.play_card(player, actual_card, ui_draw, ui_set_text, additional_targets=actual_targets, is_ai_player=True,
                                 effect_choice=effect_choice, additional_multi_targets=actual_multi_targets)
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
                raise shcg_error.CardNotFoundError("Attacker not found on field")

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
                    raise shcg_error.CardNotFoundError("Attack target not found on field")

            game_state.follower_attack(player, actual_attacker, actual_target, ui_draw, ui_set_text)
            return [('attack', actual_attacker, actual_target)]

        elif action_type == 'enhance':
            follower_template, targets_template, effect_choice = action[1], action[2], action[3]
            multi_targets_template = action[4] if len(action) > 4 else None

            if follower_template.is_generated:
                actual_follower = next(
                    (f for f in game_state.fields[player]
                    if f.type == 'follower' and f.void_id == follower_template.void_id and f.can_enhance),
                    None
            )
            else:
                actual_follower = next(
                    (f for f in game_state.fields[player]
                    if f.type == 'follower' and f.unique_id == follower_template.unique_id and f.can_enhance),
                    None
                )
            if actual_follower is None:
                raise shcg_error.CardNotFoundError(f"Follower to enhance not found on field: {actual_follower}")

            # Resolve targets list (one per selection step)
            actual_targets = None
            if targets_template is not None:
                actual_targets = []
                for t in targets_template:
                    if t is None:
                        actual_targets.append(None)
                    elif t.is_generated:
                        at = _find_card_in_zones_by_void_id(game_state, t.void_id, player)
                        if at is None:
                            raise shcg_error.CardNotFoundError("Target for enhance not found")
                        actual_targets.append(at)
                    else:
                        at = _find_card_in_zones(game_state, t.unique_id, player)
                        if at is None:
                            raise shcg_error.CardNotFoundError("Target for enhance not found")
                        actual_targets.append(at)

            # Resolve multi targets
            actual_multi_targets = None
            if multi_targets_template is not None:
                actual_multi_targets = []
                for t in multi_targets_template:
                    if t.is_generated:
                        at = _find_card_in_zones_by_void_id(game_state, t.void_id, player)
                    else:
                        at = _find_card_in_zones(game_state, t.unique_id, player)
                    if at is None:
                        raise shcg_error.CardNotFoundError(f"Multi-target for card enhance not found: {t}")
                    actual_multi_targets.append(at)

            game_state.on_card_enhanced(player, actual_follower, actual_targets, is_ai_player=True,
                                        ui_set_text=ui_set_text, ui_draw=ui_draw, effect_choice=effect_choice,
                                        additional_multi_targets=actual_multi_targets)

            return [('enhance', actual_follower)]

        elif action_type == 'draw':
            game_state.draw_card_with_foxtail(player, ui_draw, ui_set_text)
            return [('draw',)]

        return []


class MinimaxAIManager:
    """Manages Minimax AI players for the game."""

    def __init__(self, cuets_player_turn: int, cuets_opp_turn: int, unique_states_max_player_turn: int, unique_states_max_opp_turn: int):
        self.ai_players: dict[int, MinimaxAIPlayer | None] = {1: None, 2: None}
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
            self.ai_players[player] = MinimaxAIPlayer(player, self.cuets_player_turn, self.cuets_opp_turn, 
                                                      self.unique_states_max_player_turn, self.unique_states_max_opp_turn)
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
