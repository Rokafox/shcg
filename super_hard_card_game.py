import os
import json
import more_itertools as mit
import itertools
import pygame, pygame_gui
import cards
import random
import ai_player_new


pygame.init()
clock = pygame.time.Clock()

# ====================================
# Game State
# ====================================

DEFAULT_HP_F = 20
DEFAULT_HP_S = 26

class SHCGGameState:
    def __init__(self, current_player):
        self.current_player = current_player  # 1 or 2
        self.turn = 1
        self.concluded = False
        self.decks: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.hands: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.fields: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.max_hp = {1: DEFAULT_HP_S, 2: DEFAULT_HP_F}
        self.hp = {1: DEFAULT_HP_S, 2: DEFAULT_HP_F}
        self.foxtail = {1: 9, 2: 9}
        self.enhance_used_this_turn = {1: 0, 2: 0}
        self.max_enhance_allowed_per_turn = {1: 1, 2: 1}
        # Every time a card is generated, the player who generated it gets 1 count
        self.amount_card_generated_from_void: dict[int, int] = {1: 0, 2: 0}
        # hidden card
        self.hidden_cards: dict[int, list[cards.Card]] = {1: [], 2: []}
        # graveyard and banished zones
        self.graveyard: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.banished: dict[int, list[cards.Card]] = {1: [], 2: []}
        # ui
        self.top_of_the_deck_ui_marker: dict[int, pygame_gui.elements.UIImage | None] = {1: None, 2: None}
    
    @property
    def opponent(self):
        return 3 - self.current_player

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
            text_box.append_html_text(f"プレイヤー{player}がカード{drawn_card}引いたのじゃ。\n")
        if ui_draw:
            self.draw_hand_ui(player)
            # draw_deck_ui is unnecessary as it is handled by pygame event


    def play_card(self, player: int, card: cards.Card, ui_draw, ui_set_text, additional_target: cards.Card | None,
                  is_ai_player: bool, effect_choice: str | None):
        global text_box
        if len(self.fields[player]) > 4 and card.type != 'spell':
            return
        if self.foxtail[player] < card.cost:
            return
        self.use_foxtail(player, card.cost, ui_draw, ui_set_text)
        self.hands[player].remove(card)
        if ui_set_text:
            text_box.append_html_text(f"プレイヤー{player}が{card}をプレイしたぞ！\n")
        if card.request_card_selection_on_play:
            target = additional_target
            if ui_set_text and target is not None:
                prefix = "AI" if is_ai_player else ""
                text_box.append_html_text(f"{prefix}プレイヤー{player}が{card}をプレイする時に{target}を選択したのじゃ。\n")
        else:
            target = None

        if card.request_effect_choose_option:
            if effect_choice is None or effect_choice not in card.request_effect_choose_option:
                if ui_set_text:
                    text_box.append_html_text(f"プレイヤー{player}の選択は無効じゃった。ランダムに選ぶのじゃ。\n")
                effect_choice = random.choice(card.request_effect_choose_option)
            elif ui_set_text and is_ai_player:
                text_box.append_html_text(f"AIプレイヤー{player}が{card}の効果選択として{effect_choice}を選択したのじゃ。\n")
        else:
            effect_choice = None

        card.on_play_effect(self, draw_ui=ui_draw, set_text=ui_set_text,
                                the_actual_textbox=text_box,
                                selected_card_for_effect=target,
                                effect_choice=effect_choice)
        if isinstance(card, cards.Follower):
            self.fields[player].append(card)
            card.on_summon_effect()
        elif isinstance(card, cards.Spell):
            self.graveyard[player].append(card)
            # if has star pheonix in graveyard, summon it.
            if self.graveyard[player]:
                for c in self.graveyard[player].copy():
                    if isinstance(c, cards.スターフェニックス):
                        if len(self.fields[player]) > 4:
                            break
                        # create a new instance of star pheonix with same unique_id and void_id
                        new_star_pheonix = cards.スターフェニックス()
                        new_star_pheonix.unique_id = c.unique_id
                        new_star_pheonix.void_id = c.void_id
                        self.fields[player].append(new_star_pheonix)
                        self.graveyard[player].remove(c)
                        if ui_set_text:
                            text_box.append_html_text(f"プレイヤー{player}のスターフェニックスが墓場から場に出たのじゃ！\n")
        elif isinstance(card, cards.Amulet):
            self.fields[player].append(card)
        if ui_draw:
            self.draw_hand_ui(player)
            self.draw_field_ui(player)
            self.draw_field_ui(3 - player)
            self.draw_deck_ui(player)


    def follower_attack(self, player, attacker: cards.Follower, target: cards.Follower | str, ui_draw, ui_set_text):
        assert attacker.attack_ability > 0, "This follower cannot attack."
        assert attacker.can_attack_this_turn == True, "This follower cannot attack this turn."
        assert attacker.type == 'follower', "Attacker must be a follower."
        assert attacker in self.fields[player], "Attacker is not on the field."
        if isinstance(target, cards.Follower):
            assert target in self.fields[self.opponent], "Target follower is not on opponent's field."
            if ui_set_text:
                # text_box.append_html_text(f"{attacker} is about to attack {target}.\n")
                text_box.append_html_text(f"{attacker}は{target}を攻撃するぞ！\n")
            target_hp_before = target.hp
            target.take_damage(attacker.attack, self, ui_draw, ui_set_text, text_box, attacker=attacker, is_battle_damage=True)
            target_hp_changed = target_hp_before - target.hp
            # drain ability
            if attacker.ability_drain and target_hp_changed > 0:
                self.player_heal(player, target_hp_changed, ui_draw, ui_set_text)
            attacker.take_damage(target.attack, self, ui_draw, ui_set_text, text_box, attacker=target, is_battle_damage=True)
            # Remove dead followers handled in take_damage method
            attacker.after_attack_effect()
            if ui_draw:
                self.draw_field_ui(1)
                self.draw_field_ui(2)
        elif target == "leader":
            if ui_set_text:
                text_box.append_html_text(f"{attacker}の直接攻撃！\n")
            self.player_take_damage(self.opponent, attacker.attack, ui_draw, ui_set_text, is_follower_attack=True)
            # drain ability
            if attacker.ability_drain and attacker.attack > 0:
                self.player_heal(player, attacker.attack, ui_draw, ui_set_text)
            attacker.after_attack_effect()
            self.draw_field_ui(player)
        else:
            raise Exception("Should not reach here.")


    def player_take_damage(self, player: int, amount: int, ui_draw: bool, ui_set_text: bool, is_follower_attack: bool=False) -> bool:
        assert amount >= 0
        # has 神弓の座天使・リリエル on field, no effect damage taken
        if not is_follower_attack:
            for c in self.fields[player]:
                if isinstance(c, cards.神弓の座天使リリエル):
                    if ui_set_text:
                        text_box.append_html_text(f"プレイヤー{player}は神弓の座天使・リリエルの効果で能力によるダメージを受けなかったのじゃ。\n")
                    return False
        self.hp[player] -= amount
        if ui_set_text:
            text_box.append_html_text(f"プレイヤー{player}が{amount}のダメージを受けたのじゃ。残りHP:{self.hp[player]}。\n")
        if amount > 0 and ui_draw:
            self.draw_player_hp_ui()
        if self.hp[player] <= 0:
            winner = 3 - player
            if ui_set_text:
                text_box.append_html_text(f"プレイヤー{winner}の勝利じゃ！\n")
            self.concluded = True
            return True
        return False

    def player_heal(self, player: int, amount: int, ui_draw, ui_set_text) -> None:
        """
        Heal leader, but not exceeding max HP.
        """
        assert amount >= 0
        prev_hp = self.hp[player]
        self.hp[player] = min(self.hp[player] + amount, self.max_hp[player])
        if ui_set_text:
            text_box.append_html_text(f"プレイヤー{player}が{self.hp[player] - prev_hp}のHPを回復したのじゃ。現在のHP:{self.hp[player]}。\n")
        if amount > 0 and ui_draw:
            self.draw_player_hp_ui()


    def end_turn(self, ui_draw, ui_set_text):
        for c in self.fields[self.current_player].copy():
            c.end_of_turn_on_field_effect(self, ui_draw, ui_set_text, text_box)
        if self.concluded:
            # text_box.append_html_text("The game has concluded. Start a new game instead.\n")
            text_box.append_html_text("ゲームは終了したのじゃ。新しいゲームを始めようではないか。\n")
            return
        self.current_player = self.opponent
        self.foxtail[self.current_player] = 9
        for card in self.fields[self.current_player]:
            card.start_of_turn_on_field_effect(self.current_player)
        self.turn += 1
        self.enhance_used_this_turn = {1: 0, 2: 0}
        # If both players have no cards in deck, the game ends in a draw
        if self.decks[1] == [] and self.decks[2] == []:
            self.concluded = True
            if ui_set_text:
                text_box.append_html_text("引き分けじゃ。\n")
            return
        if ui_draw:
            self.draw_tail_ui(self.current_player)
            self.draw_field_ui(1)
            self.draw_field_ui(2)
            self.draw_hand_ui(1)
            self.draw_hand_ui(2)
            self.draw_deck_ui(1)
            self.draw_deck_ui(2)
        if ui_set_text:
            text_box.append_html_text(text_box_introduction_text)
            text_box.append_html_text(f"プレイヤー{self.current_player}のターンじゃ。\n")
            text_box.append_html_text(f"ターン{self.turn}。\n")


    def use_foxtail(self, player, amount, ui_draw, ui_set_text):
        # The player use this amount of foxtail
        assert amount >= 0
        assert amount <= 9
        if amount == 0:
            return
        global global_vars_tail_indicators, global_vars_tail_indicators_active
        foxtail_prev = self.foxtail[player]
        if self.foxtail[player] >= amount:
            self.foxtail[player] -= amount
            if ui_draw:
                for i in range(self.foxtail[player], foxtail_prev):
                    global_vars_tail_indicators[player][i].set_image(image_others["405"])
                    global_vars_tail_indicators_active[player].remove(global_vars_tail_indicators[player][i])
        else:
            print(f"Error: Player {player} does not have enough foxtail to use {amount}. Current foxtail: {self.foxtail[player]}")
            raise ValueError("Not enough foxtail")


    def add_foxtail(self, player, amount, ui_draw, ui_set_text):
        # add amount of foxtail for player
        assert amount >= 0
        if amount == 0:
            return
        global global_vars_tail_indicators, global_vars_tail_indicators_active
        foxtail_prev = self.foxtail[player]
        if self.foxtail[player] + amount <= 9:
            self.foxtail[player] += amount
        for i in range(foxtail_prev, self.foxtail[player]):
            global_vars_tail_indicators[player][i].set_image(image_others["foxtail"])
            global_vars_tail_indicators_active[player].append(global_vars_tail_indicators[player][i])
        else:
            self.foxtail[player] = 9
            self.draw_tail_ui(1)

    def on_card_enhanced(self, player, card_to_enhance: cards.Follower, additional_target: cards.Card | None, is_ai_player: bool, ui_set_text,
                         ui_draw):
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
            text_box.append_html_text(f"プレイヤー{player}が{card_to_enhance}を強化するぞ！\n")
        if card_to_enhance.request_card_selection_on_enhance:
            target = additional_target
            if ui_set_text and target is not None:
                prefix = "AI" if is_ai_player else ""
                text_box.append_html_text(f"{prefix}プレイヤー{player}が{card_to_enhance}を強化する時に{target}を選択したのじゃ。\n")
            card_to_enhance.on_enhance_effect(self, draw_ui=ui_draw, set_text=ui_set_text,
                                              the_actual_textbox=text_box,
                                              selected_card_for_effect=target)
        else:
            card_to_enhance.on_enhance_effect(self, draw_ui=ui_draw, set_text=ui_set_text,
                                              the_actual_textbox=text_box,
                                              selected_card_for_effect=None)
        
        global_vars_shcg.enhance_used_this_turn[player] += 1
        global_vars_shcg.use_foxtail(player, 1, ui_draw=True, ui_set_text=True)
        if ui_draw:
            global_vars_shcg.draw_field_ui(player)
            global_vars_shcg.draw_field_ui(3 - player)


    # ====================================
    # UI functions
    # ====================================


    def draw_deck_ui(self, player):
        global global_vars_deck_slots
        if global_vars_deck_slots[player]:
            for card_ui in global_vars_deck_slots[player]:
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
                ui_manager
            )
            card_ui.set_image(draw_card(deck[i]))
            global_vars_deck_slots[player].append(card_ui)
            if i == len(deck) - 1:
                self.top_of_the_deck_ui_marker[player] = card_ui
                card_ui.set_tooltip(deck_tooltip_str, delay=0.1, wrap_width=600)
        return


    def draw_hand_ui(self, player):
        self.hands[player] = sorted(self.hands[player], key=lambda x: x.cost)
        hand = self.hands[player]
        global global_vars_hand_slots
        slots = global_vars_hand_slots[player]
        for i in range(9):
            if i < len(hand):
                slots[i].set_image(draw_card(hand[i]))
                slots[i].set_tooltip(hand[i].tooltip_str(), delay=0.1, wrap_width=300)
            else:
                slots[i].set_image(image_405_card_slot)
                slots[i].set_tooltip("", delay=0.1, wrap_width=300)
        return


    def draw_field_ui(self, player):
        self.fields[player] = sorted(self.fields[player], key=lambda x: x.cost)
        field = self.fields[player]
        global global_vars_field_slots
        slots = global_vars_field_slots[player]
        for i in range(5):
            if i < len(field):
                slots[i].set_image(draw_card(field[i], show_attack_status_indicator=True))
                slots[i].set_tooltip(field[i].tooltip_str(), delay=0.1, wrap_width=300)
            else:
                slots[i].set_image(image_405_card_slot)
                slots[i].set_tooltip("", delay=0.1, wrap_width=300)
        return


    def draw_tail_ui(self, player):
        # fill tail indicators to default value (9) according to foxtail count
        foxtail = self.foxtail[player]
        global global_vars_tail_indicators, global_vars_tail_indicators_active
        indicators = global_vars_tail_indicators[player]
        for i in range(9):
            if i < foxtail:
                indicators[i].set_image(image_others["foxtail"])  # filled
                global_vars_tail_indicators_active[player].append(indicators[i])
            else:
                indicators[i].set_image(image_others["405"])  # empty
        return


    def draw_player_hp_ui(self):
        # draw player hp on player_1_hp_slot and player_2_hp_slot
        # green text, bold font
        font_bold = pygame.font.Font(None, 64)
        
        # player 1
        hp_text_1 = str(self.hp[1])
        image_with_hp_1 = image_others["405"].copy()
        hp_render_1 = font_bold.render(hp_text_1, True, (0, 255, 0))
        
        # transform size of image_with_hp_1 to fit the player_1_hp_slot
        x = player_1_hp_slot.get_relative_rect().width
        y = player_1_hp_slot.get_relative_rect().height
        image_with_hp_1 = pygame.transform.scale(image_with_hp_1, (x, y))
        text_rect_1 = hp_render_1.get_rect(center=(x//2, y//2))
        image_with_hp_1.blit(hp_render_1, text_rect_1)
        player_1_hp_slot.set_image(image_with_hp_1)
        
        # player 2
        hp_text_2 = str(self.hp[2])
        image_with_hp_2 = image_others["405"].copy()
        hp_render_2 = font_bold.render(hp_text_2, True, (0, 255, 0))
        
        # transform size of image_with_hp_2 to fit the player_2_hp_slot
        x = player_2_hp_slot.get_relative_rect().width
        y = player_2_hp_slot.get_relative_rect().height
        image_with_hp_2 = pygame.transform.scale(image_with_hp_2, (x, y))
        text_rect_2 = hp_render_2.get_rect(center=(x//2, y//2))
        image_with_hp_2.blit(hp_render_2, text_rect_2)
        player_2_hp_slot.set_image(image_with_hp_2)


# =====================================
# Load Images
# =====================================

if not os.path.exists("./image"):
    os.mkdir("./image")
if not os.path.exists("./image/cards"):
    os.mkdir("./image/cards")
if not os.path.exists("./image/leader"):
    os.mkdir("./image/leader")
if not os.path.exists("./image/others"):
    os.mkdir("./image/others")

image_files_cards = [x[:-4] for x in os.listdir("./image/cards") if x.endswith((".jpg", ".png"))]
image_files_leader = [x[:-4] for x in os.listdir("./image/leader") if x.endswith((".jpg", ".png"))]
image_files_others = [x[:-4] for x in os.listdir("./image/others") if x.endswith((".jpg", ".png"))]
image_cards: dict[str, pygame.Surface] = {}
image_leader: dict[str, pygame.Surface] = {}
image_others: dict[str, pygame.Surface] = {}

for _ in image_files_cards:
    image_path_jpg = f"image/cards/{_}.jpg"
    image_path_png = f"image/cards/{_}.png"
    if os.path.exists(image_path_jpg):
        image_cards[_] = pygame.image.load(image_path_jpg)
    elif os.path.exists(image_path_png):
        image_cards[_] = pygame.image.load(image_path_png)

for _ in image_files_leader:
    image_path_jpg = f"image/leader/{_}.jpg"
    image_path_png = f"image/leader/{_}.png"
    if os.path.exists(image_path_jpg):
        image_leader[_] = pygame.image.load(image_path_jpg)
    elif os.path.exists(image_path_png):
        image_leader[_] = pygame.image.load(image_path_png)

for _ in image_files_others:
    image_path_jpg = f"image/others/{_}.jpg"
    image_path_png = f"image/others/{_}.png"
    if os.path.exists(image_path_jpg):
        image_others[_] = pygame.image.load(image_path_jpg)
    elif os.path.exists(image_path_png):
        image_others[_] = pygame.image.load(image_path_png)

# NOTE:
# a special image image_others["405"] is full transparent to represent no image
# image_others["404coyote"] is a placeholder image for missing images




# =====================================
# End of Loading Images
# =====================================
# Color and UI Managers
# =====================================

antique_white = pygame.Color("#FAEBD7")
deep_dark_blue = pygame.Color("#000022")
light_yellow = pygame.Color("#FFFFE0")
light_purple = pygame.Color("#f0eaf5")
light_red = pygame.Color("#fbe4e4")
light_green = pygame.Color("#e5fae5")
light_blue = pygame.Color("#e6f3ff")
light_pink = pygame.Color("#fae5eb")

display_surface = pygame.display.set_mode((1600, 900), flags=pygame.SCALED | pygame.RESIZABLE)
ui_manager_lower = pygame_gui.UIManager((1600, 900), "theme_light_yellow.json", starting_language='ja')
ui_manager = pygame_gui.UIManager((1600, 900), "theme_light_yellow.json", starting_language='ja')
ui_manager_overlay = pygame_gui.UIManager((1600, 900), "theme_light_yellow.json", starting_language='ja')

global_vars_theme = "Yellow Theme"

# create a image called 405_card_slot, which is a transparent image of size 100x145, with thin white border
image_405_card_slot = pygame.transform.scale(pygame.Surface((100, 145), pygame.SRCALPHA), (100, 145))
pygame.draw.rect(image_405_card_slot, deep_dark_blue, pygame.Rect(0, 0, 100, 145), 2)


# =====================================
# End of Color and UI Managers
# =====================================
# Example UI Components
# =====================================

global_vars_deck_slots: dict[int, list[pygame_gui.elements.UIImage]] = {1: [], 2: []}

label_leader_1 = pygame_gui.elements.UILabel(pygame.Rect((50, 10), (200, 50)),
                                    "Player 1",
                                    ui_manager)

label_leader_2 = pygame_gui.elements.UILabel(pygame.Rect((50, 900 - 60), (200, 50)),
                                    "Player 2",
                                    ui_manager)

end_turn_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1320, 300), (260, 50)),
                                    text='End Turn',
                                    manager=ui_manager,)



# =====================================
# Card/Effect Selection Window
# =====================================

card_selection_window = None
card_selection_list = None
effect_selection_list = None
card_selection_confirm_button = None
card_selection_cancel_button = None
pending_selection_action = None  # dict with pending play/enhance action info
_card_selection_option_map: dict[str, cards.Card] = {}  # display string -> card object


def _build_card_selection_options(selection_type: str, pending_info: dict) -> list[str]:
    """Build display strings for the card selection list and populate the option map."""
    global _card_selection_option_map
    _card_selection_option_map = {}

    cp = global_vars_shcg.current_player
    op = 3 - cp
    played_card = pending_info.get('card')
    action_type = pending_info.get('type')  # 'play' or 'enhance'

    options: list[str] = []

    if selection_type == "field":
        for i, c in enumerate(global_vars_shcg.fields[cp]):
            if isinstance(c, cards.Follower):
                display = f"{i + 1} {str(c)}"
                options.append(display)
                _card_selection_option_map[display] = c

    elif selection_type == "field_opponent":
        for i, c in enumerate(global_vars_shcg.fields[op]):
            if isinstance(c, cards.Follower):
                display = f"{i + 1} {str(c)}"
                options.append(display)
                _card_selection_option_map[display] = c

    elif selection_type == "field_both":
        for i, c in enumerate(global_vars_shcg.fields[cp]):
            if isinstance(c, cards.Follower):
                display = f"CP {i + 1} {str(c)}"
                options.append(display)
                _card_selection_option_map[display] = c
        for i, c in enumerate(global_vars_shcg.fields[op]):
            if isinstance(c, cards.Follower):
                display = f"OP {i + 1} {str(c)}"
                options.append(display)
                _card_selection_option_map[display] = c

    elif selection_type == "hand":
        for i, c in enumerate(global_vars_shcg.hands[cp]):
            if action_type == 'play' and c is played_card:
                continue
            display = f"{i + 1} {str(c)}"
            options.append(display)
            _card_selection_option_map[display] = c

    elif selection_type == "hand_spell":
        for i, c in enumerate(global_vars_shcg.hands[cp]):
            if action_type == 'play' and c is played_card:
                continue
            if isinstance(c, cards.Spell):
                display = f"{i + 1} {str(c)}"
                options.append(display)
                _card_selection_option_map[display] = c

    elif selection_type == "hand_follower_aiteru":
        hand_after = [c for c in global_vars_shcg.hands[cp] if c is not played_card]
        num_followers = len([c for c in hand_after if c.type == 'follower'])
        for i, c in enumerate(hand_after):
            if c.type == 'follower' and c.cost <= num_followers:
                display = f"{i + 1} {str(c)}"
                options.append(display)
                _card_selection_option_map[display] = c

    elif selection_type == "hand_opponent":
        for i, c in enumerate(global_vars_shcg.hands[op]):
            display = f"{i + 1} {str(c)}"
            options.append(display)
            _card_selection_option_map[display] = c

    return options


def build_card_selection_window(pending_info: dict):
    """Open a window for the player to select a target card and/or effect choice."""
    global card_selection_window, card_selection_list, effect_selection_list
    global card_selection_confirm_button, card_selection_cancel_button
    global pending_selection_action

    pending_selection_action = pending_info

    if card_selection_window:
        card_selection_window.kill()

    card_sel_type = pending_info.get('needs_card_selection', '')
    effect_options = pending_info.get('needs_effect_choice', [])

    # Compute card options
    card_options = []
    if card_sel_type:
        card_options = _build_card_selection_options(card_sel_type, pending_info)

    # Compute window height dynamically
    y_offset = 10
    win_height = 80  # base for buttons + padding
    if card_options:
        win_height += 30 + min(len(card_options) * 25, 200) + 10
    if effect_options:
        win_height += 30 + min(len(effect_options) * 25, 100) + 10
    win_height = max(win_height, 180)

    card_name = str(pending_info['card'])
    action_label = "プレイ" if pending_info['type'] == 'play' else "強化"
    win_title = f"{card_name} - {action_label} 選択"

    card_selection_window = pygame_gui.elements.UIWindow(
        pygame.Rect((500, 200), (420, win_height)),
        ui_manager,
        window_display_title=win_title,
        object_id="#card_selection_window",
        resizable=False
    )

    card_selection_list = None
    effect_selection_list = None

    if card_options:
        pygame_gui.elements.UILabel(
            pygame.Rect((10, y_offset), (380, 25)),
            "ターゲットを選択：",
            ui_manager,
            container=card_selection_window
        )
        y_offset += 30
        list_height = min(len(card_options) * 25, 200)
        card_selection_list = pygame_gui.elements.UISelectionList(
            pygame.Rect((10, y_offset), (380, list_height)),
            card_options,
            ui_manager,
            container=card_selection_window,
            allow_multi_select=False
        )
        y_offset += list_height + 10

    if effect_options:
        pygame_gui.elements.UILabel(
            pygame.Rect((10, y_offset), (380, 25)),
            "効果を選択：",
            ui_manager,
            container=card_selection_window
        )
        y_offset += 30
        list_height = min(len(effect_options) * 25, 100)
        effect_selection_list = pygame_gui.elements.UISelectionList(
            pygame.Rect((10, y_offset), (380, list_height)),
            effect_options,
            ui_manager,
            container=card_selection_window,
            allow_multi_select=False
        )
        y_offset += list_height + 10

    card_selection_cancel_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((10, y_offset), (180, 35)),
        text="キャンセル",
        manager=ui_manager,
        container=card_selection_window,
        object_id="#card_selection_cancel"
    )
    card_selection_confirm_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((210, y_offset), (180, 35)),
        text="確定",
        manager=ui_manager,
        container=card_selection_window,
        object_id="#card_selection_confirm"
    )


def _execute_pending_selection():
    """Read selections from the window and execute the pending play/enhance action."""
    global pending_selection_action, card_selection_window

    if not pending_selection_action:
        return

    info = pending_selection_action
    action_type = info['type']
    player = info['player']
    card = info['card']

    selected_target = None
    selected_effect = None

    card_required = bool(info.get('needs_card_selection'))
    effect_required = bool(info.get('needs_effect_choice'))
    card_ok = not card_required
    effect_ok = not effect_required

    # Read card selection
    if card_required and card_selection_list:
        selected_str = card_selection_list.get_single_selection()
        if selected_str and selected_str in _card_selection_option_map:
            selected_target = _card_selection_option_map[selected_str]
        card_ok = selected_target is not None

    # Read effect choice
    if effect_required and effect_selection_list:
        selected_effect = effect_selection_list.get_single_selection()
        effect_ok = selected_effect is not None

    can_proceed = card_ok and effect_ok

    if can_proceed:
    # Execute action
        if action_type == 'play':
            global_vars_shcg.play_card(player, card, ui_draw=True, ui_set_text=True,
                                    additional_target=selected_target,
                                    is_ai_player=False, effect_choice=selected_effect)
        elif action_type == 'enhance':
            global_vars_shcg.on_card_enhanced(player, card_to_enhance=card,
                                            additional_target=selected_target,
                                            is_ai_player=False,
                                            ui_draw=True, ui_set_text=True)

        # Clean up
        _cancel_pending_selection()
    else:
        return


def _cancel_pending_selection():
    """Cancel any pending selection and close the window."""
    global pending_selection_action, card_selection_window
    global card_selection_list, effect_selection_list
    global card_selection_confirm_button, card_selection_cancel_button
    pending_selection_action = None
    if card_selection_window:
        card_selection_window.kill()
    card_selection_window = None
    card_selection_list = None
    effect_selection_list = None
    card_selection_confirm_button = None
    card_selection_cancel_button = None



settings_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((50, 330), (200, 50)),
                                    text='Settings',
                                    manager=ui_manager,)

new_game_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((50, 390), (200, 50)),
                                    text='New Game',
                                    manager=ui_manager,)

quit_game_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((50, 450), (200, 50)),
                                    text='Quit Game',
                                    manager=ui_manager,)

deck_builder_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((50, 510), (200, 50)),
                                    text='Deck Builder',
                                    manager=ui_manager,)

text_box = pygame_gui.elements.UITextEntryBox(pygame.Rect((895, 255), (410, 345)),"", ui_manager)
text_box_introduction_text = "======================================\n"
text_box.set_text(text_box_introduction_text)


def draw_card(card: cards.Card, show_attack_status_indicator: bool = False, wh: tuple = (200, 290)) -> pygame.Surface:
    width = max(1, int(wh[0]))
    height = max(1, int(wh[1]))
    card_surface = pygame.Surface((width, height))

    base_width = 100
    base_height = 145
    scale_x = width / base_width
    scale_y = height / base_height
    scale_min = min(scale_x, scale_y)

    def sx(x: int) -> int:
        return int(round(x * scale_x))

    def sy(y: int) -> int:
        return int(round(y * scale_y))

    font_size = max(12, int(round(32 * scale_min)))
    font_bold = pygame.font.Font(None, font_size)
    outline_1 = max(1, int(round(1 * scale_min)))
    outline_2 = max(1, int(round(2 * scale_min)))
    outline_offsets = [
        (-outline_1, -outline_1), (-outline_1, outline_1),
        (outline_1, -outline_1), (outline_1, outline_1),
        (-outline_2, 0), (outline_2, 0),
        (0, -outline_2), (0, outline_2),
    ]
    
    # 強化済みカードは別画像を使用
    if hasattr(card, 'is_enhanced') and card.is_enhanced:
        card_image_key = f"{card.name}_e"
        if card_image_key in image_cards:
            scaled_card_img = pygame.transform.scale(image_cards[card_image_key], (width, height))
            card_surface.blit(scaled_card_img, (0, 0))
        else:
            scaled_card_img = pygame.transform.scale(image_others["404coyote"], (width, height))
            card_surface.blit(scaled_card_img, (0, 0))
    elif card.name in image_cards:
        # 通常カード画像
        scaled_card_img = pygame.transform.scale(image_cards[card.name], (width, height))
        card_surface.blit(scaled_card_img, (0, 0))
    else:
        scaled_card_img = pygame.transform.scale(image_others["404coyote"], (width, height))
        card_surface.blit(scaled_card_img, (0, 0))

    cost_text = str(card.cost)
    for dx, dy in outline_offsets:
        cost_outline = font_bold.render(cost_text, True, (0, 0, 0))
        card_surface.blit(cost_outline, (sx(8) + dx, sy(8) + dy))
    cost_render = font_bold.render(cost_text, True, (255, 215, 0))
    card_surface.blit(cost_render, (sx(8), sy(8)))
    
    if card.type == 'follower':
        attack_text = str(card.attack)
        for dx, dy in outline_offsets:
            attack_outline = font_bold.render(attack_text, True, (0, 0, 0))
            card_surface.blit(attack_outline, (sx(8) + dx, sy(120) + dy))
        attack_render = font_bold.render(attack_text, True, (255, 50, 50))
        card_surface.blit(attack_render, (sx(8), sy(120)))
        
        hp_text = str(card.hp)
        hp_width = font_bold.size(hp_text)[0]
        for dx, dy in outline_offsets:
            hp_outline = font_bold.render(hp_text, True, (0, 0, 0))
            card_surface.blit(hp_outline, (sx(92) - hp_width + dx, sy(120) + dy))
        hp_render = font_bold.render(hp_text, True, (50, 255, 50))
        card_surface.blit(hp_render, (sx(92) - hp_width, sy(120)))
    
        if show_attack_status_indicator:  # show can attack status for followers
                if card.attack_ability == 0 or card.can_attack_this_turn == False:
                    # cannot attack, gray
                    indicator_color = (150, 150, 150)
                elif card.attack_ability == 1:
                    # can attack follower, yellow
                    indicator_color = (255, 255, 50)
                elif card.attack_ability == 2:
                    # can attack player, green
                    indicator_color = (50, 255, 50)
                else:
                    raise ValueError(f"Unknown attack ability: {card.attack_ability}")
                # outline the card with the indicator color
                indicator_line_width = max(1, int(round(2 * scale_min)))
                pygame.draw.rect(card_surface, indicator_color, pygame.Rect(0, 0, width, height), indicator_line_width)
    elif card.type == 'spell':
        # draw "S" at bottom left, blue color
        spell_text = "S"
        for dx, dy in outline_offsets:
            spell_outline = font_bold.render(spell_text, True, (0, 0, 0))
            card_surface.blit(spell_outline, (sx(8) + dx, sy(120) + dy))
        spell_render = font_bold.render(spell_text, True, (108, 210, 253))
        card_surface.blit(spell_render, (sx(8), sy(120)))
    elif card.type == 'amulet':
        # draw "A" at bottom left, purple color
        amulet_text = "A"
        for dx, dy in outline_offsets:
            amulet_outline = font_bold.render(amulet_text, True, (0, 0, 0))
            card_surface.blit(amulet_outline, (sx(8) + dx, sy(120) + dy))
        amulet_render = font_bold.render(amulet_text, True, (231, 130, 242))
        card_surface.blit(amulet_render, (sx(8), sy(120)))
        # draw counter, if any on bottom right
        if hasattr(card, 'counter'):
            counter_text = str(card.counter)
            counter_width = font_bold.size(counter_text)[0]
            for dx, dy in outline_offsets:
                counter_outline = font_bold.render(counter_text, True, (0, 0, 0))
                card_surface.blit(counter_outline, (sx(92) - counter_width + dx, sy(120) + dy))
            counter_render = font_bold.render(counter_text, True, (231, 130, 242))
            card_surface.blit(counter_render, (sx(92) - counter_width, sy(120)))
    
    # 強化可能マーカーを右上に表示
    if hasattr(card, 'can_enhance') and card.can_enhance:
        # foxtail_img = pygame.transform.scale(image_others["foxtail"], (24, 24))
        # card_surface.blit(foxtail_img, (68, 0))  # Does not look good. Instead, use word "E"
        enhance_text = "E"
        for dx, dy in outline_offsets:
            enhance_outline = font_bold.render(enhance_text, True, (0, 0, 0))
            card_surface.blit(enhance_outline, (sx(80) + dx, sy(8) + dy))
        enhance_render = font_bold.render(enhance_text, True, (255, 215, 0))
        card_surface.blit(enhance_render, (sx(80), sy(8)))
    
    return card_surface


def create_slots(count, start_pos, size, spacing, image_key):
    slots = []
    for i in range(count):
        slot = pygame_gui.elements.UIImage(
            pygame.Rect((start_pos[0] + i * spacing, start_pos[1]), size),
            pygame.Surface(size),
            ui_manager
        )
        slot.set_image(image_others[image_key])
        slots.append(slot)
    return slots

global_vars_hand_slots = {1: create_slots(9, (300, 50), (100, 145), 110, "404coyote"), 
                          2: create_slots(9, (300, 700), (100, 145), 110, "404coyote")}

global_vars_field_slots = {1: create_slots(5, (300, 300), (100, 145), 120, "404coyote"), 
                           2: create_slots(5, (300, 450), (100, 145), 120, "404coyote")}

global_vars_tail_indicators = {1: create_slots(9, (300, 220), (32, 32), 40, "405"), 
                               2: create_slots(9, (300, 648), (32, 32), 40, "405")}
global_vars_tail_indicators_active = {1: [], 2: []}

global_vars_leader_slots = {1: create_slots(1, (50, 50), (200, 200), 0, "404coyote"),
                            2: create_slots(1, (50, 900 - 200 - 50), (200, 200), 0, "404coyote")}

global_vars_player_hp_slots = {1: create_slots(1, (50, 260), (200, 50), 0, "405"),
                               2: create_slots(1, (50, 900 - 300), (200, 50), 0, "405")}

player_1_hp_slot = global_vars_player_hp_slots[1][0]
player_2_hp_slot = global_vars_player_hp_slots[2][0]

# =====================================
# End of Example UI Components
# =====================================
# Component tooltips
# =====================================

def build_component_tooltips():
    """
    All tooltips here. Delay should always be 0.1
    """
    settings_button.set_tooltip("Open settings window.", delay=0.1, wrap_width=300)
    end_turn_button.set_tooltip("End your turn and pass to opponent.", delay=0.1, wrap_width=300)
    new_game_button.set_tooltip("Start a new game.", delay=0.1, wrap_width=300)
    deck_builder_button.set_tooltip("Open deck builder to create custom decks.", delay=0.1, wrap_width=300)


build_component_tooltips()

# =====================================
# Windows & Support Functions
# =====================================

def build_settings_window():
    global theme_selection_menu, settings_window, ai_player1_toggle, ai_player2_toggle
    global settings_p1_deck_dropdown, settings_p2_deck_dropdown
    try:
        settings_window.kill()
    except Exception as e:
        pass

    def local_translate(s: str) -> str:
        # If ever needed
        return s

    # Get current AI manager based on toggle
    current_ai_manager = global_vars_minimax_ai_manager

    settings_window = pygame_gui.elements.UIWindow(pygame.Rect((500, 150), (400, 600)),
                                        ui_manager,
                                        window_display_title=local_translate("Settings"),
                                        object_id="#settings_window",
                                        resizable=False)

    theme_selection_label = pygame_gui.elements.UILabel(pygame.Rect((10, 10), (140, 35)),
                                        local_translate("Theme:"),
                                        ui_manager,
                                        container=settings_window)

    theme_selection_menu = pygame_gui.elements.UIDropDownMenu(["Yellow Theme", "Purple Theme", "Red Theme", "Blue Theme", "Green Theme", "Pink Theme"],
                                                            global_vars_theme,
                                                            pygame.Rect((180, 10), (156, 35)),
                                                            ui_manager,
                                                            container=settings_window,)

    # AI Player Settings
    ai_settings_label = pygame_gui.elements.UILabel(pygame.Rect((10, 60), (340, 35)),
                                        local_translate("AI Player Settings:"),
                                        ui_manager,
                                        container=settings_window)

    ai_player1_label = pygame_gui.elements.UILabel(pygame.Rect((10, 100), (160, 35)),
                                        local_translate("AI controls Player 1:"),
                                        ui_manager,
                                        container=settings_window)

    ai_player1_toggle = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((200, 100), (100, 35)),
                                        text="ON" if current_ai_manager.ai_enabled[1] else "OFF",
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#ai_player1_toggle")

    ai_player2_label = pygame_gui.elements.UILabel(pygame.Rect((10, 145), (160, 35)),
                                        local_translate("AI controls Player 2:"),
                                        ui_manager,
                                        container=settings_window)

    ai_player2_toggle = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((200, 145), (100, 35)),
                                        text="ON" if current_ai_manager.ai_enabled[2] else "OFF",
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#ai_player2_toggle")

    # CUETS Player Turn and CUETS Opponent Turn Depth Dropdown
    global cuets_player_turn_dropdown, cuets_opp_turn_dropdown
    cuets_player_turn_label = pygame_gui.elements.UILabel(pygame.Rect((10, 190), (180, 35)),
                                        local_translate("CUETS Player Turn:"),
                                        ui_manager,
                                        container=settings_window)
    cuets_player_turn_label.set_tooltip("Set the min number of continuous unique end turn states reaches before random exploration stops, for the current player.", delay=0.1, wrap_width=300)
    cuets_player_turn_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=["2", "3", "4", "5", "6", "7", "8", "9", "10"],
                                        starting_option=str(global_vars_cuets_player_turn_set_option),
                                        relative_rect=pygame.Rect((200, 190), (100, 35)),
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#ai_depth_dropdown")

    cuets_opp_turn_label = pygame_gui.elements.UILabel(pygame.Rect((10, 235), (180, 35)),
                                        local_translate("CUETS Opponent Turn:"),
                                        ui_manager,
                                        container=settings_window)
    cuets_opp_turn_label.set_tooltip("When exploring end turn states for the current player, do the same for the opponent turn to avoid loss. Set the min number of continuous unique end turn states reaches before random exploration stops.", delay=0.1, wrap_width=300)
    cuets_opp_turn_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=["2", "3", "4", "5", "6", "7", "8", "9", "10"],
                                        starting_option=str(global_vars_cuets_opp_turn_set_option),
                                        relative_rect=pygame.Rect((200, 235), (100, 35)),
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#ai_depth_dropdown_opp")

    # Deck Selection for New Games
    deck_settings_label = pygame_gui.elements.UILabel(pygame.Rect((10, 290), (340, 35)),
                                        local_translate("Deck Settings:"),
                                        ui_manager,
                                        container=settings_window)

    deck_options = _get_deck_options_list()

    p1_deck_label = pygame_gui.elements.UILabel(pygame.Rect((10, 330), (120, 35)),
                                        local_translate("Player 1 Deck:"),
                                        ui_manager,
                                        container=settings_window)

    # Ensure selected deck is valid, fallback to Random
    p1_selected = deck_builder_selected_decks.get(1, "Random")
    if p1_selected not in deck_options:
        p1_selected = "Random"
        deck_builder_selected_decks[1] = "Random"

    settings_p1_deck_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=deck_options,
                                        starting_option=p1_selected,
                                        relative_rect=pygame.Rect((140, 330), (200, 35)),
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#settings_p1_deck")

    p2_deck_label = pygame_gui.elements.UILabel(pygame.Rect((10, 375), (120, 35)),
                                        local_translate("Player 2 Deck:"),
                                        ui_manager,
                                        container=settings_window)

    p2_selected = deck_builder_selected_decks.get(2, "Random")
    if p2_selected not in deck_options:
        p2_selected = "Random"
        deck_builder_selected_decks[2] = "Random"

    settings_p2_deck_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=deck_options,
                                        starting_option=p2_selected,
                                        relative_rect=pygame.Rect((140, 375), (200, 35)),
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#settings_p2_deck")

    settings_p1_deck_dropdown.set_tooltip("Select which deck Player 1 uses when starting a new game.", delay=0.1, wrap_width=300)
    settings_p2_deck_dropdown.set_tooltip("Select which deck Player 2 uses when starting a new game.", delay=0.1, wrap_width=300)


settings_window = None
theme_selection_menu = None
ai_player1_toggle = None
ai_player2_toggle = None
cuets_player_turn_dropdown = None
cuets_opp_turn_dropdown = None
global_vars_cuets_player_turn_set_option: int = 6
global_vars_cuets_opp_turn_set_option: int = 3


def change_theme(theme=None):
    global global_vars_theme, global_vars_shcg
    THEME_FILES = {
        "Yellow Theme": "theme_light_yellow.json",
        "Purple Theme": "theme_light_purple.json",
        "Red Theme": "theme_light_red.json",
        "Blue Theme": "theme_light_blue.json",
        "Green Theme": "theme_light_green.json",
        "Pink Theme": "theme_light_pink.json"
    }
    global_vars_theme = theme if theme else theme_selection_menu.selected_option[0]
    if global_vars_theme in THEME_FILES:
        theme_file = THEME_FILES[global_vars_theme]
        ui_manager_lower.get_theme().load_theme(theme_file)
        ui_manager.get_theme().load_theme(theme_file)
        ui_manager_overlay.get_theme().load_theme(theme_file)
    else:
        raise ValueError(f"Unknown theme: {global_vars_theme}")
    ui_manager_lower.rebuild_all_from_changed_theme_data()
    ui_manager.rebuild_all_from_changed_theme_data()
    ui_manager_overlay.rebuild_all_from_changed_theme_data()
    build_component_tooltips() # This is needed as theme switching resets tooltips delay and wrap width
    global_vars_shcg.draw_deck_ui(1)
    global_vars_shcg.draw_deck_ui(2)
    global_vars_shcg.draw_hand_ui(1)
    global_vars_shcg.draw_hand_ui(2)
    global_vars_shcg.draw_field_ui(1)
    global_vars_shcg.draw_field_ui(2)
    


global_vars_shcg: SHCGGameState = SHCGGameState(current_player=2)
global_vars_use_minimax_ai: bool = True  # Default to new minimax AI
global_vars_minimax_ai_manager = ai_player_new.MinimaxAIManager(6, 3)

def _build_random_deck() -> list[cards.Card]:
    """Build a random deck (15 types x 3 copies = 45 cards)."""
    deck: list[cards.Card] = []
    selected_card_types = random.sample(cards.all_card_types, 15)
    for card_type in selected_card_types:
        for _ in range(3):
            deck.append(card_type())
    random.shuffle(deck)
    return deck


def _resolve_deck_for_player(player: int) -> list[cards.Card]:
    """Resolve which deck to use for a player based on settings selection."""
    deck_name = deck_builder_selected_decks.get(player, "Random")
    if deck_name != "Random" and deck_name in deck_builder_saved_decks:
        return _build_deck_from_recipe(deck_builder_saved_decks[deck_name])
    return _build_random_deck()


def start_new_game():
    # fetch decks, deck and deck for cpu are selected by player
    # shuffle decks
    # draw UI components
    # Use deck selected in settings (saved deck or random)
    example_deck_1 = _resolve_deck_for_player(1)
    example_deck_2 = _resolve_deck_for_player(2)

    text_box.set_text(text_box_introduction_text)
    global global_vars_shcg
    global_vars_shcg = SHCGGameState(current_player=2)
    global_vars_shcg.decks = {1: example_deck_1, 2: example_deck_2}

    # draw UI
    global_vars_shcg.draw_player_hp_ui()
    global_vars_shcg.draw_tail_ui(1)
    global_vars_shcg.draw_tail_ui(2)
    # draw hand
    global_vars_shcg.draw_hand_ui(1)
    global_vars_shcg.draw_hand_ui(2)
    # draw deck
    global_vars_shcg.draw_deck_ui(1)
    global_vars_shcg.draw_deck_ui(2)
    # draw field
    global_vars_shcg.draw_field_ui(1)
    global_vars_shcg.draw_field_ui(2)
    # text_box.append_html_text(f"Player {global_vars_shcg.current_player}'s turn. \n")
    # text_box.append_html_text(f"Turn {global_vars_shcg.turn}. \n")
    text_box.append_html_text(f"ニューゲームを開始したぞ！プレイヤー2のターンなのじゃ。\n")
    text_box.append_html_text(f"ターン{global_vars_shcg.turn}\n")
    global_vars_minimax_ai_manager.ai_clear_pending_actions()


def build_debug_window():
    """
    A dropdown and button
    Add any card to current player's top of deck for testing
    """
    global debug_window, debug_card_selection_dropdown, debug_add_card_button
    global debug_add_player_1_hp_button, debug_add_player_2_hp_button
    global debug_add_foxtail_player_1_button
    try:
        debug_window.kill()
    except Exception as e:
        pass

    debug_window = pygame_gui.elements.UIWindow(pygame.Rect((600, 250), (280, 400)),
                                        ui_manager,
                                        window_display_title="Debug Window",
                                        object_id="#debug_window",
                                        resizable=False)
    
    debug_card_selection_label = pygame_gui.elements.UILabel(pygame.Rect((10, 10), (50, 35)),
                                        "Card:",
                                        ui_manager,
                                        container=debug_window)
    all_card_names = [card_type().name for card_type in cards.all_card_types]
    debug_card_selection_dropdown = pygame_gui.elements.UIDropDownMenu(all_card_names,
                                                        all_card_names[0],
                                                        pygame.Rect((70, 10), (200, 35)),
                                                        ui_manager,
                                                        container=debug_window,)
    debug_add_card_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 55), (260, 50)),
                                        text="Add to Top of Deck",
                                        manager=ui_manager,
                                        container=debug_window,
                                        object_id="#debug_add_card_button",
                                        command=debug_add_card_to_top_of_deck)
    
    debug_add_player_1_hp_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 115), (260, 50)),
                                        text="Add 1 HP to Player 1",
                                        manager=ui_manager,
                                        container=debug_window,
                                        object_id="#debug_add_player_1_hp_button",
                                        command=debug_add_1_hp_to_player_1)

    debug_add_player_2_hp_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 175), (260, 50)),
                                        text="Add 1 HP to Player 2",
                                        manager=ui_manager,
                                        container=debug_window,
                                        object_id="#debug_add_player_2_hp_button",
                                        command=debug_add_1_hp_to_player_2)
    
    debug_add_foxtail_player_1_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 235), (260, 50)),
                                        text="Add Foxtail to Current Player",
                                        manager=ui_manager,
                                        container=debug_window,
                                        object_id="#debug_add_foxtail_player_1_button",
                                        command=debug_add_foxtail_to_current_player)



debug_window = None
debug_card_selection_dropdown = None
debug_add_card_button = None

def debug_add_card_to_top_of_deck():
    global global_vars_shcg
    if global_vars_shcg.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    card_to_add: cards.Card | None = None
    card_name = debug_card_selection_dropdown.selected_option[0]
    for card_type in cards.all_card_types:
        if card_type().name == card_name:
            card_to_add = card_type()
            break
    if card_to_add:
        cp = global_vars_shcg.current_player
        global_vars_shcg.decks[cp].append(card_to_add)
        global_vars_shcg.draw_deck_ui(cp)
        text_box.append_html_text(f"DEBUG:カード「{card_name}」をプレイヤー{cp}のデッキの一番上に追加したのじゃ。\n")
    else:
        raise ValueError(f"Card not found: {card_name}")

def debug_add_1_hp_to_player_1():
    global global_vars_shcg
    if global_vars_shcg.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    prev_hp = global_vars_shcg.hp[1]
    global_vars_shcg.hp[1] = min(global_vars_shcg.hp[1] + 1, global_vars_shcg.max_hp[1])
    delta = global_vars_shcg.hp[1] - prev_hp
    global_vars_shcg.draw_player_hp_ui()
    text_box.append_html_text(f"DEBUG:プレイヤー1の体力を{delta}回復したのじゃ。\n")

def debug_add_1_hp_to_player_2():
    global global_vars_shcg
    if global_vars_shcg.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    prev_hp = global_vars_shcg.hp[2]
    global_vars_shcg.hp[2] = min(global_vars_shcg.hp[2] + 1, global_vars_shcg.max_hp[2])
    delta = global_vars_shcg.hp[2] - prev_hp
    global_vars_shcg.draw_player_hp_ui()
    text_box.append_html_text(f"DEBUG:プレイヤー2の体力を{delta}回復したのじゃ。\n")

def debug_add_foxtail_to_current_player():
    global global_vars_shcg
    if global_vars_shcg.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    cp = global_vars_shcg.current_player
    if global_vars_shcg.foxtail[cp] < 9:
        global_vars_shcg.foxtail[cp] += 1
        global_vars_shcg.draw_tail_ui(cp)
        text_box.append_html_text(f"DEBUG:プレイヤーに狐尾を1つ追加したのじゃ。\n")
    else:
        text_box.append_html_text(f"DEBUG:プレイヤーの狐尾は最大数に達しているのじゃ。\n")


# top right
debug_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1500, 10), (90, 35)),
                                    text='Debug',
                                    manager=ui_manager,
                                    command=build_debug_window)

# Graveyard / Banished buttons (same x as debug button)
graveyard_window = None

def build_graveyard_window(player: int, zone: str):
    """
    Build a window showing graveyard or banished cards for a player.
    zone: 'graveyard' or 'banished'
    """
    global graveyard_window
    try:
        graveyard_window.kill()
    except Exception:
        pass

    if zone == 'graveyard':
        card_list = global_vars_shcg.graveyard[player]
        title = f"P{player} 墓場 ({len(card_list)})"
    else:
        card_list = global_vars_shcg.banished[player]
        title = f"P{player} 消滅 ({len(card_list)})"

    graveyard_window = pygame_gui.elements.UIWindow(
        pygame.Rect((400, 150), (800, 500)),
        ui_manager,
        window_display_title=title,
        object_id="#graveyard_window",
        resizable=False
    )

    if not card_list:
        pygame_gui.elements.UILabel(
            pygame.Rect((10, 10), (760, 35)),
            "カードなし",
            ui_manager,
            container=graveyard_window
        )
        return

    # Display cards in a grid (6 per row)
    cards_per_row = 6
    card_w, card_h = 100, 145
    pad_x, pad_y = 10, 10
    for i, card in enumerate(card_list):
        row = i // cards_per_row
        col = i % cards_per_row
        x = pad_x + col * (card_w + pad_x)
        y = pad_y + row * (card_h + pad_y)
        card_ui = pygame_gui.elements.UIImage(
            pygame.Rect((x, y), (card_w, card_h)),
            pygame.Surface((card_w, card_h)),
            ui_manager,
            container=graveyard_window
        )
        card_ui.set_image(draw_card(card))
        card_ui.set_tooltip(card.tooltip_str(), delay=0.1, wrap_width=300)


# Player 1 graveyard/banished buttons (below debug button, same x)
p1_graveyard_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 50), (90, 35)),
    text='P1 G',
    manager=ui_manager,
    command=lambda: build_graveyard_window(1, 'graveyard'))

p1_banished_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 90), (90, 35)),
    text='P1 B',
    manager=ui_manager,
    command=lambda: build_graveyard_window(1, 'banished'))

# Player 2 graveyard/banished buttons (near bottom, same x)
p2_graveyard_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 810), (90, 35)),
    text='P2 G',
    manager=ui_manager,
    command=lambda: build_graveyard_window(2, 'graveyard'))

p2_banished_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 850), (90, 35)),
    text='P2 B',
    manager=ui_manager,
    command=lambda: build_graveyard_window(2, 'banished'))


# =====================================
# Deck Builder
# =====================================

# Deck builder state
deck_builder_window = None
deck_builder_deck: dict[str, int] = {}  # card_name -> copy count (1-3)
deck_builder_saved_decks: dict[str, dict[str, int]] = {}  # deck_name -> recipe
deck_builder_selected_decks: dict[int, str] = {1: "Random", 2: "Random"}  # player -> deck name or "Random"

DECKS_SAVE_FILE = "saved_decks.json"

# UI element references
deck_builder_collection_list: pygame_gui.elements.UISelectionList | None = None # List of available cards
deck_builder_deck_list: pygame_gui.elements.UISelectionList | None = None # List of cards in current deck with counts
deck_builder_add_button = None
deck_builder_add3_button = None
deck_builder_remove_button = None
deck_builder_remove3_button = None
deck_builder_clear_button = None
deck_builder_randomize_button = None
deck_builder_deck_count_label = None
deck_builder_card_preview = None
deck_builder_card_info_label = None
deck_builder_save_button = None
deck_builder_load_button = None
deck_builder_delete_button = None
deck_builder_rename_button = None
deck_builder_saved_list = None
deck_builder_name_entry = None

# Settings window deck selection UI references
settings_p1_deck_dropdown = None
settings_p2_deck_dropdown = None

# Mapping from display string to card type class
deck_builder_collection_map: dict[str, type] = {}
deck_builder_deck_item_to_name: dict[str, str] = {}

global_vars_db_deck_max_copies = 3
global_vars_db_where_currently_selected: str = "collection"  # or "deck"
global_vars_db_recently_selected_card: cards.Card | None = None


def save_decks_to_file():
    """Save all saved decks and selected deck settings to JSON file."""
    data = {
        "saved_decks": deck_builder_saved_decks,
        "selected_decks": deck_builder_selected_decks,
    }
    with open(DECKS_SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_decks_from_file():
    """Load saved decks and selected deck settings from JSON file."""
    global deck_builder_saved_decks, deck_builder_selected_decks
    if not os.path.exists(DECKS_SAVE_FILE):
        return
    try:
        with open(DECKS_SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "saved_decks" in data and isinstance(data["saved_decks"], dict):
            deck_builder_saved_decks = data["saved_decks"]
        if "selected_decks" in data and isinstance(data["selected_decks"], dict):
            for key in ["1", "2"]:
                if key in data["selected_decks"]:
                    deck_builder_selected_decks[int(key)] = data["selected_decks"][key]
    except (json.JSONDecodeError, KeyError, ValueError):
        pass


def _get_deck_options_list() -> list[str]:
    """Get list of deck names for dropdowns, with 'Random' as first option."""
    return ["Random"] + sorted(deck_builder_saved_decks.keys())


# Load saved decks on startup
load_decks_from_file()


def _deck_builder_card_display_str(card_type) -> str:
    """Create a display string for a card type in the collection list."""
    card = card_type()
    if card.type == 'follower':
        return f"[{card.cost}] {card.name} ({card.attack}/{card.hp})"
    elif card.type == 'spell':
        return f"[{card.cost}] {card.name} (Spell)"
    elif card.type == 'amulet':
        return f"[{card.cost}] {card.name} (Amulet)"
    return f"[{card.cost}] {card.name}"


def _build_deck_from_recipe(recipe: dict[str, int]) -> list[cards.Card]:
    """Build a list of Card instances from a deck recipe."""
    deck = []
    for card_type in cards.all_card_types:
        card = card_type()
        if card.name in recipe:
            for _ in range(recipe[card.name]):
                deck.append(card_type())
    random.shuffle(deck)
    return deck


def build_deck_builder_window():
    global deck_builder_window
    global deck_builder_collection_list, deck_builder_deck_list
    global deck_builder_add_button, deck_builder_add3_button
    global deck_builder_remove_button, deck_builder_remove3_button, deck_builder_clear_button
    global deck_builder_randomize_button
    global deck_builder_deck_count_label, deck_builder_card_preview
    global deck_builder_card_info_label
    global deck_builder_save_button, deck_builder_load_button
    global deck_builder_delete_button, deck_builder_rename_button
    global deck_builder_saved_list, deck_builder_name_entry
    global deck_builder_collection_map

    try:
        deck_builder_window.kill()
    except Exception:
        pass

    deck_builder_window = pygame_gui.elements.UIWindow(
        pygame.Rect((150, 50), (1200, 750)),
        ui_manager,
        window_display_title="Deck Builder",
        object_id="#deck_builder_window",
        resizable=False
    )

    # === Left Panel: Card Collection ===
    pygame_gui.elements.UILabel(
        pygame.Rect((10, 5), (380, 25)),
        "Card Collection",
        ui_manager,
        container=deck_builder_window
    )

    # Build card list items and mapping
    card_list_items = []
    deck_builder_collection_map = {}
    for card_type in cards.all_card_types:
        display_str = _deck_builder_card_display_str(card_type)
        card_list_items.append(display_str)
        deck_builder_collection_map[display_str] = card_type

    deck_builder_collection_list = pygame_gui.elements.UISelectionList(
        pygame.Rect((10, 35), (380, 470)),
        card_list_items,
        ui_manager,
        container=deck_builder_window,
        allow_multi_select=False
    )

    # === Center Panel: Preview & Controls ===
    deck_builder_card_preview = pygame_gui.elements.UIImage(
        pygame.Rect((405, 35), (200, 290)),
        pygame.transform.scale(image_405_card_slot, (200, 290)),
        ui_manager,
        container=deck_builder_window
    )

    deck_builder_card_info_label = pygame_gui.elements.UILabel(
        pygame.Rect((405, 330), (200, 40)),
        "",
        ui_manager,
        container=deck_builder_window
    )

    deck_builder_add_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 375), (120, 35)),
        text="Add x1",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_add"
    )

    deck_builder_add3_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 415), (120, 35)),
        text="Add x3",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_add3"
    )

    deck_builder_remove_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 455), (120, 35)),
        text="Remove x1",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_remove"
    )

    deck_builder_remove3_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 495), (120, 35)),
        text="Remove x3",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_remove3"
    )

    deck_builder_clear_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 535), (120, 35)),
        text="Clear Deck",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_clear"
    )

    deck_builder_randomize_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 575), (120, 35)),
        text="Random",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_random"
    )

    # === Right Panel: Deck Contents ===
    deck_builder_deck_count_label = pygame_gui.elements.UILabel(
        pygame.Rect((620, 5), (380, 25)),
        "Deck: 0 cards (0 types)",
        ui_manager,
        container=deck_builder_window
    )

    deck_builder_deck_list = pygame_gui.elements.UISelectionList(
        pygame.Rect((620, 35), (380, 370)),
        [],
        ui_manager,
        container=deck_builder_window,
        allow_multi_select=False
    )

    # === Bottom: Deck Name Entry + Save/Load/Delete/Rename + Saved Decks List ===
    pygame_gui.elements.UILabel(
        pygame.Rect((10, 515), (80, 30)),
        "Deck Name:",
        ui_manager,
        container=deck_builder_window
    )

    deck_builder_name_entry = pygame_gui.elements.UITextEntryLine(
        pygame.Rect((95, 515), (290, 30)),
        ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_name_entry"
    )
    deck_builder_name_entry.set_text("My Deck")

    deck_builder_save_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((10, 555), (180, 35)),
        text="Save Deck",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_save"
    )

    deck_builder_rename_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((200, 555), (180, 35)),
        text="Rename Deck",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_rename"
    )

    deck_builder_delete_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((10, 600), (180, 35)),
        text="Delete Deck",
        manager=ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_delete"
    )

    # Saved decks list
    pygame_gui.elements.UILabel(
        pygame.Rect((540, 410), (200, 25)),
        "Saved Decks:",
        ui_manager,
        container=deck_builder_window
    )

    deck_builder_saved_list = pygame_gui.elements.UISelectionList(
        pygame.Rect((540, 440), (380, 195)),
        _get_saved_decks_display_list(),
        ui_manager,
        container=deck_builder_window,
        allow_multi_select=False
    )


    # Set tooltips
    deck_builder_add_button.set_tooltip("Add 1 copy of the selected card to the deck.", delay=0.1, wrap_width=300)
    deck_builder_add3_button.set_tooltip("Set the selected card to 3 copies in the deck.", delay=0.1, wrap_width=300)
    deck_builder_remove_button.set_tooltip("Remove 1 copy of the selected card from the deck.", delay=0.1, wrap_width=300)
    deck_builder_remove3_button.set_tooltip("Remove up to 3 copies of the selected card from the deck.", delay=0.1, wrap_width=300)
    deck_builder_clear_button.set_tooltip("Remove all cards from the deck.", delay=0.1, wrap_width=300)
    deck_builder_randomize_button.set_tooltip("Fill the deck with 15 random card types (x3 each).", delay=0.1, wrap_width=300)
    deck_builder_save_button.set_tooltip("Save the current deck with the name in the text field.", delay=0.1, wrap_width=300)
    deck_builder_delete_button.set_tooltip("Delete the selected saved deck.", delay=0.1, wrap_width=300)
    deck_builder_rename_button.set_tooltip("Rename the selected saved deck to the name in the text field.", delay=0.1, wrap_width=300)

    # Refresh deck display
    _update_deck_builder_deck_display()



def _get_saved_decks_display_list() -> list[str]:
    """Build display strings for the saved decks list."""
    items = []
    for name in sorted(deck_builder_saved_decks.keys()):
        recipe = deck_builder_saved_decks[name]
        total = sum(recipe.values())
        items.append(f"{name} ({total} cards, {len(recipe)} types)")
    return items if items else ["(No saved decks)"]


def _get_saved_list_selected_name() -> str | None:
    """Get the deck name from the selected saved decks list item."""
    if not deck_builder_saved_list:
        return None
    selected = deck_builder_saved_list.get_single_selection()
    if not selected or selected == "(No saved decks)":
        return None
    # Format is "DeckName (N cards, M types)" - extract name before " ("
    idx = selected.rfind(" (")
    if idx > 0:
        return selected[:idx]
    return selected


def _refresh_saved_decks_list():
    """Refresh the saved decks list widget."""
    if deck_builder_saved_list:
        deck_builder_saved_list.set_item_list(_get_saved_decks_display_list())


def _get_selected_card_type(where: str):
    """
    Get the card type class.
    where: collection or deck
    """
    global global_vars_db_where_currently_selected, global_vars_db_recently_selected_card
    if not deck_builder_collection_list:
        return None
    if where == "collection":
        global_vars_db_where_currently_selected = "collection"
        selected = deck_builder_collection_list.get_single_selection()
    elif where == "deck":
        global_vars_db_where_currently_selected = "deck"
        selected = deck_builder_deck_list.get_single_selection()
        # remove x1 x2 x3 from end of string for mapping
        if selected:
            selected = selected.rsplit(" x", 1)[0]
    else:
        raise ValueError(f"Invalid where parameter: {where}")
    if not selected:
        return None
    global_vars_db_recently_selected_card = deck_builder_collection_map.get(selected)
    return global_vars_db_recently_selected_card


def deck_builder_add_card(count: int = 1):
    """Add copies of the selected card to the deck."""
    card_type = global_vars_db_recently_selected_card
    if not card_type:
        return
    card_name = card_type().name
    current = deck_builder_deck.get(card_name, 0)
    if count == 1:
        deck_builder_deck[card_name] = min(current + 1, global_vars_db_deck_max_copies)
    else:
        deck_builder_deck[card_name] = global_vars_db_deck_max_copies
    _update_deck_builder_deck_display()


def deck_builder_remove_card(count: int = 1):
    """Remove copies of a card from the deck (selected from either list)."""
    card_name = None
    card_type = global_vars_db_recently_selected_card
    if card_type:
        card_name = card_type().name
    if not card_name or card_name not in deck_builder_deck:
        return
    if count <= 1:
        deck_builder_deck[card_name] -= 1
    else:
        deck_builder_deck[card_name] -= count
    if deck_builder_deck[card_name] <= 0:
        del deck_builder_deck[card_name]
    _update_deck_builder_deck_display()


def deck_builder_clear():
    """Clear all cards from the deck."""
    deck_builder_deck.clear()
    _update_deck_builder_deck_display()


def deck_builder_randomize():
    """Fill the deck with 15 random card types, 3 copies each."""
    deck_builder_deck.clear()
    selected = random.sample(cards.all_card_types, 15)
    for card_type in selected:
        card = card_type()
        deck_builder_deck[card.name] = 3
    _update_deck_builder_deck_display()


def _update_deck_builder_deck_display():
    """Refresh the deck list and count label."""
    global deck_builder_deck_item_to_name
    if not deck_builder_deck_list or not deck_builder_deck_count_label:
        return

    # Build sorted deck list items (by type priority, then cost, then name)
    type_priority = {'follower': 0, 'spell': 1, 'amulet': 2}
    entries = []
    for card_type in cards.all_card_types:
        card = card_type()
        if card.name in deck_builder_deck:
            count = deck_builder_deck[card.name]
            entries.append((type_priority[card.type], card.cost, card.name, count, card_type))

    entries.sort()
    items = []
    deck_builder_deck_item_to_name = {}
    for _, _, name, count, card_type in entries:
        display = f"{_deck_builder_card_display_str(card_type)} x{count}"
        items.append(display)
        deck_builder_deck_item_to_name[display] = name
    total_cards = sum(count for _, _, _, count, _ in entries)

    deck_builder_deck_list.set_item_list(items)
    deck_builder_deck_count_label.set_text(
        f"Deck: {total_cards} cards ({len(deck_builder_deck)} types)"
    )


def _update_deck_builder_card_info(where: str):
    """
    Update card preview image and info label based on current selection.
    where: collection or deck, determines which selection to read from for preview
    """
    if not deck_builder_card_preview or not deck_builder_card_info_label:
        return
    card_type = _get_selected_card_type(where)
    if card_type:
        card = card_type()
        preview_surface = draw_card(card)
        deck_builder_card_preview.set_image(preview_surface)
        deck_builder_card_preview.set_tooltip(card.tooltip_str(), delay=0.1, wrap_width=300)
        count = deck_builder_deck.get(card.name, 0)
        deck_builder_card_info_label.set_text(f"In deck: {count}/{global_vars_db_deck_max_copies}")
    else:
        deck_builder_card_preview.set_image(
            image_405_card_slot
        )
        deck_builder_card_preview.set_tooltip("", delay=0.1, wrap_width=300)
        deck_builder_card_info_label.set_text("")


def deck_builder_save_deck():
    """Save the current deck editor contents under the name in the text entry."""
    if not deck_builder_name_entry or not deck_builder_deck:
        return
    name = deck_builder_name_entry.get_text().strip()
    if not name:
        return
    deck_builder_saved_decks[name] = dict(deck_builder_deck)
    save_decks_to_file()
    _refresh_saved_decks_list()


def deck_builder_load_deck():
    """Load the selected saved deck into the editor."""
    name = _get_saved_list_selected_name()
    if not name or name not in deck_builder_saved_decks:
        return
    deck_builder_deck.clear()
    deck_builder_deck.update(deck_builder_saved_decks[name])
    if deck_builder_name_entry:
        deck_builder_name_entry.set_text(name)
    _update_deck_builder_deck_display()


def deck_builder_delete_deck():
    """Delete the selected saved deck."""
    name = _get_saved_list_selected_name()
    if not name or name not in deck_builder_saved_decks:
        return
    del deck_builder_saved_decks[name]
    # If any player had this deck selected, reset to Random
    for p in [1, 2]:
        if deck_builder_selected_decks.get(p) == name:
            deck_builder_selected_decks[p] = "Random"
    save_decks_to_file()
    _refresh_saved_decks_list()


def deck_builder_rename_deck():
    """Rename the selected saved deck to the name in the text entry."""
    old_name = _get_saved_list_selected_name()
    if not old_name or old_name not in deck_builder_saved_decks:
        return
    if not deck_builder_name_entry:
        return
    new_name = deck_builder_name_entry.get_text().strip()
    if not new_name or new_name == old_name:
        return
    # Move recipe to new name
    deck_builder_saved_decks[new_name] = deck_builder_saved_decks.pop(old_name)
    # Update any player selections that referenced the old name
    for p in [1, 2]:
        if deck_builder_selected_decks.get(p) == old_name:
            deck_builder_selected_decks[p] = new_name
    save_decks_to_file()
    _refresh_saved_decks_list()


# =====================================
# End of Deck Builder
# =====================================

start_new_game()

# =====================================
# End of Windows & Support Functions
# =====================================




if __name__ == "__main__":
    pygame.display.set_caption("Super Hard Card Game")
    try:
        pygame.display.set_icon(pygame.image.load("icon.png"))
    except Exception:
        print(f"Error loading icon.png")

    print("Starting!")
    # Drag and Drop feature
    ui_drag_and_drop_target = None
    ui_drag_and_drop_target_orig_pos = (0, 0)
    ui_drag_and_drop_usage: str = ""
    running = True 

    # other variables
    the_selected_card: cards.Card | None = None # record which card in hand is being dragged


    while running:
        time_delta = clock.tick(60)/1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_decks_to_file()
                running = False
                            
            if event.type == pygame.KEYDOWN:
                pass

            if event.type == pygame.KEYUP:
                pass

            # right click
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                pass

            # left click
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not global_vars_shcg.concluded:
                cp = global_vars_shcg.current_player
                if global_vars_shcg.top_of_the_deck_ui_marker[cp] and global_vars_shcg.top_of_the_deck_ui_marker[cp].rect.collidepoint(event.pos):
                    ui_drag_and_drop_target_orig_pos = (global_vars_shcg.top_of_the_deck_ui_marker[cp].rect.x, global_vars_shcg.top_of_the_deck_ui_marker[cp].rect.y)
                    ui_drag_and_drop_usage = "draw_card_player"
                    ui_drag_and_drop_target = global_vars_shcg.top_of_the_deck_ui_marker[cp]
                for index, card_slot in enumerate(global_vars_hand_slots[cp]):
                    if card_slot.rect.collidepoint(event.pos):
                        # find which card in hand this is
                        if index < len(global_vars_shcg.hands[cp]):
                            the_selected_card = global_vars_shcg.hands[cp][index]
                        ui_drag_and_drop_target_orig_pos = (card_slot.rect.x, card_slot.rect.y)
                        ui_drag_and_drop_usage = "play_card_player"
                        ui_drag_and_drop_target = card_slot
                # follower on field if can attack, can be dragged to opponent followers or leader to attack
                for index, card_slot in enumerate(global_vars_field_slots[cp]):
                    if card_slot.rect.collidepoint(event.pos):
                        # find which card on field this is
                        if index < len(global_vars_shcg.fields[cp]):
                            the_selected_card = global_vars_shcg.fields[cp][index]
                        if the_selected_card and the_selected_card.type == 'follower' and the_selected_card.attack_ability > 0 and the_selected_card.can_attack_this_turn:
                            ui_drag_and_drop_target_orig_pos = (card_slot.rect.x, card_slot.rect.y)
                            ui_drag_and_drop_usage = "attack_with_follower_player"
                            ui_drag_and_drop_target = card_slot
                for index, tail in enumerate(global_vars_tail_indicators_active[cp]):
                    if tail.rect.collidepoint(event.pos):
                        ui_drag_and_drop_target_orig_pos = (tail.rect.x, tail.rect.y)
                        ui_drag_and_drop_usage = "use_foxtail_player"
                        ui_drag_and_drop_target = tail

            if event.type == pygame.MOUSEBUTTONUP:
                # drag and drop
                if ui_drag_and_drop_target != None:
                    cp = global_vars_shcg.current_player

                    if ui_drag_and_drop_usage == "draw_card_player":
                        if any([slot.rect.colliderect(ui_drag_and_drop_target.rect) for slot in global_vars_hand_slots[cp]]):
                            global_vars_shcg.draw_card_with_foxtail(cp, ui_draw=True, ui_set_text=True)
                        ui_drag_and_drop_target.kill()
                        global_vars_shcg.draw_deck_ui(cp)

                    elif ui_drag_and_drop_usage == "play_card_player":
                        if any([slot.rect.colliderect(ui_drag_and_drop_target.rect) for slot in global_vars_field_slots[cp]]):
                            if the_selected_card:
                                needs_card_sel = the_selected_card.request_card_selection_on_play
                                needs_effect_sel = the_selected_card.request_effect_choose_option
                                if needs_card_sel or needs_effect_sel:
                                    # Check if card selection has valid targets; skip if empty
                                    has_valid_targets = True
                                    if needs_card_sel:
                                        test_options = _build_card_selection_options(needs_card_sel, {
                                            'type': 'play', 'card': the_selected_card, 'player': cp})
                                        if not test_options:
                                            has_valid_targets = False
                                    if has_valid_targets:
                                        build_card_selection_window({
                                            'type': 'play',
                                            'player': cp,
                                            'card': the_selected_card,
                                            'needs_card_selection': needs_card_sel,
                                            'needs_effect_choice': needs_effect_sel,
                                        })
                                    else:
                                        # No valid targets, play with None target
                                        global_vars_shcg.play_card(cp, the_selected_card, ui_draw=True, ui_set_text=True,
                                                                   additional_target=None,
                                                                   is_ai_player=False, effect_choice=None)
                                else:
                                    global_vars_shcg.play_card(cp, the_selected_card, ui_draw=True, ui_set_text=True,
                                                               additional_target=None,
                                                               is_ai_player=False, effect_choice=None)
                                the_selected_card = None
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)

                    elif ui_drag_and_drop_usage == "attack_with_follower_player":
                        opponent = global_vars_shcg.opponent
                        protect_exists = any([c.ability_protect for c in global_vars_shcg.fields[opponent] if isinstance(c, cards.Follower)])
                        for index, slot in enumerate(global_vars_field_slots[opponent]):
                            if slot.rect.collidepoint(event.pos):
                                if the_selected_card:
                                    target_card = None
                                    if index < len(global_vars_shcg.fields[opponent]):
                                        target_card = global_vars_shcg.fields[opponent][index]
                                    if target_card and target_card.type == 'follower':
                                        # if target_card .ability_protect is false but there exists other followers
                                        # on opponent field with ability_protect true, cannot attack this target
                                        if protect_exists and not target_card.ability_protect:
                                            text_box.append_html_text(f"【守護】フォロワーがいるから攻撃できないぞ！ \n")
                                        else:
                                            global_vars_shcg.follower_attack(cp, the_selected_card, target_card, ui_draw=True, ui_set_text=True)
                        if global_vars_leader_slots[opponent][0].rect.collidepoint(event.pos) and the_selected_card.attack_ability >= 2:
                            if protect_exists:
                                text_box.append_html_text(f"【守護】フォロワーがいるから攻撃できないぞ！ \n")
                            else:
                                global_vars_shcg.follower_attack(cp, the_selected_card, "leader", ui_draw=True, ui_set_text=True)
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)

                    elif ui_drag_and_drop_usage == "use_foxtail_player":
                        if global_vars_shcg.enhance_used_this_turn[cp] >= global_vars_shcg.max_enhance_allowed_per_turn[cp]:
                            text_box.append_html_text(f"このターンにはもう強化を使えないのじゃ。 \n")
                        else:
                            for index, slot in enumerate(global_vars_field_slots[cp]):
                                if slot.rect.collidepoint(event.pos):
                                    if index < len(global_vars_shcg.fields[cp]):
                                        target_card = global_vars_shcg.fields[cp][index]
                                        if isinstance(target_card, cards.Follower) and target_card.can_enhance:
                                            needs_card_sel = target_card.request_card_selection_on_enhance
                                            if needs_card_sel:
                                                test_options = _build_card_selection_options(needs_card_sel, {
                                                    'type': 'enhance', 'card': target_card, 'player': cp})
                                                if test_options:
                                                    build_card_selection_window({
                                                        'type': 'enhance',
                                                        'player': cp,
                                                        'card': target_card,
                                                        'needs_card_selection': needs_card_sel,
                                                        'needs_effect_choice': [],
                                                    })
                                                else:
                                                    global_vars_shcg.on_card_enhanced(cp, card_to_enhance=target_card,
                                                                                      additional_target=None,
                                                                                      is_ai_player=False,
                                                                                      ui_draw=True,
                                                                                      ui_set_text=True)
                                            else:
                                                global_vars_shcg.on_card_enhanced(cp, card_to_enhance=target_card,
                                                                                  additional_target=None,
                                                                                  is_ai_player=False,
                                                                                  ui_draw=True,
                                                                                  ui_set_text=True)

                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)

                    else:
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)


                    ui_drag_and_drop_target = None
                    ui_drag_and_drop_usage = ""
                    ui_drag_and_drop_target_orig_pos = (0, 0)

            if event.type == pygame.MOUSEMOTION:
                if ui_drag_and_drop_target != None:
                    ui_drag_and_drop_target.set_position((ui_drag_and_drop_target.rect.x + event.rel[0], ui_drag_and_drop_target.rect.y + event.rel[1]))

            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                # Card selection window buttons
                if card_selection_confirm_button and event.ui_element == card_selection_confirm_button:
                    _execute_pending_selection()
                if card_selection_cancel_button and event.ui_element == card_selection_cancel_button:
                    _cancel_pending_selection()
                if event.ui_element == settings_button:
                    build_settings_window()
                if event.ui_element == new_game_button:
                    start_new_game()
                if event.ui_element == quit_game_button:
                    save_decks_to_file()
                    running = False
                if event.ui_element == end_turn_button:
                    global_vars_shcg.end_turn(ui_draw=True, ui_set_text=True)
                if event.ui_element == deck_builder_button:
                    build_deck_builder_window()
                # Deck builder buttons
                if deck_builder_add_button and event.ui_element == deck_builder_add_button:
                    deck_builder_add_card(1)
                if deck_builder_add3_button and event.ui_element == deck_builder_add3_button:
                    deck_builder_add_card(3)
                if deck_builder_remove_button and event.ui_element == deck_builder_remove_button:
                    deck_builder_remove_card(1)
                if deck_builder_remove3_button and event.ui_element == deck_builder_remove3_button:
                    deck_builder_remove_card(3)
                if deck_builder_clear_button and event.ui_element == deck_builder_clear_button:
                    deck_builder_clear()
                if deck_builder_randomize_button and event.ui_element == deck_builder_randomize_button:
                    deck_builder_randomize()
                if deck_builder_save_button and event.ui_element == deck_builder_save_button:
                    deck_builder_save_deck()
                if deck_builder_delete_button and event.ui_element == deck_builder_delete_button:
                    deck_builder_delete_deck()
                if deck_builder_rename_button and event.ui_element == deck_builder_rename_button:
                    deck_builder_rename_deck()
                # AI toggle buttons
                current_ai_manager = global_vars_minimax_ai_manager
                if ai_player1_toggle and event.ui_element == ai_player1_toggle:
                    current_ai_manager.ai_enabled[1] = not current_ai_manager.ai_enabled[1]
                    current_ai_manager.enable_ai(1, current_ai_manager.ai_enabled[1])
                    ai_player1_toggle.set_text("ON" if current_ai_manager.ai_enabled[1] else "OFF")
                if ai_player2_toggle and event.ui_element == ai_player2_toggle:
                    current_ai_manager.ai_enabled[2] = not current_ai_manager.ai_enabled[2]
                    current_ai_manager.enable_ai(2, current_ai_manager.ai_enabled[2])
                    ai_player2_toggle.set_text("ON" if current_ai_manager.ai_enabled[2] else "OFF")

            if event.type == pygame_gui.UI_TEXT_BOX_LINK_CLICKED:
                pass

            # Deck builder selection list events
            if event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
                if deck_builder_collection_list and event.ui_element == deck_builder_collection_list:
                    _update_deck_builder_card_info('collection')
                if deck_builder_deck_list and event.ui_element == deck_builder_deck_list:
                    _update_deck_builder_card_info('deck')
                if deck_builder_saved_list and event.ui_element == deck_builder_saved_list:
                    name = _get_saved_list_selected_name()
                    if name and deck_builder_name_entry:
                        deck_builder_name_entry.set_text(name)
                    # load
                    deck_builder_load_deck()

            if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                if event.ui_element == theme_selection_menu:
                    change_theme()
                if event.ui_element == cuets_player_turn_dropdown:
                    global_vars_cuets_player_turn_set_option = int(cuets_player_turn_dropdown.selected_option[0])
                    global_vars_minimax_ai_manager.set_new_cuets(global_vars_cuets_player_turn_set_option,
                                                global_vars_cuets_opp_turn_set_option)
                if event.ui_element == cuets_opp_turn_dropdown:
                    global_vars_cuets_opp_turn_set_option = int(cuets_opp_turn_dropdown.selected_option[0])
                    global_vars_minimax_ai_manager.set_new_cuets(global_vars_cuets_player_turn_set_option,
                                                global_vars_cuets_opp_turn_set_option)
                # Deck selection in settings
                if settings_p1_deck_dropdown and event.ui_element == settings_p1_deck_dropdown:
                    deck_builder_selected_decks[1] = settings_p1_deck_dropdown.selected_option[0]
                    save_decks_to_file()
                if settings_p2_deck_dropdown and event.ui_element == settings_p2_deck_dropdown:
                    deck_builder_selected_decks[2] = settings_p2_deck_dropdown.selected_option[0]
                    save_decks_to_file()

            if event.type == pygame_gui.UI_WINDOW_CLOSE:
                if card_selection_window and event.ui_element == card_selection_window:
                    _cancel_pending_selection()

            ui_manager_lower.process_events(event)
            ui_manager.process_events(event)
            ui_manager_overlay.process_events(event)

        # AI Turn Logic - use appropriate AI manager based on toggle
        active_ai_manager = global_vars_minimax_ai_manager
        if not global_vars_shcg.concluded and active_ai_manager.is_ai_turn(global_vars_shcg):
            current_time = pygame.time.get_ticks()
            if current_time - active_ai_manager.last_ai_action_time >= active_ai_manager.ai_action_delay:
                ai = active_ai_manager.get_current_ai(global_vars_shcg)
                if ai:
                    actions = ai.take_turn(
                        global_vars_shcg,
                        ui_draw=True,
                        ui_set_text=True,
                        text_box=text_box
                    )
                    active_ai_manager.last_ai_action_time = current_time
                    if not actions:
                        # AI has no more actions, end turn
                        global_vars_shcg.end_turn(ui_draw=True, ui_set_text=True)

        ui_manager_lower.update(time_delta)
        ui_manager.update(time_delta)
        ui_manager_overlay.update(time_delta)
        if global_vars_theme == "Yellow Theme":
            display_surface.fill(light_yellow)
        elif global_vars_theme == "Purple Theme":
            display_surface.fill(light_purple)
        elif global_vars_theme == "Red Theme":
            display_surface.fill(light_red)
        elif global_vars_theme == "Green Theme":
            display_surface.fill(light_green)
        elif global_vars_theme == "Blue Theme":
            display_surface.fill(light_blue)
        elif global_vars_theme == "Pink Theme":
            display_surface.fill(light_pink)
        ui_manager_lower.draw_ui(display_surface)
        ui_manager.draw_ui(display_surface)
        ui_manager_overlay.draw_ui(display_surface)
        # debug_ui_manager.update(time_delta)
        # debug_ui_manager.draw_ui(display_surface)

        pygame.display.update()

    pygame.quit()
