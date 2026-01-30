import os
import more_itertools as mit
import itertools
import pygame, pygame_gui
import cards
import random


pygame.init()
clock = pygame.time.Clock()

# If we ever need a temporary folder
# if not os.path.exists("./.tmp"):
#     os.mkdir("./.tmp")

# # clean everything in ./.tmp, old data
# for file in os.listdir("./.tmp"):
#     os.remove(f"./.tmp/{file}")

# ====================================
# Game State
# ====================================

class SHCGGameState:
    def __init__(self, current_player):
        self.current_player = current_player  # 1 or 2
        self.turn = 1
        self.concluded = False
        self.decks: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.hands: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.fields: dict[int, list[cards.Card]] = {1: [], 2: []}
        self.hp = {1: 20, 2: 20}
        self.foxtail = {1: 9, 2: 9}
        self.enhance_used_this_turn = {1: 0, 2: 0}
        self.max_enhance_allowed_per_turn = {1: 1, 2: 1}
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
            text_box.append_html_text(f"Player {player} drew a card: {drawn_card}. \n")
        if ui_draw:
            self.draw_hand_ui(player)
            # draw_deck_ui is unnecessary as it is handled by pygame event


    def play_card(self, player: int, card: cards.Card, ui_draw, ui_set_text):
        global single_card_selection_dropdown_field
        if len(self.fields[player]) > 4 and card.type != 'spell':
            return
        if self.foxtail[player] < card.cost:
            return
        self.use_foxtail(player, card.cost, ui_draw, ui_set_text)
        self.hands[player].remove(card)
        if card.request_card_selection_on_play:
            target = None
            if card.request_card_selection_on_play == "field":
                for i, c in enumerate(self.fields[player]):
                    if f"{i + 1} {str(c)}" == single_card_selection_dropdown_field.selected_option[0]:
                        target = c
                        break 
            card.on_play_effect(player, target_follower=target)
        if card.type == 'follower':
            self.fields[player].append(card)
        elif card.type == 'spell':
            pass
        elif card.type == 'amulet':
            self.fields[player].append(card)
        if ui_set_text:
            text_box.append_html_text(f"Player {player} played {card}.\n")
        if ui_draw:
            self.draw_hand_ui(player)
            self.draw_field_ui(player)


    def follower_attack(self, player, attacker: cards.Follower, target: cards.Follower | str, ui_draw, ui_set_text):
        assert attacker.attack_ability > 0, "This follower cannot attack."
        assert attacker.can_attack_this_turn == True, "This follower cannot attack this turn."
        assert attacker.type == 'follower', "Attacker must be a follower."
        assert attacker in self.fields[player], "Attacker is not on the field."
        if isinstance(target, cards.Follower):
            assert target in self.fields[self.opponent], "Target follower is not on opponent's field."
            if ui_set_text:
                text_box.append_html_text(f"{attacker} is about to attack {target}.\n")
            target.hp -= attacker.attack
            attacker.hp -= target.attack
            if target.hp <= 0:
                self.fields[self.opponent].remove(target)
                if ui_set_text:
                    text_box.append_html_text(f"Player {self.opponent}'s {target} was destroyed.\n")
            if attacker.hp <= 0:
                self.fields[self.current_player].remove(attacker)
                if ui_set_text:
                    text_box.append_html_text(f"Player {player}'s {attacker} was destroyed.\n")
            attacker.after_attack_effect()
            if ui_draw:
                self.draw_field_ui(1)
                self.draw_field_ui(2)
        elif target == "leader":
            # リーダーへの攻撃
            self.player_take_damage(self.opponent, attacker.attack, ui_draw, ui_set_text)
            attacker.after_attack_effect()
            self.draw_field_ui(player)
        else:
            raise Exception("Should not reach here.")


    def player_take_damage(self, player: int, amount: int, ui_draw, ui_set_text) -> bool:
        assert amount >= 0
        self.hp[player] -= amount
        if ui_set_text:
            text_box.append_html_text(f"Player {player} took {amount} damage, remaining HP: {self.hp[player]}.\n")
        if amount > 0 and ui_draw:
            self.draw_player_hp_ui()
        if self.hp[player] <= 0:
            winner = self.opponent
            if ui_set_text:
                text_box.append_html_text(f"Player {winner} wins!\n")
            self.concluded = True
            return True
        return False


    def end_turn(self, ui_draw, ui_set_text):
        if self.concluded:
            text_box.append_html_text("The game has concluded. Start a new game instead.\n")
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
                text_box.append_html_text("Draw.\n")
            return
        if ui_draw:
            self.draw_tail_ui(self.current_player)
            self.draw_field_ui(1)
            self.draw_field_ui(2)
        if ui_set_text:
            text_box.set_text(text_box_introduction_text)
            text_box.append_html_text(f"Player {self.current_player}'s turn.\n")
            text_box.append_html_text(f"Turn {self.turn}.\n")


    def use_foxtail(self, player, amount, ui_draw, ui_set_text):
        # The player use this amount of foxtail
        assert amount >= 0
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

    # ====================================
    # UI functions
    # ====================================

    def draw_deck_ui(self, player):
        deck = self.decks[player]
        if not deck:
            return
        if player == 1: # 'top'
            base_x = 1500 - 100 - 50
            base_y = 50
        else:  # 'bottom'
            base_x = 1500 - 100 - 50
            base_y = 900 - 145 - 50
        for i in range(len(deck)):
            offset = i * 1
            card_ui = pygame_gui.elements.UIImage(
                pygame.Rect((base_x + offset, base_y + offset), (100, 145)),
                pygame.Surface((100, 145)),
                ui_manager
            )
            card_ui.set_image(draw_card(deck[i]))
            if i == len(deck) - 1:
                self.top_of_the_deck_ui_marker[player] = card_ui
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
        update_single_card_selection_dropdown_field_options(field)
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

label_leader_1 = pygame_gui.elements.UILabel(pygame.Rect((50, 10), (200, 50)),
                                    "Player 1",
                                    ui_manager)

label_leader_2 = pygame_gui.elements.UILabel(pygame.Rect((50, 900 - 60), (200, 50)),
                                    "Player 2",
                                    ui_manager)

end_turn_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1320, 300), (260, 50)),
                                    text='End Turn',
                                    manager=ui_manager,)

single_card_selection_dropdown_field = pygame_gui.elements.UIDropDownMenu(options_list=[""],
                                                                  starting_option="",
                                                                  relative_rect=pygame.Rect((1320, 360), (260, 50)),
                                                                  manager=ui_manager,)

def update_single_card_selection_dropdown_field_options(options: list[cards.Card]):
    if not options:
        return
    global single_card_selection_dropdown_field
    single_card_selection_dropdown_field.kill()
    card_list: list[str] = [f"{i + 1} {str(card)}" for i, card in enumerate(options)]
    single_card_selection_dropdown_field = pygame_gui.elements.UIDropDownMenu(options_list=card_list, 
                                                                      starting_option=card_list[0],
                                                                      relative_rect=pygame.Rect((1320, 360), (260, 50)),
                                                                      manager=ui_manager,)

settings_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((50, 330), (200, 50)),
                                    text='Settings',
                                    manager=ui_manager,)

new_game_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((50, 390), (200, 50)),
                                    text='New Game',
                                    manager=ui_manager,)


text_box = pygame_gui.elements.UITextEntryBox(pygame.Rect((900, 300), (400, 295)),"", ui_manager)
text_box_introduction_text = "======================================\n"
text_box.set_text(text_box_introduction_text)


def draw_card(card: cards.Card, show_attack_status_indicator: bool = False) -> pygame.Surface:
    card_surface = pygame.Surface((100, 145))
    
    # 強化済みカードは別画像を使用
    if hasattr(card, 'is_enhanced') and card.is_enhanced:
        card_image_key = f"{card.name}_e"
        if card_image_key in image_cards:
            scaled_card_img = pygame.transform.scale(image_cards[card_image_key], (100, 145))
            card_surface.blit(scaled_card_img, (0, 0))
        else:
            scaled_card_img = pygame.transform.scale(image_others["404coyote"], (100, 145))
            card_surface.blit(scaled_card_img, (0, 0))
    elif card.name in image_cards:
        # 通常カード画像
        scaled_card_img = pygame.transform.scale(image_cards[card.name], (100, 145))
        card_surface.blit(scaled_card_img, (0, 0))
    else:
        scaled_card_img = pygame.transform.scale(image_others["404coyote"], (100, 145))
        card_surface.blit(scaled_card_img, (0, 0))
    
    font_bold = pygame.font.Font(None, 32)
    cost_text = str(card.cost)
    for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1), (-2,0), (2,0), (0,-2), (0,2)]:
        cost_outline = font_bold.render(cost_text, True, (0, 0, 0))
        card_surface.blit(cost_outline, (8 + dx, 8 + dy))
    cost_render = font_bold.render(cost_text, True, (255, 215, 0))
    card_surface.blit(cost_render, (8, 8))
    
    if card.type == 'follower':
        attack_text = str(card.attack)
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1), (-2,0), (2,0), (0,-2), (0,2)]:
            attack_outline = font_bold.render(attack_text, True, (0, 0, 0))
            card_surface.blit(attack_outline, (8 + dx, 120 + dy))
        attack_render = font_bold.render(attack_text, True, (255, 50, 50))
        card_surface.blit(attack_render, (8, 120))
        
        hp_text = str(card.hp)
        hp_width = font_bold.size(hp_text)[0]
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1), (-2,0), (2,0), (0,-2), (0,2)]:
            hp_outline = font_bold.render(hp_text, True, (0, 0, 0))
            card_surface.blit(hp_outline, (92 - hp_width + dx, 120 + dy))
        hp_render = font_bold.render(hp_text, True, (50, 255, 50))
        card_surface.blit(hp_render, (92 - hp_width, 120))
    
    if show_attack_status_indicator:  # show can attack status for followers
        if card.type == 'follower':
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
            pygame.draw.rect(card_surface, indicator_color, pygame.Rect(0, 0, 100, 145), 2)
    
    # 強化可能マーカーを右上に表示
    if hasattr(card, 'can_enhance') and card.can_enhance:
        # foxtail_img = pygame.transform.scale(image_others["foxtail"], (24, 24))
        # card_surface.blit(foxtail_img, (68, 0))  # Does not look good. Instead, use word "E"
        enhance_text = "E"
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1), (-2,0), (2,0), (0,-2), (0,2)]:
            enhance_outline = font_bold.render(enhance_text, True, (0, 0, 0))
            card_surface.blit(enhance_outline, (80 + dx, 8 + dy))
        enhance_render = font_bold.render(enhance_text, True, (255, 215, 0))
        card_surface.blit(enhance_render, (80, 8))
    
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


build_component_tooltips()

# =====================================
# Windows & Support Functions
# =====================================

def build_settings_window():
    global theme_selection_menu, settings_window
    try:
        settings_window.kill()
    except Exception as e:
        pass

    def local_translate(s: str) -> str:
        # If ever needed
        return s

    settings_window = pygame_gui.elements.UIWindow(pygame.Rect((500, 300), (400, 200)),
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


settings_window = None
theme_selection_menu = None


def change_theme(theme=None):
    global global_vars_theme
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


global_vars_shcg: SHCGGameState = SHCGGameState(current_player=2)

def start_new_game():
    # fetch decks, deck and deck for cpu are selected by player
    # shuffle decks
    # draw UI components
    example_deck_1: list[cards.Card] = []
    example_deck_2: list[cards.Card] = []
    for i in range(40):
        ゴブリン = cards.ゴブリン()
        ファイター = cards.ファイター()
        ゴリアテ = cards.ゴリアテ()
        ガブリエル = cards.ガブリエル()
        card = random.choice([ゴブリン, ファイター, ゴリアテ, ガブリエル])
        example_deck_1.append(card)

    for i in range(40):
        ゴブリン = cards.ゴブリン()
        ファイター = cards.ファイター()
        ゴリアテ = cards.ゴリアテ()
        ガブリエル = cards.ガブリエル()
        card = random.choice([ゴブリン, ファイター, ゴリアテ, ガブリエル])
        example_deck_2.append(card)

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
    text_box.append_html_text(f"Player {global_vars_shcg.current_player}'s turn. \n")
    text_box.append_html_text(f"Turn {global_vars_shcg.turn}. \n")

    
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
                                global_vars_shcg.play_card(cp, the_selected_card, ui_draw=True, ui_set_text=True)
                                the_selected_card = None
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)

                    elif ui_drag_and_drop_usage == "attack_with_follower_player":
                        # opponent = 2 if cp == 1 else 1
                        opponent = global_vars_shcg.opponent
                        for index, slot in enumerate(global_vars_field_slots[opponent]):
                            if slot.rect.collidepoint(event.pos):
                                if the_selected_card:
                                    target_card = None
                                    if index < len(global_vars_shcg.fields[opponent]):
                                        target_card = global_vars_shcg.fields[opponent][index]
                                    if target_card and target_card.type == 'follower':
                                        global_vars_shcg.follower_attack(cp, the_selected_card, target_card, ui_draw=True, ui_set_text=True)
                        if global_vars_leader_slots[opponent][0].rect.collidepoint(event.pos) and the_selected_card.attack_ability >= 2:
                            global_vars_shcg.follower_attack(cp, the_selected_card, "leader", ui_draw=True, ui_set_text=True)
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)

                    elif ui_drag_and_drop_usage == "use_foxtail_player":
                        if global_vars_shcg.enhance_used_this_turn[cp] >= global_vars_shcg.max_enhance_allowed_per_turn[cp]:
                            text_box.append_html_text(f"All enhance actions of player {cp} used for this turn. \n")
                        else:
                            for index, slot in enumerate(global_vars_field_slots[cp]):
                                if slot.rect.collidepoint(event.pos):
                                    if index < len(global_vars_shcg.fields[cp]):
                                        target_card = global_vars_shcg.fields[cp][index]
                                        if target_card.type == 'follower' and target_card.can_enhance:
                                            target_card.on_enhance_effect(cp)
                                            text_box.append_html_text(f"Player {cp} enhanced {target_card}. \n")
                                            global_vars_shcg.enhance_used_this_turn[cp] += 1
                                            global_vars_shcg.draw_field_ui(cp)
                                            global_vars_shcg.use_foxtail(cp, 1, ui_draw=True, ui_set_text=True)
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
                if event.ui_element == settings_button:
                    build_settings_window()
                if event.ui_element == new_game_button:
                    start_new_game()
                if event.ui_element == end_turn_button:
                    global_vars_shcg.end_turn(ui_draw=True, ui_set_text=True)

            if event.type == pygame_gui.UI_TEXT_BOX_LINK_CLICKED:
                pass

            if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                if event.ui_element == theme_selection_menu:
                    change_theme()

            ui_manager_lower.process_events(event)
            ui_manager.process_events(event)
            ui_manager_overlay.process_events(event)

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
