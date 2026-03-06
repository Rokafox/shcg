"""
Game State class
"""
import copy
import itertools
import json
import shcg_core_cards
import shcg_core_error
import pygame
import pygame_gui



DEFAULT_HP_F = 20
DEFAULT_HP_S = 26

class SHCGGameState:
    def __init__(self, current_player):
        # update serialize_to_string and compute_state_hash and __deepcopy__ if you change the attributes here
        self.current_player = current_player  # 1 or 2
        self.turn = 1
        self.concluded = False
        self.winner = None
        self.decks: dict[int, list[shcg_core_cards.Card]] = {1: [], 2: []}
        self.hands: dict[int, list[shcg_core_cards.Card]] = {1: [], 2: []}
        self.fields: dict[int, list[shcg_core_cards.Card]] = {1: [], 2: []}
        self.max_hp = {1: DEFAULT_HP_S, 2: DEFAULT_HP_F}
        self.hp = {1: DEFAULT_HP_S, 2: DEFAULT_HP_F}
        self.foxtail = {1: 9, 2: 9}
        self.enhance_used_this_turn = {1: 0, 2: 0}
        self.max_enhance_allowed_per_turn = {1: 1, 2: 1}
        # Every time a card is generated, the player who generated it gets 1 count
        self.amount_card_generated_from_void: dict[int, int] = {1: 0, 2: 0}
        # hidden card
        self.hidden_cards: dict[int, list[shcg_core_cards.Card]] = {1: [], 2: []}
        # graveyard and banished zones
        self.graveyard: dict[int, list[shcg_core_cards.Card]] = {1: [], 2: []}
        self.banished: dict[int, list[shcg_core_cards.Card]] = {1: [], 2: []}
        # ui
        self.top_of_the_deck_ui_marker: dict[int, pygame_gui.elements.UIImage | None] = {1: None, 2: None}
        self.all_ui_components_to_none()
        # color
        self.deep_dark_blue = None
    
    def __deepcopy__(self, memo):
        new_state = SHCGGameState.__new__(SHCGGameState)
        memo[id(self)] = new_state

        # Scalar fields
        new_state.current_player = self.current_player
        new_state.turn = self.turn
        new_state.concluded = self.concluded
        new_state.winner = self.winner

        # Simple int-valued dicts — shallow copy is sufficient
        new_state.hp = dict(self.hp)
        new_state.max_hp = dict(self.max_hp)
        new_state.foxtail = dict(self.foxtail)
        new_state.enhance_used_this_turn = dict(self.enhance_used_this_turn)
        new_state.max_enhance_allowed_per_turn = dict(self.max_enhance_allowed_per_turn)
        new_state.amount_card_generated_from_void = dict(self.amount_card_generated_from_void)

        # Deep copy card zones.
        # unique_id / void_id must survive as the *same* string values so the AI's
        # find_card_by_id / find_card_by_void_id lookups match across state copies.
        # UUID objects are not safe here because some card constructors regenerate them;
        # we explicitly overwrite them with str() of the originals after deepcopy.
        def _copy_card(card):
            c = copy.deepcopy(card)
            c.unique_id = card.unique_id
            c.void_id = card.void_id
            return c

        def _copy_zone(zone):
            return [_copy_card(c) for c in zone]

        new_state.decks = {k: _copy_zone(v) for k, v in self.decks.items()}
        new_state.hands = {k: _copy_zone(v) for k, v in self.hands.items()}
        new_state.fields = {k: _copy_zone(v) for k, v in self.fields.items()}
        new_state.hidden_cards = {k: _copy_zone(v) for k, v in self.hidden_cards.items()}
        new_state.graveyard = {k: _copy_zone(v) for k, v in self.graveyard.items()}
        new_state.banished = {k: _copy_zone(v) for k, v in self.banished.items()}

        # UI references — never copied; always reset to None
        new_state.top_of_the_deck_ui_marker = {1: None, 2: None}
        new_state.deep_dark_blue = None
        new_state.all_ui_components_to_none()

        return new_state

    @property
    def opponent(self):
        return 3 - self.current_player

    def all_ui_components_to_none(self):
        self.image_others = None
        self.image_leader = None
        self.ui_manager = None
        self.draw_card_image_func = None
        self.image_405_card_slot = None
        self.player_2_hp_slot = None
        self.player_1_hp_slot = None
        self.leader_slots = None
        self.global_vars_tail_indicators = None
        self.global_vars_tail_indicators_active = None
        self.text_box = None
        self.global_vars_deck_slots = None
        self.global_vars_hand_slots = None
        self.global_vars_field_slots = None

    def draw_card_with_foxtail(self, player, ui_draw, ui_set_text):
        """
        At any time, the current player can consume 1 foxtail to draw a card. No restriction unless hand is full.
        """
        if self.decks[player] == [] or len(self.hands[player]) >= 9:
            return
        if self.foxtail[player] > 0:
            self.use_foxtail(player, 1, ui_draw, ui_set_text)
        else:
            return
        drawn_card = self.decks[player].pop()
        self.hands[player].append(drawn_card)
        if ui_set_text:
            self.text_box.append_html_text(f"プレイヤー{player}がカード{drawn_card}引いたのじゃ。\n")
        if ui_draw:
            self.draw_hand_ui(player)
            # draw_deck_ui is unnecessary as it is handled by pygame event

    def draw_card_by_effect(self, player, num_cards, ui_draw, ui_set_text):
        """
        draw num_cards cards triggered by card effect.
        """
        for _ in range(num_cards):
            if self.decks[player] == [] or len(self.hands[player]) >= 9:
                return
            drawn_card = self.decks[player].pop()
            self.hands[player].append(drawn_card)
            if ui_set_text:
                self.text_box.append_html_text(f"プレイヤー{player}がカード{drawn_card}引いたのじゃ。\n")
        if ui_draw:
            self.draw_hand_ui(player)
            self.draw_deck_ui(player)

    def play_card(self, player: int, card: shcg_core_cards.Card, ui_draw, ui_set_text, additional_targets: list[shcg_core_cards.Card] | None,
                  is_ai_player: bool, effect_choice: str | None,
                  additional_multi_targets: list[shcg_core_cards.Card] | None = None):
        if len(self.fields[player]) > 4 and not isinstance(card, shcg_core_cards.Spell):
            raise shcg_core_error.FlowError("Cannot play more than 5 followers/amulets on the field.")
        if self.foxtail[player] < card.cost:
            raise shcg_core_error.FlowError(f"Not enough foxtail to play {card}. Required: {card.cost}, Available: {self.foxtail[player]}")
        self.use_foxtail(player, card.cost, ui_draw, ui_set_text)
        self.hands[player].remove(card)

        targets = None
        multi_targets = None
        player_prefix = "AI" if is_ai_player else ""

        if card.request_card_selection_on_play:
            targets = additional_targets
            if ui_set_text and targets:
                targets_str = ", ".join(str(t) for t in targets)
                self.text_box.append_html_text(f"{player_prefix}プレイヤー{player}が{card}をプレイする時に{targets_str}を選択したのじゃ。\n")

        if card.request_multi_card_selection_on_play[0]:
            multi_targets = additional_multi_targets
            if ui_set_text and multi_targets:
                targets_str = ", ".join(str(t) for t in multi_targets)
                self.text_box.append_html_text(f"{player_prefix}プレイヤー{player}が{card}をプレイする時に{targets_str}を複数選択したのじゃ。\n")

        if card.request_effect_choose_option:
            if effect_choice is None or effect_choice not in card.request_effect_choose_option:
                raise shcg_core_error.AbilityToReadError(f"Invalid effect choice: {effect_choice}. Must be one of {card.request_effect_choose_option}")
            elif ui_set_text and is_ai_player:
                self.text_box.append_html_text(f"AIプレイヤー{player}が{card}の効果選択として{effect_choice}を選択したのじゃ。\n")
        else:
            effect_choice = None

        if "skip_on_play_effect" in card.extra_effect_list:
            if ui_set_text:
                self.text_box.append_html_text(f"{card}の場に出す効果は発動しなかったのじゃ。\n")
        else:
            card.on_play_effect(self, draw_ui=ui_draw, set_text=ui_set_text,
                                the_actual_textbox=self.text_box,
                                selected_card_for_effect=targets,
                                effect_choice=effect_choice,
                                selected_cards_for_multi_effect=multi_targets)

        if isinstance(card, shcg_core_cards.Follower):
            card.mv([card], "summon", self, draw_ui=ui_draw, set_text=ui_set_text, the_actual_textbox=self.text_box, player=player)
        elif isinstance(card, shcg_core_cards.Spell):
            card.mv([card], "play_spell", self, draw_ui=ui_draw, set_text=ui_set_text, the_actual_textbox=self.text_box, player=player)
        elif isinstance(card, shcg_core_cards.Amulet):
            card.mv([card], "place_amulet", self, draw_ui=ui_draw, set_text=ui_set_text, the_actual_textbox=self.text_box, player=player)
        if ui_draw:
            self.draw_hand_ui(player)
            self.draw_field_ui(player)
            self.draw_field_ui(3 - player)
            self.draw_deck_ui(player)


    def get_valid_attack_targets(self, player: int, follower: shcg_core_cards.Follower) -> list[shcg_core_cards.Follower | str]:
        """
        Given a follower on the field, return a list of valid attack targets.
        Targets can be opponent Followers or "leader".
        Returns empty list if the follower cannot attack.
        """
        if not isinstance(follower, shcg_core_cards.Follower):
            return []
        if follower.attack_ability <= 0 or not follower.can_attack_this_turn:
            return []
        if follower not in self.fields[player]:
            return []

        opponent = 3 - player
        targets: list[shcg_core_cards.Follower | str] = []

        protect_exists = any(c.ability_protect for c in self.fields[opponent] if isinstance(c, shcg_core_cards.Follower))

        if protect_exists:
            for c in self.fields[opponent]:
                if isinstance(c, shcg_core_cards.Follower) and c.ability_protect:
                    targets.append(c)
        else:
            for c in self.fields[opponent]:
                if isinstance(c, shcg_core_cards.Follower):
                    targets.append(c)
            if follower.attack_ability >= 2:
                targets.append("leader")

        return targets


    def follower_attack(self, player, attacker: shcg_core_cards.Follower, target: shcg_core_cards.Follower | str, ui_draw, ui_set_text):
        if attacker.attack_ability <= 0:
            raise shcg_core_error.FlowError(f"{attacker} cannot attack because it has no attack ability.")
        if not attacker.can_attack_this_turn:
            raise shcg_core_error.FlowError(f"{attacker} cannot attack this turn.")
        if not isinstance(attacker, shcg_core_cards.Follower):
            raise shcg_core_error.FlowError(f"{attacker} is not a follower and cannot attack.")
        if attacker not in self.fields[player]:
            raise shcg_core_error.FlowError(f"{attacker} is not on the field and cannot attack.")
        # check protect ability
        protect_exists = any([c.ability_protect for c in self.fields[self.opponent] if isinstance(c, shcg_core_cards.Follower)])

        # attacker before attack effect
        attacker.before_attack_effect(self, ui_draw, ui_set_text, self.text_box, target)

        if isinstance(target, shcg_core_cards.Follower):
            if target not in self.fields[self.opponent]:
                raise shcg_core_error.FlowError(f"{target} is not on the field and cannot be attacked.")
            if not target.ability_protect and protect_exists:
                raise shcg_core_error.FlowError(f"Cannot attack {target} because there is a follower with protect ability on opponent's field.")
            if ui_set_text:
                # self.text_box.append_html_text(f"{attacker} is about to attack {target}.\n")
                self.text_box.append_html_text(f"{attacker}は{target}を攻撃するぞ！\n")
            target_hp_before = target.hp
            target.take_damage(attacker.attack, self, ui_draw, ui_set_text, self.text_box, attacker=attacker, is_battle_damage=True)
            target_hp_changed = target_hp_before - target.hp
            # drain ability
            if attacker.ability_drain and target_hp_changed > 0:
                self.player_heal(player, target_hp_changed, ui_draw, ui_set_text)
            attacker.take_damage(target.attack, self, ui_draw, ui_set_text, self.text_box, attacker=target, is_battle_damage=True)
            # Remove dead followers handled in take_damage method
            attacker.after_attack_effect()
            if ui_draw:
                self.draw_field_ui(1)
                self.draw_field_ui(2)
        elif target == "leader":
            if attacker.attack_ability < 2:
                raise shcg_core_error.FlowError(f"{attacker} cannot attack leader because its attack ability is less than 2.")
            if protect_exists:
                raise shcg_core_error.FlowError(f"Cannot attack leader because there is a follower with protect ability on opponent's field.")
            if ui_set_text:
                self.text_box.append_html_text(f"{attacker}の直接攻撃！\n")
            self.player_take_damage(self.opponent, attacker.attack, ui_draw, ui_set_text, is_follower_attack=True)
            # drain ability
            if attacker.ability_drain and attacker.attack > 0:
                self.player_heal(player, attacker.attack, ui_draw, ui_set_text)
            attacker.after_attack_effect()
            if ui_draw:
                self.draw_field_ui(player)
        else:
            raise Exception("Should not reach here.")


    def player_take_damage(self, player: int, amount: int, ui_draw: bool, ui_set_text: bool, is_follower_attack: bool=False) -> bool:
        if amount < 0:
            raise shcg_core_error.FlowError("Damage amount cannot be negative.")
        # has 神弓の座天使・リリエル on field, no effect damage taken
        if not is_follower_attack:
            for c in self.fields[player]:
                if isinstance(c, shcg_core_cards.神弓の座天使リリエル):
                    if ui_set_text:
                        self.text_box.append_html_text(f"プレイヤー{player}は神弓の座天使・リリエルの効果で能力によるダメージを受けなかったのじゃ。\n")
                    return False
        self.hp[player] -= amount
        if ui_set_text:
            self.text_box.append_html_text(f"プレイヤー{player}が{amount}のダメージを受けたのじゃ。残りHP:{self.hp[player]}。\n")
        if amount > 0 and ui_draw:
            self.draw_player_hp_ui()
        if self.hp[player] <= 0:
            winner = 3 - player
            if ui_set_text:
                self.text_box.append_html_text(f"プレイヤー{winner}の勝利じゃ！\n")
            self.concluded = True
            self.winner = winner
            return True
        return False

    def player_heal(self, player: int, amount: int, ui_draw, ui_set_text) -> None:
        """
        Heal leader, but not exceeding max HP.
        """
        if amount < 0:
            raise shcg_core_error.FlowError("Heal amount cannot be negative.")
        prev_hp = self.hp[player]
        self.hp[player] = min(self.hp[player] + amount, self.max_hp[player])
        if ui_set_text:
            self.text_box.append_html_text(f"プレイヤー{player}が{self.hp[player] - prev_hp}のHPを回復したのじゃ。現在のHP:{self.hp[player]}。\n")
        if amount > 0 and ui_draw:
            self.draw_player_hp_ui()


    def compute_state_hash(self) -> tuple:
        """
        Fast hashable representation of the game state for AI deduplication.

        Returns a nested tuple of primitives that Python can hash natively —
        no JSON serialisation, no hashlib, no string allocation.

        Zone ordering rules:
          - fields / hands / graveyard / banished / hidden_cards: sorted (card order
            is irrelevant for state identity).
          - decks: order preserved (top card determines the next draw).
        """
        def card_key(card) -> tuple:
            return (
                type(card).__name__,
                getattr(card, 'hp', None), # non-followers have hp of None to distinguish them
                getattr(card, 'max_hp', None),
                getattr(card, 'attack', None),
                getattr(card, 'is_enhanced', None),
                getattr(card, 'can_attack_this_turn', None),
                getattr(card, 'ability_rush', None),
                getattr(card, 'ability_super_rush', None),
                getattr(card, 'ability_protect', None),
                getattr(card, 'ability_drain', None),
                getattr(card, 'ability_lethal', None),
                getattr(card, 'cost', None),
                getattr(card, 'original_cost', None),
                getattr(card, 'counter', None),
                getattr(card, 'counter_max', None),
            )

        def zone_key(card_list, ordered: bool = False) -> tuple:
            keys = [card_key(c) for c in card_list]
            return tuple(sorted(keys) if not ordered else keys)

        return (
            zone_key(self.fields[1]),           zone_key(self.fields[2]),
            zone_key(self.hands[1]),            zone_key(self.hands[2]),
            zone_key(self.decks[1], ordered=True), zone_key(self.decks[2], ordered=True),
            zone_key(self.graveyard[1]),        zone_key(self.graveyard[2]),
            zone_key(self.banished[1]),         zone_key(self.banished[2]),
            zone_key(self.hidden_cards[1]),     zone_key(self.hidden_cards[2]),
            self.hp[1], self.hp[2],
            self.max_hp[1], self.max_hp[2],
            self.enhance_used_this_turn[1], self.enhance_used_this_turn[2],
            self.amount_card_generated_from_void[1], self.amount_card_generated_from_void[2],
        )

    def serialize_to_string(self) -> str:
        """Serialize the entire game state to a JSON string. Can be restored with load_from_string."""
        def serialize_zone(card_list):
            return [shcg_core_cards.serialize_card(c) for c in card_list]

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
    def load_from_string(s: str):
        """Restore a GameStateSnapshot from a JSON string produced by serialize_to_string."""
        data = json.loads(s)

        def deserialize_zone(card_dicts):
            return [shcg_core_cards.deserialize_card(d) for d in card_dicts]

        snap = SHCGGameState.__new__(SHCGGameState)
        snap.top_of_the_deck_ui_marker = {1: None, 2: None}
        snap.all_ui_components_to_none()
        snap.deep_dark_blue = None
        snap.decks = {1: [], 2: []}
        snap.hands = {1: [], 2: []}
        snap.fields = {1: [], 2: []}
        snap.hidden_cards = {1: [], 2: []}
        snap.graveyard = {1: [], 2: []}
        snap.banished = {1: [], 2: []}
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

    def redraw_all_ui(self):
        """Redraw all UI elements to reflect current game state."""
        self.draw_player_hp_ui()
        self.draw_tail_ui(1)
        self.draw_tail_ui(2)
        self.draw_hand_ui(1)
        self.draw_hand_ui(2)
        self.draw_deck_ui(1)
        self.draw_deck_ui(2)
        self.draw_field_ui(1)
        self.draw_field_ui(2)
        self.draw_current_player_indicator()

    def end_turn(self, ui_draw, ui_set_text):
        if self.concluded:
            if ui_set_text:
                self.text_box.append_html_text("ゲームは終了したのじゃ。新しいゲームを始めようではないか。\n")
            return
        for c in self.fields[self.current_player].copy():
            c.end_of_turn_on_field_effect(self, ui_draw, ui_set_text, self.text_box)
            if "end_of_turn_destroy" in c.extra_effect_list and c in self.fields[self.current_player]:
                c.mv(self.fields[self.current_player], "destroy", self, draw_ui=ui_draw, set_text=ui_set_text, the_actual_textbox=self.text_box, player=self.current_player)
        if self.concluded:
            if ui_draw:
                self.redraw_all_ui()
            return
        self.current_player = self.opponent
        self.foxtail[self.current_player] = 9
        for card in self.fields[self.current_player].copy():
            card.start_of_turn_on_field_effect(self, ui_draw, ui_set_text, self.text_box)
        for card in itertools.chain(self.hands[self.current_player].copy(), self.graveyard[self.current_player].copy(), 
                                    self.banished[self.current_player].copy(), self.decks[self.current_player].copy()):
            card.start_of_turn_not_on_field_effect(self, ui_draw, ui_set_text, self.text_box)
        self.turn += 1
        self.enhance_used_this_turn = {1: 0, 2: 0}
        if self.concluded:
            if ui_draw:
                self.redraw_all_ui()
            return
        # If both players have no cards in deck, the game ends in a draw
        if self.decks[1] == [] and self.decks[2] == []:
            self.concluded = True
            self.winner = None
            if ui_set_text:
                self.text_box.append_html_text("引き分けじゃ。\n")
            if ui_draw:
                self.redraw_all_ui()
            return
        if ui_draw:
            self.redraw_all_ui()
        if ui_set_text:
            self.text_box.append_html_text("======================================\n")
            self.text_box.append_html_text(f"プレイヤー{self.current_player}のターンじゃ。\n")
            self.text_box.append_html_text(f"ターン{self.turn}。\n")


    def use_foxtail(self, player, amount, ui_draw, ui_set_text):
        # The player use this amount of foxtail
        assert amount >= 0
        assert amount <= 9
        if amount == 0:
            return
        foxtail_prev = self.foxtail[player]
        if self.foxtail[player] >= amount:
            self.foxtail[player] -= amount
            if ui_draw:
                for i in range(self.foxtail[player], foxtail_prev):
                    self.global_vars_tail_indicators[player][i].set_image(self.image_others["405"])
                    self.global_vars_tail_indicators_active[player].remove(self.global_vars_tail_indicators[player][i])
        else:
            raise shcg_core_error.FlowError(f"Player {player} does not have enough foxtail to use {amount}. Current foxtail: {self.foxtail[player]}")


    def add_foxtail(self, player, amount, ui_draw, ui_set_text):
        # add amount of foxtail for player
        assert amount >= 0
        if amount == 0:
            return
        foxtail_prev = self.foxtail[player]
        self.foxtail[player] = min(9, self.foxtail[player] + amount)

        if ui_draw:
            for i in range(foxtail_prev, self.foxtail[player]):
                self.global_vars_tail_indicators[player][i].set_image(self.image_others["foxtail"])
                self.global_vars_tail_indicators_active[player].append(self.global_vars_tail_indicators[player][i])


    def on_card_enhanced(self, player, card_to_enhance: shcg_core_cards.Follower, additional_targets: list[shcg_core_cards.Card] | None, is_ai_player: bool, ui_set_text,
                         ui_draw, effect_choice: str | None = None,
                         additional_multi_targets: list[shcg_core_cards.Card] | None = None):
        # not having foxtail will return early
        assert self.foxtail[player] > 0
        if self.foxtail[player] < 1:
            return
        if self.enhance_used_this_turn[player] >= self.max_enhance_allowed_per_turn[player]:
            return
        if not hasattr(card_to_enhance, 'can_enhance') or not card_to_enhance.can_enhance:
            return
        if card_to_enhance not in self.fields[player]:
            return
        if ui_set_text:
            self.text_box.append_html_text(f"プレイヤー{player}が{card_to_enhance}を強化するぞ！\n")

        targets = None
        multi_targets = None

        prefix = "AI" if is_ai_player else ""
        if card_to_enhance.request_card_selection_on_enhance:
            targets = additional_targets
            if ui_set_text and targets:
                targets_str = ",".join(str(t) for t in targets)
                self.text_box.append_html_text(f"{prefix}プレイヤー{player}が{card_to_enhance}を強化する時に{targets_str}を選択したのじゃ。\n")

        if card_to_enhance.request_multi_card_selection_on_enhance[0]:
            multi_targets = additional_multi_targets
            if ui_set_text and multi_targets:
                targets_str = ",".join(str(t) for t in multi_targets)
                self.text_box.append_html_text(f"{prefix}プレイヤー{player}が{card_to_enhance}を強化する時に{targets_str}を複数選択したのじゃ。\n")

        card_to_enhance.on_enhance_effect(self, draw_ui=ui_draw, set_text=ui_set_text,
                                            the_actual_textbox=self.text_box,
                                            selected_card_for_effect=targets,
                                            effect_choice=effect_choice,
                                            selected_cards_for_multi_effect=multi_targets)

        self.enhance_used_this_turn[player] += 1
        self.use_foxtail(player, 1, ui_draw=ui_draw, ui_set_text=ui_set_text)
        if ui_draw:
            self.draw_field_ui(player)
            self.draw_field_ui(3 - player)
            self.draw_hand_ui(player)
            self.draw_hand_ui(3 - player)


    def draw_deck_ui(self, player):
        if self.global_vars_deck_slots[player]:
            for card_ui in self.global_vars_deck_slots[player]:
                card_ui.kill()
        deck = self.decks[player]
        if not deck:
            return
        if player == 1: # 'top'
            base_x = 1500 - 100 - 50
            base_y = 50
        else:  # 'bottom'
            base_x = 1500 - 100 - 50
            base_y = 900 - 145 - 50
        deck_tooltip_str = " | ".join([f"{i + 1}: {str(card)}" for i, card in enumerate(deck)])
        for i in range(len(deck)):
            offset = i * 1
            card_ui = pygame_gui.elements.UIImage(
                pygame.Rect((base_x + offset, base_y + offset), (100, 145)),
                pygame.Surface((100, 145)),
                self.ui_manager
            )
            card_ui.set_image(self.draw_card_image_func(deck[i]))
            self.global_vars_deck_slots[player].append(card_ui)
            if i == len(deck) - 1:
                self.top_of_the_deck_ui_marker[player] = card_ui
                card_ui.set_tooltip(deck_tooltip_str, delay=0.1, wrap_width=600)
        return


    def draw_hand_ui(self, player):
        self.hands[player] = sorted(self.hands[player], key=lambda x: x.cost)
        hand = self.hands[player]
        slots = self.global_vars_hand_slots[player]
        for i in range(9):
            if i < len(hand):
                slots[i].set_image(self.draw_card_image_func(hand[i]))
                # some accessbility tooltip for some cards
                if isinstance(hand[i], shcg_core_cards.次元の魔女ドロシー):
                    # show num of spell in graveyard
                    num_spells_in_graveyard = sum(1 for c in self.graveyard[player] if isinstance(c, shcg_core_cards.Spell))
                    hand[i].extra_tooltip_str = f"墓地にあるスペルの枚数: {num_spells_in_graveyard}"
                slots[i].set_tooltip(hand[i].tooltip_str(), delay=0.1, wrap_width=300)
            else:
                slots[i].set_image(self.image_405_card_slot)
                slots[i].set_tooltip("", delay=0.1, wrap_width=300)
        return


    def draw_field_ui(self, player):
        self.fields[player] = sorted(self.fields[player], key=lambda x: x.cost)
        field = self.fields[player]
        slots = self.global_vars_field_slots[player]
        for i in range(5):
            if i < len(field):
                slots[i].set_image(self.draw_card_image_func(field[i], show_attack_status_indicator=True))
                slots[i].set_tooltip(field[i].tooltip_str(), delay=0.1, wrap_width=300)
            else:
                slots[i].set_image(self.image_405_card_slot)
                slots[i].set_tooltip("", delay=0.1, wrap_width=300)
        return


    def draw_tail_ui(self, player):
        # fill tail indicators to default value (9) according to foxtail count
        foxtail = self.foxtail[player]
        indicators = self.global_vars_tail_indicators[player]
        for i in range(9):
            if i < foxtail:
                indicators[i].set_image(self.image_others["foxtail"])  # filled
                self.global_vars_tail_indicators_active[player].append(indicators[i])
            else:
                indicators[i].set_image(self.image_others["405"])  # empty
        return


    def draw_player_hp_ui(self):
        # draw player hp on player_1_hp_slot and player_2_hp_slot
        # green text, bold font
        font_bold = pygame.font.Font(None, 64)
        
        # player 1
        hp_text_1 = str(self.hp[1])
        image_with_hp_1 = self.image_others["405"].copy()
        hp_render_1 = font_bold.render(hp_text_1, True, self.deep_dark_blue)
        
        # transform size of image_with_hp_1 to fit the player_1_hp_slot
        x = self.player_1_hp_slot.get_relative_rect().width
        y = self.player_1_hp_slot.get_relative_rect().height
        image_with_hp_1 = pygame.transform.scale(image_with_hp_1, (x, y))
        text_rect_1 = hp_render_1.get_rect(center=(x//2, y//2))
        image_with_hp_1.blit(hp_render_1, text_rect_1)
        self.player_1_hp_slot.set_image(image_with_hp_1)
        
        # player 2
        hp_text_2 = str(self.hp[2])
        image_with_hp_2 = self.image_others["405"].copy()
        hp_render_2 = font_bold.render(hp_text_2, True, self.deep_dark_blue)
        
        # transform size of image_with_hp_2 to fit the player_2_hp_slot
        x = self.player_2_hp_slot.get_relative_rect().width
        y = self.player_2_hp_slot.get_relative_rect().height
        image_with_hp_2 = pygame.transform.scale(image_with_hp_2, (x, y))
        text_rect_2 = hp_render_2.get_rect(center=(x//2, y//2))
        image_with_hp_2.blit(hp_render_2, text_rect_2)
        self.player_2_hp_slot.set_image(image_with_hp_2)

    def draw_current_player_indicator(self):
        # draw an indicator on the current player's leader image slot
        # deep dark blue border with width 5
        for player in [1, 2]:
            if player == self.current_player:
                border_width = 5
            else:
                border_width = 0

            slot = self.leader_slots[player][0]
            slot_width = slot.get_relative_rect().width
            slot_height = slot.get_relative_rect().height

            leader_img_key = str(player)
            if leader_img_key in self.image_leader:
                leader_image = self.image_leader[leader_img_key]
            else:
                leader_image = self.image_others["404coyote"]

            image_with_indicator = pygame.transform.scale(leader_image, (slot_width, slot_height))
            if border_width > 0:
                pygame.draw.rect(
                    image_with_indicator,
                    self.deep_dark_blue,
                    pygame.Rect(0, 0, slot_width, slot_height),
                    border_width,
                )
            slot.set_image(image_with_indicator)
