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

for name in image_files_cards:
    image_path_jpg = f"image/cards/{name}.jpg"
    image_path_png = f"image/cards/{name}.png"
    if os.path.exists(image_path_jpg):
        image_cards[name] = pygame.image.load(image_path_jpg)
    elif os.path.exists(image_path_png):
        image_cards[name] = pygame.image.load(image_path_png)

for name in image_files_leader:
    image_path_jpg = f"image/leader/{name}.jpg"
    image_path_png = f"image/leader/{name}.png"
    if os.path.exists(image_path_jpg):
        image_leader[name] = pygame.image.load(image_path_jpg)
    elif os.path.exists(image_path_png):
        image_leader[name] = pygame.image.load(image_path_png)

for name in image_files_others:
    image_path_jpg = f"image/others/{name}.jpg"
    image_path_png = f"image/others/{name}.png"
    if os.path.exists(image_path_jpg):
        image_others[name] = pygame.image.load(image_path_jpg)
    elif os.path.exists(image_path_png):
        image_others[name] = pygame.image.load(image_path_png)

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


image_slot_leader_1 = pygame_gui.elements.UIImage(pygame.Rect((50, 50), (200, 200)),
                                    pygame.Surface((200, 200)),
                                    ui_manager)
image_slot_leader_1.set_image(image_others["404coyote"])

image_slot_leader_2 = pygame_gui.elements.UIImage(pygame.Rect((50, 900 - 200 - 50), (200, 200)),
                                    pygame.Surface((200, 200)),
                                    ui_manager)
image_slot_leader_2.set_image(image_others["404coyote"])

player_1_hp_slot = pygame_gui.elements.UIImage(pygame.Rect((50, 260), (200, 50)),
                                    pygame.Surface((200, 50)),
                                    ui_manager)

player_2_hp_slot = pygame_gui.elements.UIImage(pygame.Rect((50, 900 - 300), (200, 50)),
                                    pygame.Surface((200, 50)),
                                    ui_manager)

label_leader_1 = pygame_gui.elements.UILabel(pygame.Rect((50, 10), (200, 50)),
                                    "Player 1",
                                    ui_manager)

label_leader_2 = pygame_gui.elements.UILabel(pygame.Rect((50, 900 - 60), (200, 50)),
                                    "Player 2",
                                    ui_manager)

end_turn_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1320, 300), (1600 - 1320 -20, 295)),
                                    text='End Turn',
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


def draw_card(card, show_attack_status_indicator: bool = False) -> pygame.Surface:
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
    
    font = pygame.font.Font(None, 28)
    font_bold = pygame.font.Font(None, 32)
    cost_text = str(card.cost)
    for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1), (-2,0), (2,0), (0,-2), (0,2)]:
        cost_outline = font_bold.render(cost_text, True, (0, 0, 0))
        card_surface.blit(cost_outline, (8 + dx, 8 + dy))
    cost_render = font_bold.render(cost_text, True, (255, 215, 0))
    card_surface.blit(cost_render, (8, 8))
    
    if hasattr(card, 'type') and card.type == 'follower':
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
        if hasattr(card, 'type') and card.type == 'follower':
            if card.can_attack_status == 0:
                # cannot attack, gray
                indicator_color = (150, 150, 150)
            elif card.can_attack_status == 1:
                # can attack follower, yellow
                indicator_color = (255, 255, 50)
            elif card.can_attack_status == 2:
                # can attack player, green
                indicator_color = (50, 255, 50)
            else:
                raise ValueError(f"Unknown can_attack_status: {card.can_attack_status}")
            # outline the card with the indicator color
            pygame.draw.rect(card_surface, indicator_color, pygame.Rect(0, 0, 100, 145), 2)
    
    # 強化可能マーカーを右上に表示
    if hasattr(card, 'can_enhance') and card.can_enhance:
        # foxtail_img = pygame.transform.scale(image_others["foxtail"], (32, 32))
        # card_surface.blit(foxtail_img, (68, 0))  # Does not look good. Instead, use word "E"
        enhance_text = "E"
        for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1), (-2,0), (2,0), (0,-2), (0,2)]:
            enhance_outline = font_bold.render(enhance_text, True, (0, 0, 0))
            card_surface.blit(enhance_outline, (80 + dx, 8 + dy))
        enhance_render = font_bold.render(enhance_text, True, (255, 215, 0))
        card_surface.blit(enhance_render, (80, 8))
    
    return card_surface


# Hand of player (9 slots each)
hand_slots_leader_2 = []
for i in range(9):
    slot = pygame_gui.elements.UIImage(pygame.Rect((300 + i * 110, 700), (100, 145)),
                                        pygame.Surface((100, 145)),
                                        ui_manager)
    slot.set_image(image_others["404coyote"]) # Temporary use 404coyote instead of transparent image
    hand_slots_leader_2.append(slot)

hand_slots_leader_1 = []
for i in range(9):
    slot = pygame_gui.elements.UIImage(pygame.Rect((300 + i * 110, 50), (100, 145)),
                                        pygame.Surface((100, 145)),
                                        ui_manager)
    slot.set_image(image_others["404coyote"])
    hand_slots_leader_1.append(slot)


def draw_hand_ui(player):
    global hand_player_1, hand_player_2
    hand = []
    if player == 1: # 'top'
        hand_player_1 = sorted(hand_player_1, key=lambda x: x.cost)
        hand = hand_player_1
        slots = hand_slots_leader_1
    else:  # 'bottom'
        hand_player_2 = sorted(hand_player_2, key=lambda x: x.cost)
        hand = hand_player_2
        slots = hand_slots_leader_2
    for i in range(9):
        if i < len(hand):
            slots[i].set_image(draw_card(hand[i]))
            slots[i].set_tooltip(hand[i].tooltip_str(), delay=0.1, wrap_width=300)
        else:
            slots[i].set_image(image_405_card_slot)
    return


# Deck (pile of cards) of each player, right bottom and right top next to last hand slot
# In this super hard card game, deck, cards are openly visible to both players

# card on top of the deck is draggable to hand area to draw, so need to mark it
top_of_deck_marker_player_1 = None
top_of_deck_marker_player_2 = None


def draw_deck_ui(player):
    global deck_player_1, deck_player_2
    deck = []
    if player == 1: # 'top'
        base_x = 1500 - 100 - 50
        base_y = 50
        deck = deck_player_1
    else:  # 'bottom'
        base_x = 1500 - 100 - 50
        base_y = 900 - 145 - 50
        deck = deck_player_2
    if not deck:
        return
    for i in range(len(deck)):
        offset = i * 1
        card_ui = pygame_gui.elements.UIImage(
            pygame.Rect((base_x + offset, base_y + offset), (100, 145)),
            pygame.Surface((100, 145)),
            ui_manager
        )
        card_ui.set_image(draw_card(deck[i]))
        if i == len(deck) - 1:
            global top_of_deck_marker_player_1, top_of_deck_marker_player_2
            if player == 1:
                top_of_deck_marker_player_1 = card_ui
            else:
                top_of_deck_marker_player_2 = card_ui
    return


# field slots of each player (5 slots each)
field_slots_leader_1 = []
for i in range(5):
    slot = pygame_gui.elements.UIImage(pygame.Rect((300 + i * 120, 300), (100, 145)),
                                        pygame.Surface((100, 145)),
                                        ui_manager)
    slot.set_image(image_others["404coyote"])
    field_slots_leader_1.append(slot)

field_slots_leader_2 = []
for i in range(5):
    slot = pygame_gui.elements.UIImage(pygame.Rect((300 + i * 120, 450), (100, 145)),
                                        pygame.Surface((100, 145)),
                                        ui_manager)
    slot.set_image(image_others["404coyote"])
    field_slots_leader_2.append(slot)


def draw_field_ui(player):
    # draw cards on field slots, just as draw_hand_ui
    global field_player_1, field_player_2
    field = []
    if player == 1: # 'top'
        field_player_1 = sorted(field_player_1, key=lambda x: x.cost)
        field = field_player_1
        slots = field_slots_leader_1
    else:  # 'bottom'
        field_player_2 = sorted(field_player_2, key=lambda x: x.cost)
        field = field_player_2
        slots = field_slots_leader_2
    for i in range(5):
        if i < len(field):
            slots[i].set_image(draw_card(field[i], show_attack_status_indicator=True))
            slots[i].set_tooltip(field[i].tooltip_str(), delay=0.1, wrap_width=300)
        else:
            slots[i].set_image(image_405_card_slot)
    return


# Tail indicators (how many foxtail this player have currently), just above hand slots, from left to right, 32 x 32, max 9
tail_indicators_leader_1 = []
tail_indicators_leader_1_active = []
for i in range(9):
    indicator = pygame_gui.elements.UIImage(pygame.Rect((300 + i * 40, 200 + 20), (32, 32)),
                                        pygame.Surface((32, 32)),
                                        ui_manager)
    indicator.set_image(image_others["405"])
    tail_indicators_leader_1.append(indicator)

tail_indicators_leader_2 = []
tail_indicators_leader_2_active = []
for i in range(9):
    indicator = pygame_gui.elements.UIImage(pygame.Rect((300 + i * 40, 700 - 20 - 32), (32, 32)),
                                        pygame.Surface((32, 32)),
                                        ui_manager)
    indicator.set_image(image_others["405"])
    tail_indicators_leader_2.append(indicator)


def draw_tail_ui(player):
    # fill tail indicators to default value (9) according to foxtail count
    global foxtail_player_1, foxtail_player_2
    global tail_indicators_leader_1, tail_indicators_leader_2
    global tail_indicators_leader_1_active, tail_indicators_leader_2_active
    foxtail = 0
    if player == 1:
        foxtail = foxtail_player_1
        indicators = tail_indicators_leader_1
        tail_indicators_leader_1_active = []
    else:
        foxtail = foxtail_player_2
        indicators = tail_indicators_leader_2
        tail_indicators_leader_2_active = []
    for i in range(9):
        if i < foxtail:
            indicators[i].set_image(image_others["foxtail"])  # filled
            if player == 1:
                tail_indicators_leader_1_active.append(indicators[i])
            else:
                tail_indicators_leader_2_active.append(indicators[i])
        else:
            indicators[i].set_image(image_others["405"])  # empty
    return


def use_foxtail(player, amount):
    # use amount of foxtail for player without redrawing UI
    # also includes error checking
    assert amount >= 0
    if amount == 0:
        return
    global foxtail_player_1, foxtail_player_2
    global tail_indicators_leader_1, tail_indicators_leader_2
    global tail_indicators_leader_1_active, tail_indicators_leader_2_active
    if player == 1:
        foxtail_prev = foxtail_player_1
        if foxtail_player_1 >= amount:
            foxtail_player_1 -= amount
            for i in range(foxtail_player_1, foxtail_prev):
                tail_indicators_leader_1[i].set_image(image_others["405"])
                tail_indicators_leader_1_active.remove(tail_indicators_leader_1[i])
        else:
            raise ValueError("Not enough foxtail")
    else:
        foxtail_prev = foxtail_player_2
        if foxtail_player_2 >= amount:
            foxtail_player_2 -= amount
            for i in range(foxtail_player_2, foxtail_prev):
                tail_indicators_leader_2[i].set_image(image_others["405"])
                tail_indicators_leader_2_active.remove(tail_indicators_leader_2[i])
        else:
            raise ValueError("Not enough foxtail")


def add_foxtail(player, amount):
    # add amount of foxtail for player without redrawing UI
    # also includes error checking
    assert amount >= 0
    if amount == 0:
        return
    global foxtail_player_1, foxtail_player_2
    global tail_indicators_leader_1, tail_indicators_leader_2
    global tail_indicators_leader_1_active, tail_indicators_leader_2_active
    if player == 1:
        foxtail_prev = foxtail_player_1
        if foxtail_player_1 + amount <= 9:
            foxtail_player_1 += amount
        for i in range(foxtail_prev, foxtail_player_1):
            tail_indicators_leader_1[i].set_image(image_others["foxtail"])
            tail_indicators_leader_1_active.append(tail_indicators_leader_1[i])
        else:
            foxtail_player_1 = 9
            draw_tail_ui(1)
    else:
        foxtail_prev = foxtail_player_2
        if foxtail_player_2 + amount <= 9:
            foxtail_player_2 += amount
        for i in range(foxtail_prev, foxtail_player_2):
            tail_indicators_leader_2[i].set_image(image_others["foxtail"])
            tail_indicators_leader_2_active.append(tail_indicators_leader_2[i])
        else:
            foxtail_player_2 = 9
            draw_tail_ui(2)


def draw_player_hp_ui():
    # draw player hp on player_1_hp_slot and player_2_hp_slot
    # green text, bold font
    global player_hp_1, player_hp_2
    font_bold = pygame.font.Font(None, 64)
    
    # player 1
    hp_text_1 = str(player_hp_1)
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
    hp_text_2 = str(player_hp_2)
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
# End of Example UI Components
# =====================================
# Component tooltips
# =====================================

def build_component_tooltips():
    """
    All tooltips here. Delay should always be 0.1
    """
    image_slot_leader_1.set_tooltip("Example tooltip.", delay=0.1, wrap_width=300)
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
    if theme:
        global_vars_theme = theme
    else:
        global_vars_theme = theme_selection_menu.selected_option[0]
    if global_vars_theme == "Yellow Theme":
        ui_manager_lower.get_theme().load_theme("theme_light_yellow.json")
        ui_manager.get_theme().load_theme("theme_light_yellow.json")
        ui_manager_overlay.get_theme().load_theme("theme_light_yellow.json")
    elif global_vars_theme == "Purple Theme":
        ui_manager_lower.get_theme().load_theme("theme_light_purple.json")
        ui_manager.get_theme().load_theme("theme_light_purple.json")
        ui_manager_overlay.get_theme().load_theme("theme_light_purple.json")
    elif global_vars_theme == "Red Theme":
        ui_manager_lower.get_theme().load_theme("theme_light_red.json")
        ui_manager.get_theme().load_theme("theme_light_red.json")
        ui_manager_overlay.get_theme().load_theme("theme_light_red.json")
    elif global_vars_theme == "Blue Theme":
        ui_manager_lower.get_theme().load_theme("theme_light_blue.json")
        ui_manager.get_theme().load_theme("theme_light_blue.json")
        ui_manager_overlay.get_theme().load_theme("theme_light_blue.json")
    elif global_vars_theme == "Green Theme":
        ui_manager_lower.get_theme().load_theme("theme_light_green.json")
        ui_manager.get_theme().load_theme("theme_light_green.json")
        ui_manager_overlay.get_theme().load_theme("theme_light_green.json")
    elif global_vars_theme == "Pink Theme":
        ui_manager_lower.get_theme().load_theme("theme_light_pink.json")
        ui_manager.get_theme().load_theme("theme_light_pink.json")
        ui_manager_overlay.get_theme().load_theme("theme_light_pink.json")
    else:
        raise ValueError(f"Unknown theme: {global_vars_theme}")
    
    ui_manager_lower.rebuild_all_from_changed_theme_data()
    ui_manager.rebuild_all_from_changed_theme_data()
    ui_manager_overlay.rebuild_all_from_changed_theme_data()
    build_component_tooltips() # This is needed as theme switching resets tooltips delay and wrap width



card_selection_window = None
card_selection_checkboxes: list[tuple[pygame_gui.elements.UICheckBox, cards.Card]] = []
csw_confirm_button = None

def build_selection_window(card_list: list[cards.Card]):
    """
    Some cards, when activating effect, may require selection from card or field
    A window, draw cards, use UICheckBox, button to confirm selection
    """
    global card_selection_window, card_selection_checkboxes, csw_confirm_button
    
    try:
        card_selection_window.kill()
    except Exception:
        pass
    
    card_selection_window = pygame_gui.elements.UIWindow(
        pygame.Rect((400, 200), (800, 500)),
        ui_manager_overlay,
        window_display_title="Select Card",
        object_id="#card_selection_window",
        resizable=False
    )
    
    # Store checkboxes for later reference
    card_selection_checkboxes = []
    
    # Layout settings
    cards_per_row = 4
    checkbox_width = 30
    checkbox_height = 30
    padding_x = 150
    padding_y = 10
    start_x = 10
    start_y = 10
    
    for i, card in enumerate(card_list):
        # Calculate grid position
        row = i // cards_per_row
        col = i % cards_per_row
        
        x = start_x + col * (checkbox_width + padding_x)
        y = start_y + row * (checkbox_height + padding_y)
        
        checkbox = pygame_gui.elements.UICheckBox(
            pygame.Rect((x, y), (checkbox_width, checkbox_height)),
            str(card),
            ui_manager_overlay,
            container=card_selection_window
        )
        # checkbox.set_tooltip(card.tooltip_str, delay=0.1, wrap_width=300) # Does not work
        
        # Store reference to checkbox and associated card
        card_selection_checkboxes.append((checkbox, card))
    
    # Confirm button at bottom right
    csw_confirm_button = pygame_gui.elements.UIButton(
        pygame.Rect((600, 410), (180, 40)),
        text='Confirm Selection',
        manager=ui_manager_overlay,
        container=card_selection_window,
        object_id="#csw_confirm_button"
    )
    


def csw_get_selected_cards() -> list[cards.Card]:
    """
    Returns list of cards that were selected via checkboxes
    """
    global card_selection_checkboxes
    selected = []
    for checkbox, card in card_selection_checkboxes:
        if checkbox.is_checked:
            selected.append(card)
    return selected



deck_player_1: list[cards.Card] = []
deck_player_2: list[cards.Card] = []
hand_player_1: list[cards.Card] = []
hand_player_2: list[cards.Card] = []
field_player_1: list[cards.Card] = []
field_player_2: list[cards.Card] = []
foxtail_player_1: int = 9 # foxtail is used as cost resource
foxtail_player_2: int = 9
current_player: int = 2  # 1 or 2
player_hp_1: int = 20
player_hp_2: int = 20
game_turn: int = 1
game_concluded: bool = False
player_1_max_enhance_turns: int = 1
player_2_max_enhance_turns: int = 1
player_1_enhance_used_this_turn: int = 0
player_2_enhance_used_this_turn: int = 0

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
        card = random.choice([ゴブリン, ファイター, ゴリアテ])
        example_deck_1.append(card)

    for i in range(40):
        ゴブリン = cards.ゴブリン()
        ファイター = cards.ファイター()
        ゴリアテ = cards.ゴリアテ()
        card = random.choice([ゴブリン, ファイター, ゴリアテ])
        example_deck_2.append(card)

    text_box.set_text(text_box_introduction_text)

    global deck_player_1, deck_player_2
    deck_player_1 = example_deck_1.copy()
    deck_player_2 = example_deck_2.copy()

    random.shuffle(deck_player_1)
    random.shuffle(deck_player_2)

    global hand_player_1, hand_player_2, foxtail_player_1, foxtail_player_2
    global field_player_1, field_player_2, current_player
    global player_hp_1, player_hp_2, game_turn, game_concluded
    global player_1_max_enhance_turns, player_2_max_enhance_turns
    hand_player_1 = []
    hand_player_2 = []
    foxtail_player_1 = 9
    foxtail_player_2 = 9
    current_player = 2
    player_hp_1 = 20
    player_hp_2 = 20
    draw_player_hp_ui()
    game_turn = 1
    game_concluded = False
    player_1_max_enhance_turns = 1
    player_2_max_enhance_turns = 1
    field_player_1 = []
    field_player_2 = []
    # draw UI
    draw_tail_ui(1)
    draw_tail_ui(2)
    # draw hand
    draw_hand_ui(1)
    draw_hand_ui(2)
    # draw deck
    draw_deck_ui(1)
    draw_deck_ui(2)
    # draw field
    draw_field_ui(1)
    draw_field_ui(2)
    text_box.append_html_text(f"Player {current_player}'s turn. \n")
    text_box.append_html_text(f"Turn {game_turn}. \n")

    
start_new_game()


def draw_card_tail(player):
    # comsume 1 foxtail to draw a card
    global deck_player_1, deck_player_2, hand_player_1, hand_player_2
    if player == 1 and len(hand_player_1) >= 9:
        text_box.append_html_text(f"Player 1's hand is full. Cannot draw a card. \n")
        return
    if player == 2 and len(hand_player_2) >= 9:
        text_box.append_html_text(f"Player 2's hand is full. Cannot draw a card. \n")
        return
    if foxtail_player_1 > 0 and player == 1:
        use_foxtail(player, 1)
    elif foxtail_player_2 > 0 and player == 2:
        use_foxtail(player, 1)
    else:
        text_box.append_html_text(f"Player {player} does not have enough foxtail to draw a card. \n")
        return
    if player == 1:
        if deck_player_1:
            drawn_card = deck_player_1.pop()
            hand_player_1.append(drawn_card)
            draw_hand_ui(1)
            text_box.append_html_text(f"Player 1 drew a card: {drawn_card}. \n")
        else:
            text_box.append_html_text(f"Player 1's deck is empty. Cannot draw a card. \n")
    else:
        if deck_player_2:
            drawn_card = deck_player_2.pop()
            hand_player_2.append(drawn_card)
            draw_hand_ui(2)
            text_box.append_html_text(f"Player 2 drew a card: {drawn_card}. \n")
        else:
            text_box.append_html_text(f"Player 2's deck is empty. Cannot draw a card. \n")


def assign_card_to_field_from_hand(player, card: cards.Card):
    global hand_player_1, hand_player_2, field_player_1, field_player_2
    # remove from hand, add to field
    if player == 1 and len(field_player_1) <= 4:
        if foxtail_player_1 >= card.cost:
            use_foxtail(1, card.cost)
            hand_player_1.remove(card)
            if card.type == 'follower':
                card.summoned_this_turn = True
            text_box.append_html_text(f"Player 1 played {card}. \n")
            field_player_1.append(card)
            draw_hand_ui(1)
            draw_field_ui(1)
        else:
            text_box.append_html_text(f"Player 1 does not have enough foxtail to play {card}. \n")
            return
    elif player == 2 and len(field_player_2) <= 4:
        if foxtail_player_2 >= card.cost:
            use_foxtail(2, card.cost)
            hand_player_2.remove(card)
            if card.type == 'follower':
                card.summoned_this_turn = True
            text_box.append_html_text(f"Player 2 played {card}. \n")
            field_player_2.append(card)
            draw_hand_ui(2)
            draw_field_ui(2)
        else:
            text_box.append_html_text(f"Player 2 does not have enough foxtail to play {card.name}. \n")
            return
    else:
        return


def attack_with_follower(player, attacker: cards.Follower, target: cards.Follower | str):
    global field_player_1, field_player_2, player_hp_1, player_hp_2
    if player == 1:
        if attacker not in field_player_1:
            text_box.append_html_text(f"Player 1's attacker is not on the field. \n")
            return
        if isinstance(target, cards.Follower):
            if target not in field_player_2:
                text_box.append_html_text(f"Player 2's target is not on the field. \n")
                return
            else:
                # attack follower
                text_box.append_html_text(f"{attacker} is about to attack {target}. \n")
                target.hp -= attacker.attack
                attacker.hp -= target.attack
                if target.hp <= 0:
                    field_player_2.remove(target)
                    text_box.append_html_text(f"Player 2's {target} was destroyed. \n")
                if attacker.hp <= 0:
                    field_player_1.remove(attacker)
                    text_box.append_html_text(f"Player 1's {attacker} was destroyed. \n")
                attacker.update_can_attack_status()
                draw_field_ui(1)
                draw_field_ui(2)
        elif target == "leader":
            player_take_damage(2, attacker.attack)
            attacker.update_can_attack_status()
            draw_field_ui(1)
        else:
            text_box.append_html_text(f"Invalid target for attack. \n")
            return
    else:
        if attacker not in field_player_2:
            text_box.append_html_text(f"Player 2's attacker is not on the field. \n")
            return
        if isinstance(target, cards.Follower):
            if target not in field_player_1:
                text_box.append_html_text(f"Player 1's target is not on the field. \n")
                return
            # attack follower
            text_box.append_html_text(f"{attacker} is about to attack {target}. \n")
            target.hp -= attacker.attack
            attacker.hp -= target.attack
            if target.hp <= 0:
                field_player_1.remove(target)
                text_box.append_html_text(f"Player 1's {target} was destroyed. \n")
            if attacker.hp <= 0:
                field_player_2.remove(attacker)
                text_box.append_html_text(f"Player 2's {attacker} was destroyed. \n")
            attacker.update_can_attack_status()
            draw_field_ui(1)
            draw_field_ui(2)
        elif target == "leader":
            player_take_damage(1, attacker.attack)
            attacker.update_can_attack_status()
            draw_field_ui(2)
        else:
            text_box.append_html_text(f"Invalid target for attack. \n")
            return


def player_take_damage(player: int, amount: int):
    global player_hp_1, player_hp_2, game_concluded
    assert amount >= 0
    if player == 1:
        player_hp_1 -= amount
        text_box.append_html_text(f"Player 1 took {amount} damage, remaining HP: {player_hp_1}. \n")
        if amount > 0:
            draw_player_hp_ui()
    else:
        player_hp_2 -= amount
        text_box.append_html_text(f"Player 2 took {amount} damage, remaining HP: {player_hp_2}. \n")
        if amount > 0:
            draw_player_hp_ui()
    if player_hp_1 <= 0:
        text_box.append_html_text(f"Player 2 wins! \n")
        game_concluded = True
    elif player_hp_2 <= 0:
        text_box.append_html_text(f"Player 1 wins! \n")
        game_concluded = True



def end_turn_and_switch_player():
    global current_player, foxtail_player_1, foxtail_player_2, game_turn
    global player_1_enhance_used_this_turn, player_2_enhance_used_this_turn
    if game_concluded:
        text_box.append_html_text("The game has concluded. Start a new game instead.\n")
        return
    if current_player == 1:
        current_player = 2
        foxtail_player_2 = 9
        draw_tail_ui(2)
        for card in field_player_2:
            if card.type == 'follower':
                card.summoned_this_turn = False
                card.reset_attack_status()
    else:
        current_player = 1
        foxtail_player_1 = 9
        draw_tail_ui(1)
        # reset followers' can attack status
        for card in field_player_1:
            if card.type == 'follower':
                card.summoned_this_turn = False
                card.reset_attack_status()

    draw_field_ui(1)
    draw_field_ui(2)
    game_turn += 1
    player_1_enhance_used_this_turn = 0
    player_2_enhance_used_this_turn = 0
    text_box.set_text(text_box_introduction_text)
    text_box.append_html_text(f"Player {current_player}'s turn. \n")
    text_box.append_html_text(f"Turn {game_turn}. \n")






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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not game_concluded:
                if current_player == 1:
                    if top_of_deck_marker_player_1 and top_of_deck_marker_player_1.rect.collidepoint(event.pos):
                        ui_drag_and_drop_target_orig_pos = (top_of_deck_marker_player_1.rect.x, image_slot_leader_1.rect.y)
                        ui_drag_and_drop_usage = "draw_card_player_1"
                        ui_drag_and_drop_target = top_of_deck_marker_player_1
                    for index, card_slot in enumerate(hand_slots_leader_1):
                        if card_slot.rect.collidepoint(event.pos):
                            # find which card in hand this is
                            if index < len(hand_player_1):
                                the_selected_card = hand_player_1[index]
                            ui_drag_and_drop_target_orig_pos = (card_slot.rect.x, card_slot.rect.y)
                            ui_drag_and_drop_usage = "play_card_player_1"
                            ui_drag_and_drop_target = card_slot
                    # follower on field if can attack, can be dragged to opponent followers or leader to attack
                    for index, card_slot in enumerate(field_slots_leader_1):
                        if card_slot.rect.collidepoint(event.pos):
                            # find which card on field this is
                            if index < len(field_player_1):
                                the_selected_card = field_player_1[index]
                            if the_selected_card and the_selected_card.type == 'follower' and the_selected_card.can_attack_status > 0:
                                ui_drag_and_drop_target_orig_pos = (card_slot.rect.x, card_slot.rect.y)
                                ui_drag_and_drop_usage = "attack_with_follower_player_1"
                                ui_drag_and_drop_target = card_slot
                    for index, tail in enumerate(tail_indicators_leader_1_active):
                        if tail.rect.collidepoint(event.pos):
                            ui_drag_and_drop_target_orig_pos = (tail.rect.x, tail.rect.y)
                            ui_drag_and_drop_usage = "use_foxtail_player_1"
                            ui_drag_and_drop_target = tail

                elif current_player == 2:
                    if top_of_deck_marker_player_2 and top_of_deck_marker_player_2.rect.collidepoint(event.pos):
                        ui_drag_and_drop_target_orig_pos = (top_of_deck_marker_player_2.rect.x, image_slot_leader_2.rect.y)
                        ui_drag_and_drop_usage = "draw_card_player_2"
                        ui_drag_and_drop_target = top_of_deck_marker_player_2
                    for index, card_slot in enumerate(hand_slots_leader_2):
                        if card_slot.rect.collidepoint(event.pos):
                            # find which card in hand this is
                            if index < len(hand_player_2):
                                the_selected_card = hand_player_2[index]
                                print(f"Selected card: {the_selected_card.name}")
                                print(f"Index on hand: {index}")
                                print(hand_player_2)
                            ui_drag_and_drop_target_orig_pos = (card_slot.rect.x, card_slot.rect.y)
                            ui_drag_and_drop_usage = "play_card_player_2"
                            ui_drag_and_drop_target = card_slot
                    # follower on field if can attack, can be dragged to opponent followers or leader to attack
                    for index, card_slot in enumerate(field_slots_leader_2):
                        if card_slot.rect.collidepoint(event.pos):
                            # find which card on field this is
                            if index < len(field_player_2):
                                the_selected_card = field_player_2[index]
                            if the_selected_card and the_selected_card.type == 'follower' and the_selected_card.can_attack_status > 0:
                                ui_drag_and_drop_target_orig_pos = (card_slot.rect.x, card_slot.rect.y)
                                ui_drag_and_drop_usage = "attack_with_follower_player_2"
                                ui_drag_and_drop_target = card_slot
                    for index, tail in enumerate(tail_indicators_leader_2_active):
                        if tail.rect.collidepoint(event.pos):
                            ui_drag_and_drop_target_orig_pos = (tail.rect.x, tail.rect.y)
                            ui_drag_and_drop_usage = "use_foxtail_player_2"
                            ui_drag_and_drop_target = tail

            if event.type == pygame.MOUSEBUTTONUP:
                # drag and drop
                if ui_drag_and_drop_target != None:
                    if ui_drag_and_drop_usage == "draw_card_player_1":
                        # if collide with any hand slot of player 1, call draw card
                        if any([slot.rect.colliderect(ui_drag_and_drop_target.rect) for slot in hand_slots_leader_1]):
                            draw_card_tail(1)
                        ui_drag_and_drop_target.kill()
                        draw_deck_ui(1)
                    elif ui_drag_and_drop_usage == "draw_card_player_2":
                        if any([slot.rect.colliderect(ui_drag_and_drop_target.rect) for slot in hand_slots_leader_2]):
                            draw_card_tail(2)
                        ui_drag_and_drop_target.kill()
                        draw_deck_ui(2)
                    elif ui_drag_and_drop_usage == "play_card_player_1":
                        # if collide with any field slot of player 1, call assign card to field from hand
                        if any([slot.rect.colliderect(ui_drag_and_drop_target.rect) for slot in field_slots_leader_1]):
                            if the_selected_card:
                                assign_card_to_field_from_hand(1, the_selected_card)
                                the_selected_card = None
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)
                    elif ui_drag_and_drop_usage == "play_card_player_2":
                        if any([slot.rect.colliderect(ui_drag_and_drop_target.rect) for slot in field_slots_leader_2]):
                            if the_selected_card:
                                assign_card_to_field_from_hand(2, the_selected_card)
                                the_selected_card = None
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)
                    elif ui_drag_and_drop_usage == "attack_with_follower_player_1":
                        # if collide with any opponent field slot or leader, call attack with follower
                        for index, slot in enumerate(field_slots_leader_2):
                            if slot.rect.collidepoint(event.pos):
                                if the_selected_card:
                                    target_card = None
                                    if index < len(field_player_2):
                                        target_card = field_player_2[index]
                                    if target_card and target_card.type == 'follower':
                                        attack_with_follower(1, the_selected_card, target_card)
                        if image_slot_leader_2.rect.collidepoint(event.pos) and the_selected_card.can_attack_status >= 2:
                            attack_with_follower(1, the_selected_card, "leader")
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)
                    elif ui_drag_and_drop_usage == "attack_with_follower_player_2":
                        for index, slot in enumerate(field_slots_leader_1):
                            if slot.rect.collidepoint(event.pos):
                                if the_selected_card:
                                    target_card = None
                                    if index < len(field_player_1):
                                        target_card = field_player_1[index]
                                    if target_card and target_card.type == 'follower':
                                        attack_with_follower(2, the_selected_card, target_card)
                        if image_slot_leader_1.rect.collidepoint(event.pos) and the_selected_card.can_attack_status >= 2:
                            attack_with_follower(2, the_selected_card, "leader")
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)
                    elif ui_drag_and_drop_usage == "use_foxtail_player_1":
                        if player_1_enhance_used_this_turn >= player_1_max_enhance_turns:
                            text_box.append_html_text("All enhance actions of player 1 used for this turn. \n")
                        else:
                            # if any enhanceable follower on field, call enhance on that card
                            for index, slot in enumerate(field_slots_leader_1):
                                if slot.rect.collidepoint(event.pos):
                                    if index < len(field_player_1):
                                        target_card = field_player_1[index]
                                        if target_card.type == 'follower' and target_card.can_enhance:
                                            target_card.enhance()
                                            text_box.append_html_text(f"Player 1 enhanced {target_card}. \n")
                                            player_1_enhance_used_this_turn += 1
                                            draw_field_ui(1)
                                            use_foxtail(1, 1)
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)
                    elif ui_drag_and_drop_usage == "use_foxtail_player_2":
                        if player_2_enhance_used_this_turn >= player_2_max_enhance_turns:
                            text_box.append_html_text("All enhance actions of player 2 used for this turn. \n")
                        else:
                            for index, slot in enumerate(field_slots_leader_2):
                                if slot.rect.collidepoint(event.pos):
                                    if index < len(field_player_2):
                                        target_card = field_player_2[index]
                                        if target_card.type == 'follower' and target_card.can_enhance:
                                            target_card.enhance()
                                            text_box.append_html_text(f"Player 2 enhanced {target_card}. \n")
                                            player_2_enhance_used_this_turn += 1
                                            draw_field_ui(2)
                                            use_foxtail(2, 1)
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
                    end_turn_and_switch_player()
                if event.ui_element == csw_confirm_button:
                    selected_cards = csw_get_selected_cards()
                    text_box.append_html_text(f"Selected cards: {', '.join(str(card) for card in selected_cards)}. \n")
                    card_selection_window.kill()

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
