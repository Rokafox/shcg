import os
import json
import more_itertools as mit
import itertools
import datetime
import pygame, pygame_gui
from pygame_gui.windows import UIFileDialog
import shcg_core_cards
import random
import shcg_ai
import shcg_ui_deck_builder
import shcg_ui_zone_viewer
import shcg_ui_debug
from shcg_core_gamestate import SHCGGameState


pygame.init()
clock = pygame.time.Clock()


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
# UI Components A
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

reset_turn_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1320, 355), (260, 50)),
                                    text='Reset Turn',
                                    manager=ui_manager,)

save_game_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1320, 410), (260, 50)),
                                    text='Save Game State',
                                    manager=ui_manager,)

load_game_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1320, 465), (260, 50)),
                                    text='Load Game State',
                                    manager=ui_manager,)

load_game_file_dialog: UIFileDialog | None = None

# State saved at the start of each turn, used by Reset Turn
_turn_start_state_string: str | None = None


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


# =====================================
# End of UI Components A
# =====================================
# UI Component B
# =====================================

card_selection_window = None
card_selection_lists: list = []  # list of UISelectionList, one per step in request_card_selection_on_play/enhance
multi_card_selection_list = None
effect_selection_list = None
card_selection_confirm_button = None
card_selection_cancel_button = None
pending_selection_action = None  # dict with pending play/enhance action info
_card_selection_option_maps: list[dict[str, shcg_core_cards.Card]] = []  # list of option maps, one per step
_multi_card_selection_option_map: dict[str, shcg_core_cards.Card] = {}  # display string -> card object (multi select)


def _build_card_selection_options(selection_type: str, pending_info: dict,
                                   target_map: dict[str, shcg_core_cards.Card] | None = None) -> list[str]:
    """Build display strings for the card selection list and populate the option map.
    If target_map is provided, populate that dict. Otherwise use a throwaway local dict.
    """
    if target_map is not None:
        target_map.clear()
        om = target_map
    else:
        om = {}

    cp = global_vars_shcg.current_player
    op = 3 - cp
    played_card = pending_info.get('card')
    action_type = pending_info.get('type')  # 'play' or 'enhance'

    options: list[str] = []

    if selection_type == "field":
        for i, c in enumerate(global_vars_shcg.fields[cp]):
            if isinstance(c, shcg_core_cards.Follower):
                display = f"{i + 1} {str(c)}"
                options.append(display)
                om[display] = c

    elif selection_type == "field_opponent":
        for i, c in enumerate(global_vars_shcg.fields[op]):
            if isinstance(c, shcg_core_cards.Follower):
                display = f"{i + 1} {str(c)}"
                options.append(display)
                om[display] = c

    elif selection_type == "field_both":
        for i, c in enumerate(global_vars_shcg.fields[cp]):
            if isinstance(c, shcg_core_cards.Follower):
                display = f"CP {i + 1} {str(c)}"
                options.append(display)
                om[display] = c
        for i, c in enumerate(global_vars_shcg.fields[op]):
            if isinstance(c, shcg_core_cards.Follower):
                display = f"OP {i + 1} {str(c)}"
                options.append(display)
                om[display] = c

    elif selection_type == "hand":
        for i, c in enumerate(global_vars_shcg.hands[cp]):
            if action_type == 'play' and c is played_card:
                continue
            display = f"{i + 1} {str(c)}"
            options.append(display)
            om[display] = c

    elif selection_type == "hand_follower":
        for i, c in enumerate(global_vars_shcg.hands[cp]):
            if action_type == 'play' and c is played_card:
                continue
            if isinstance(c, shcg_core_cards.Follower):
                display = f"{i + 1} {str(c)}"
                options.append(display)
                om[display] = c

    elif selection_type == "hand_spell":
        for i, c in enumerate(global_vars_shcg.hands[cp]):
            if action_type == 'play' and c is played_card:
                continue
            if isinstance(c, shcg_core_cards.Spell):
                display = f"{i + 1} {str(c)}"
                options.append(display)
                om[display] = c

    elif selection_type == "hand_follower_aiteru":
        hand_after = [c for c in global_vars_shcg.hands[cp] if c is not played_card]
        num_followers = len([c for c in hand_after if c.type == 'follower'])
        for i, c in enumerate(hand_after):
            if c.type == 'follower' and c.cost <= num_followers:
                display = f"{i + 1} {str(c)}"
                options.append(display)
                om[display] = c

    elif selection_type == "field_c":
        for i, c in enumerate(global_vars_shcg.fields[cp]):
            display = f"{i + 1} {str(c)}"
            options.append(display)
            om[display] = c

    elif selection_type == "field_opponent_c":
        for i, c in enumerate(global_vars_shcg.fields[op]):
            display = f"{i + 1} {str(c)}"
            options.append(display)
            om[display] = c

    elif selection_type == "field_both_c":
        for i, c in enumerate(global_vars_shcg.fields[cp]):
            display = f"CP {i + 1} {str(c)}"
            options.append(display)
            om[display] = c
        for i, c in enumerate(global_vars_shcg.fields[op]):
            display = f"OP {i + 1} {str(c)}"
            options.append(display)
            om[display] = c

    elif selection_type == "hand_opponent":
        for i, c in enumerate(global_vars_shcg.hands[op]):
            display = f"{i + 1} {str(c)}"
            options.append(display)
            om[display] = c

    return options


def build_card_selection_window(pending_info: dict):
    """Open a window for the player to select target cards and/or effect choice.
    needs_card_selection is now a list[str] where each element is one selection step."""
    global card_selection_window, card_selection_lists, multi_card_selection_list, effect_selection_list
    global card_selection_confirm_button, card_selection_cancel_button
    global pending_selection_action, _card_selection_option_maps, _multi_card_selection_option_map

    pending_selection_action = pending_info

    if card_selection_window:
        card_selection_window.kill()

    card_sel_types = pending_info.get('needs_card_selection', [])
    multi_sel = pending_info.get('needs_multi_card_selection', ('', 0))
    effect_options = pending_info.get('needs_effect_choice', [])

    # Compute per-step card selection options
    step_options_list = []  # list of (options, option_map) per step
    for sel_type in card_sel_types:
        option_map = {}
        options = _build_card_selection_options(sel_type, pending_info, target_map=option_map)
        step_options_list.append((options, option_map))

    # Compute multi-select card options (populates _multi_card_selection_option_map)
    multi_card_options = []
    if multi_sel[0]:
        multi_card_options = _build_card_selection_options(multi_sel[0], pending_info,
                                                           target_map=_multi_card_selection_option_map)

    # Compute window height dynamically
    y_offset = 10
    win_height = 80  # base for buttons + padding
    for options, _ in step_options_list:
        if options:
            win_height += 30 + min(len(options) * 25, 200) + 10
    if multi_card_options:
        win_height += 30 + min(len(multi_card_options) * 25, 200) + 10
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

    card_selection_lists = []
    _card_selection_option_maps = []
    multi_card_selection_list = None
    effect_selection_list = None

    # Per-step single-select lists
    for i, (options, option_map) in enumerate(step_options_list):
        _card_selection_option_maps.append(option_map)
        if options:
            step_num = i + 1
            label_text = f"ターゲット{step_num}を選択："
            if len(card_sel_types) == 1:
                label_text = "ターゲットを選択："
            pygame_gui.elements.UILabel(
                pygame.Rect((10, y_offset), (380, 25)),
                label_text,
                ui_manager,
                container=card_selection_window
            )
            y_offset += 30
            list_height = min(len(options) * 25, 200)
            sel_list = pygame_gui.elements.UISelectionList(
                pygame.Rect((10, y_offset), (380, list_height)),
                options,
                ui_manager,
                container=card_selection_window,
                allow_multi_select=False
            )
            card_selection_lists.append(sel_list)
            y_offset += list_height + 10
        else:
            card_selection_lists.append(None)

    # Multi-select list
    if multi_card_options:
        max_count = multi_sel[1]
        pygame_gui.elements.UILabel(
            pygame.Rect((10, y_offset), (380, 25)),
            f"複数ターゲットを選択（最大{max_count}体）：",
            ui_manager,
            container=card_selection_window
        )
        y_offset += 30
        list_height = min(len(multi_card_options) * 25, 200)
        multi_card_selection_list = pygame_gui.elements.UISelectionList(
            pygame.Rect((10, y_offset), (380, list_height)),
            multi_card_options,
            ui_manager,
            container=card_selection_window,
            allow_multi_select=True
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

    selected_targets = None
    selected_multi_targets = None
    selected_effect = None

    card_sel_types = info.get('needs_card_selection', [])
    card_required = bool(card_sel_types)
    multi_sel = info.get('needs_multi_card_selection', ('', 0))
    multi_card_required = bool(multi_sel[0])
    effect_required = bool(info.get('needs_effect_choice'))
    single_ok = not card_required
    multi_ok = not multi_card_required
    effect_ok = not effect_required

    # Read per-step card selections
    if card_required and card_selection_lists:
        targets_list = []
        all_steps_ok = True
        for i, sl in enumerate(card_selection_lists):
            if sl is not None:
                selected_str = sl.get_single_selection()
                if selected_str and i < len(_card_selection_option_maps) and selected_str in _card_selection_option_maps[i]:
                    targets_list.append(_card_selection_option_maps[i][selected_str])
                else:
                    all_steps_ok = False
                    break
            else:
                # No valid targets for this step, set to None
                targets_list.append(None)
        if all_steps_ok and len(targets_list) == len(card_sel_types):
            selected_targets = targets_list
            single_ok = True
        else:
            single_ok = False

    # Read multi-card selection (independent from per-step)
    if multi_card_required:
        if multi_card_selection_list:
            max_count = multi_sel[1]
            selected_strs = multi_card_selection_list.get_multi_selection()
            if selected_strs and 0 < len(selected_strs) <= max_count:
                selected_multi_targets = [_multi_card_selection_option_map[s] for s in selected_strs if s in _multi_card_selection_option_map]
                multi_ok = len(selected_multi_targets) > 0
            else:
                multi_ok = False
        else:
            # but no options to select
            multi_ok = True

    # Read effect choice
    if effect_required and effect_selection_list:
        selected_effect = effect_selection_list.get_single_selection()
        effect_ok = selected_effect is not None

    can_proceed = single_ok and multi_ok and effect_ok

    if can_proceed:
        # Execute action
        if action_type == 'play':
            global_vars_shcg.play_card(player, card, ui_draw=True, ui_set_text=True,
                                    additional_targets=selected_targets,
                                    is_ai_player=False, effect_choice=selected_effect,
                                    additional_multi_targets=selected_multi_targets)
        elif action_type == 'enhance':
            global_vars_shcg.on_card_enhanced(player, card_to_enhance=card,
                                            additional_targets=selected_targets,
                                            is_ai_player=False,
                                            ui_draw=True, ui_set_text=True,
                                            effect_choice=selected_effect,
                                            additional_multi_targets=selected_multi_targets)

        # Clean up
        _cancel_pending_selection()
    else:
        return


def _cancel_pending_selection():
    """Cancel any pending selection and close the window."""
    global pending_selection_action, card_selection_window
    global card_selection_lists, multi_card_selection_list, effect_selection_list
    global card_selection_confirm_button, card_selection_cancel_button
    global _card_selection_option_maps
    pending_selection_action = None
    if card_selection_window:
        card_selection_window.kill()
    card_selection_window = None
    card_selection_lists = []
    _card_selection_option_maps = []
    multi_card_selection_list = None
    effect_selection_list = None
    card_selection_confirm_button = None
    card_selection_cancel_button = None


def draw_card(card: shcg_core_cards.Card, show_attack_status_indicator: bool = False, wh: tuple = (200, 290)) -> pygame.Surface:
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
# End of UI Component B
# =====================================
# UI Component C
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
    current_ai_manager = global_vars_bf_ai_manager

    settings_window = pygame_gui.elements.UIWindow(pygame.Rect((500, 50), (400, 800)),
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

    global unique_states_max_player_turn_dropdown, unique_states_max_opp_turn_dropdown
    unique_states_max_player_turn_label = pygame_gui.elements.UILabel(pygame.Rect((10, 280), (180, 35)),
                                        local_translate("USM Player Turn:"),
                                        ui_manager,
                                        container=settings_window)
    unique_states_max_player_turn_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=["100", "200", "300", "400", "500", "600", "700", "800", "900", "1000"],
                                        starting_option=str(global_vars_unique_states_max_player_turn),
                                        relative_rect=pygame.Rect((200, 280), (100, 35)),
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#cuets_unique_states_max_player_turn_dropdown")
    unique_states_max_player_turn_label.set_tooltip("Explore up to this many unique states for the current player turn.", delay=0.1, wrap_width=300)

    unique_states_max_opp_turn_label = pygame_gui.elements.UILabel(pygame.Rect((10, 325), (180, 35)),
                                        local_translate("USM Opponent Turn:"),
                                        ui_manager,
                                        container=settings_window)
    unique_states_max_opp_turn_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=["20", "40", "60", "80", "100", "120", "140", "160", "180", "200", "220", "240", "260", "280", "300"],
                                        starting_option=str(global_vars_unique_states_max_opp_turn),
                                        relative_rect=pygame.Rect((200, 325), (100, 35)),
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#cuets_unique_states_max_opp_turn_dropdown")
    unique_states_max_opp_turn_label.set_tooltip("Explore up to this many unique states for the opponent player.", delay=0.1, wrap_width=300)




    # Deck Selection for New Games
    deck_settings_label = pygame_gui.elements.UILabel(pygame.Rect((10, 370), (340, 35)),
                                        local_translate("Deck Settings:"),
                                        ui_manager,
                                        container=settings_window)

    deck_options = shcg_ui_deck_builder.get_deck_options_list()

    p1_deck_label = pygame_gui.elements.UILabel(pygame.Rect((10, 410), (120, 35)),
                                        local_translate("Player 1 Deck:"),
                                        ui_manager,
                                        container=settings_window)

    # Ensure selected deck is valid, fallback to Random
    p1_selected = shcg_ui_deck_builder.deck_builder_selected_decks.get(1, "Random")
    if p1_selected not in deck_options:
        p1_selected = "Random"
        shcg_ui_deck_builder.deck_builder_selected_decks[1] = "Random"

    settings_p1_deck_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=deck_options,
                                        starting_option=p1_selected,
                                        relative_rect=pygame.Rect((140, 410), (200, 35)),
                                        manager=ui_manager,
                                        container=settings_window,
                                        object_id="#settings_p1_deck")

    p2_deck_label = pygame_gui.elements.UILabel(pygame.Rect((10, 455), (120, 35)),
                                        local_translate("Player 2 Deck:"),
                                        ui_manager,
                                        container=settings_window)

    p2_selected = shcg_ui_deck_builder.deck_builder_selected_decks.get(2, "Random")
    if p2_selected not in deck_options:
        p2_selected = "Random"
        shcg_ui_deck_builder.deck_builder_selected_decks[2] = "Random"

    settings_p2_deck_dropdown = pygame_gui.elements.UIDropDownMenu(
                                        options_list=deck_options,
                                        starting_option=p2_selected,
                                        relative_rect=pygame.Rect((140, 455), (200, 35)),
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
unique_states_max_player_turn_dropdown = None
unique_states_max_opp_turn_dropdown = None
global_vars_cuets_player_turn_set_option: int = 6
global_vars_cuets_opp_turn_set_option: int = 3
global_vars_unique_states_max_player_turn: int = 300
global_vars_unique_states_max_opp_turn: int = 60


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



# =====================================
# End of UI Component C
# =====================================
# UI Component D
# =====================================

# top right
debug_button = pygame_gui.elements.UIButton(relative_rect=pygame.Rect((1500, 10), (90, 35)),
                                    text='Debug',
                                    manager=ui_manager,
                                    command=shcg_ui_debug.build_debug_window)


# Graveyard / Banished / Deck buttons (same x as debug button)
# Player 1 buttons (below debug button)
p1_graveyard_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 50), (90, 35)),
    text='P1 G',
    manager=ui_manager,
    command=lambda: shcg_ui_zone_viewer.open_viewer(1, 'graveyard'))

p1_banished_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 90), (90, 35)),
    text='P1 B',
    manager=ui_manager,
    command=lambda: shcg_ui_zone_viewer.open_viewer(1, 'banished'))

p1_deck_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 130), (90, 35)),
    text='P1 D',
    manager=ui_manager,
    command=lambda: shcg_ui_zone_viewer.open_viewer(1, 'deck'))

# Player 2 buttons (near bottom)
p2_graveyard_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 770), (90, 35)),
    text='P2 G',
    manager=ui_manager,
    command=lambda: shcg_ui_zone_viewer.open_viewer(2, 'graveyard'))

p2_banished_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 810), (90, 35)),
    text='P2 B',
    manager=ui_manager,
    command=lambda: shcg_ui_zone_viewer.open_viewer(2, 'banished'))

p2_deck_button = pygame_gui.elements.UIButton(
    relative_rect=pygame.Rect((1500, 850), (90, 35)),
    text='P2 D',
    manager=ui_manager,
    command=lambda: shcg_ui_zone_viewer.open_viewer(2, 'deck'))

# Settings window deck selection UI references
settings_p1_deck_dropdown = None
settings_p2_deck_dropdown = None

# Initialize deck builder with dependencies
shcg_ui_deck_builder.init(ui_manager, image_405_card_slot, draw_card)

# Initialize zone viewer with dependencies
shcg_ui_zone_viewer.init(ui_manager, draw_card, lambda: global_vars_shcg)

# Initialize debug module with dependencies
shcg_ui_debug.init(ui_manager, lambda: global_vars_shcg, lambda: text_box)


# =====================================
# End of UI Component D
# =====================================
# Component tooltips
# =====================================

def build_component_tooltips():
    """
    All tooltips here. Delay should always be 0.1
    """
    settings_button.set_tooltip("Open settings window.", delay=0.1, wrap_width=300)
    end_turn_button.set_tooltip("End your turn and pass to opponent.", delay=0.1, wrap_width=300)
    reset_turn_button.set_tooltip("Reset your turn to undo all actions taken this turn.", delay=0.1, wrap_width=300)
    new_game_button.set_tooltip("Start a new game.", delay=0.1, wrap_width=300)
    deck_builder_button.set_tooltip("Open deck builder to create custom decks.", delay=0.1, wrap_width=300)
    save_game_button.set_tooltip("Save the current game state to a file.", delay=0.1, wrap_width=300)
    load_game_button.set_tooltip("Load a game state from a file.", delay=0.1, wrap_width=300)


build_component_tooltips()

# =====================================
# End of Component tooltips
# =====================================
# Start New Game
# =====================================

global_vars_bf_ai_manager = shcg_ai.BruteForceAIManager(6, 3, 300, 60)

def _build_random_deck() -> list[shcg_core_cards.Card]:
    """Build a random deck (15 types x 3 copies = 45 cards)."""
    deck: list[shcg_core_cards.Card] = []
    selected_card_types = random.sample(shcg_core_cards.all_card_types, 15)
    for card_type in selected_card_types:
        for _ in range(3):
            deck.append(card_type())
    random.shuffle(deck)
    return deck


def _resolve_deck_for_player(player: int) -> list[shcg_core_cards.Card]:
    """Resolve which deck to use for a player based on settings selection."""
    deck_name = shcg_ui_deck_builder.deck_builder_selected_decks.get(player, "Random")
    if deck_name != "Random" and deck_name in shcg_ui_deck_builder.deck_builder_saved_decks:
        return shcg_ui_deck_builder.build_deck_from_recipe(shcg_ui_deck_builder.deck_builder_saved_decks[deck_name])
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
    global_vars_shcg.image_others = image_others
    global_vars_shcg.image_leader = image_leader
    global_vars_shcg.ui_manager = ui_manager
    global_vars_shcg.draw_card_image_func = draw_card
    global_vars_shcg.image_405_card_slot = image_405_card_slot
    global_vars_shcg.player_2_hp_slot = player_2_hp_slot
    global_vars_shcg.player_1_hp_slot = player_1_hp_slot
    global_vars_shcg.leader_slots = global_vars_leader_slots
    global_vars_shcg.deep_dark_blue = deep_dark_blue
    global_vars_shcg.global_vars_tail_indicators = global_vars_tail_indicators
    global_vars_shcg.global_vars_tail_indicators_active = global_vars_tail_indicators_active
    global_vars_shcg.text_box = text_box
    global_vars_shcg.global_vars_deck_slots = global_vars_deck_slots
    global_vars_shcg.global_vars_hand_slots = global_vars_hand_slots
    global_vars_shcg.global_vars_field_slots = global_vars_field_slots

    global_vars_shcg.decks = {1: example_deck_1, 2: example_deck_2}

    # draw UI
    global_vars_shcg.draw_player_hp_ui()
    global_vars_shcg.draw_current_player_indicator()
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

    text_box.append_html_text(f"プレイヤー{global_vars_shcg.current_player}のターンなのじゃ。\n")
    text_box.append_html_text(f"ターン{global_vars_shcg.turn}\n")
    global_vars_bf_ai_manager.ai_clear_pending_actions()
    # Save state at start of turn for Reset Turn
    global _turn_start_state_string
    _turn_start_state_string = global_vars_shcg.serialize_to_string()


start_new_game()

# =====================================
# End of Start New Game
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
    the_selected_card: shcg_core_cards.Card | None = None # record which card in hand is being dragged


    while running:
        time_delta = clock.tick(60)/1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                shcg_ui_deck_builder.save_decks_to_file()
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
                                condition1 = the_selected_card.cost <= global_vars_shcg.foxtail[cp]
                                condition2 = True
                                if len(global_vars_shcg.fields[cp]) > 4 and not isinstance(the_selected_card, shcg_core_cards.Spell):
                                    condition2 = False
                                if condition1 and condition2:
                                    needs_card_sel = the_selected_card.request_card_selection_on_play  # list[str]
                                    needs_multi_card_sel = the_selected_card.request_multi_card_selection_on_play
                                    needs_effect_sel = the_selected_card.request_effect_choose_option
                                    if needs_card_sel or needs_multi_card_sel[0] or needs_effect_sel:
                                        # Check if any selection type has valid targets
                                        has_any_valid = False
                                        dummy_info = {'type': 'play', 'card': the_selected_card, 'player': cp}
                                        if needs_card_sel:
                                            for sel_type in needs_card_sel:
                                                if _build_card_selection_options(sel_type, dummy_info):
                                                    has_any_valid = True
                                                    break
                                        if needs_multi_card_sel[0]:
                                            tmp_map = {}
                                            if _build_card_selection_options(needs_multi_card_sel[0], dummy_info, target_map=tmp_map):
                                                has_any_valid = True
                                        if needs_effect_sel:
                                            has_any_valid = True
                                        if has_any_valid:
                                            build_card_selection_window({
                                                'type': 'play',
                                                'player': cp,
                                                'card': the_selected_card,
                                                'needs_card_selection': needs_card_sel,
                                                'needs_multi_card_selection': needs_multi_card_sel,
                                                'needs_effect_choice': needs_effect_sel,
                                            })
                                        else:
                                            # No valid targets at all, play with None target
                                            global_vars_shcg.play_card(cp, the_selected_card, ui_draw=True, ui_set_text=True,
                                                                    additional_targets=None,
                                                                    is_ai_player=False, effect_choice=None)
                                    else:
                                        global_vars_shcg.play_card(cp, the_selected_card, ui_draw=True, ui_set_text=True,
                                                                additional_targets=None,
                                                                is_ai_player=False, effect_choice=None)
                                the_selected_card = None
                        ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)

                    elif ui_drag_and_drop_usage == "attack_with_follower_player":
                        opponent = global_vars_shcg.opponent
                        protect_exists = any([c.ability_protect for c in global_vars_shcg.fields[opponent] if isinstance(c, shcg_core_cards.Follower)])
                        for index, slot in enumerate(global_vars_field_slots[opponent]):
                            if slot.rect.collidepoint(event.pos):
                                if the_selected_card:
                                    target_card = None
                                    if index < len(global_vars_shcg.fields[opponent]):
                                        target_card = global_vars_shcg.fields[opponent][index]
                                    if target_card and isinstance(target_card, shcg_core_cards.Follower):
                                        # if target_card .ability_protect is false but there exists other followers
                                        # on opponent field with ability_protect true, cannot attack this target
                                        if protect_exists and not target_card.ability_protect:
                                            text_box.append_html_text(f"【守護】フォロワーがいるから攻撃できないのじゃ！ \n")
                                        else:
                                            global_vars_shcg.follower_attack(cp, the_selected_card, target_card, ui_draw=True, ui_set_text=True)
                        if global_vars_leader_slots[opponent][0].rect.collidepoint(event.pos) and the_selected_card.attack_ability >= 2:
                            if protect_exists:
                                text_box.append_html_text(f"【守護】フォロワーがいるから攻撃できないのじゃ！ \n")
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
                                        if isinstance(target_card, shcg_core_cards.Follower) and target_card.can_enhance:
                                            needs_card_sel = target_card.request_card_selection_on_enhance  # list[str]
                                            needs_multi_card_sel = target_card.request_multi_card_selection_on_enhance
                                            needs_effect_sel = target_card.request_effect_choose_option_e
                                            if needs_card_sel or needs_multi_card_sel[0] or needs_effect_sel:
                                                has_valid_targets = True
                                                if needs_card_sel:
                                                    any_step_has_targets = False
                                                    for sel_type in needs_card_sel:
                                                        test_options = _build_card_selection_options(sel_type, {
                                                            'type': 'enhance', 'card': target_card, 'player': cp})
                                                        if test_options:
                                                            any_step_has_targets = True
                                                            break
                                                    if not any_step_has_targets:
                                                        has_valid_targets = False
                                                if needs_multi_card_sel[0] and has_valid_targets:
                                                    test_multi_options = _build_card_selection_options(needs_multi_card_sel[0], {
                                                        'type': 'enhance', 'card': target_card, 'player': cp})
                                                    if not test_multi_options:
                                                        has_valid_targets = False
                                                if has_valid_targets:
                                                    build_card_selection_window({
                                                        'type': 'enhance',
                                                        'player': cp,
                                                        'card': target_card,
                                                        'needs_card_selection': needs_card_sel,
                                                        'needs_multi_card_selection': needs_multi_card_sel,
                                                        'needs_effect_choice': needs_effect_sel,
                                                    })
                                                else:
                                                    global_vars_shcg.on_card_enhanced(cp, card_to_enhance=target_card,
                                                                                      additional_targets=None,
                                                                                      is_ai_player=False,
                                                                                      ui_draw=True,
                                                                                      ui_set_text=True)
                                            else:
                                                global_vars_shcg.on_card_enhanced(cp, card_to_enhance=target_card,
                                                                                  additional_targets=None,
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
                    shcg_ui_deck_builder.save_decks_to_file()
                    running = False
                if event.ui_element == end_turn_button:
                    global_vars_shcg.end_turn(ui_draw=True, ui_set_text=True)
                    _turn_start_state_string = global_vars_shcg.serialize_to_string()
                if event.ui_element == reset_turn_button:
                    if _turn_start_state_string and not global_vars_shcg.concluded:
                        global_vars_shcg.load_from_string(_turn_start_state_string)
                        global_vars_shcg.redraw_all_ui()
                        text_box.append_html_text(f"ターンをリセットしたのじゃ。\n")
                if event.ui_element == save_game_button:
                    save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_states")
                    os.makedirs(save_dir, exist_ok=True)
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    save_path = os.path.join(save_dir, f"save_{timestamp}.json")
                    state_string = global_vars_shcg.serialize_to_string()
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(state_string)
                    text_box.append_html_text(f"保存:{os.path.basename(save_path)}\n")
                if event.ui_element == load_game_button:
                    if load_game_file_dialog is None:
                        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_states")
                        os.makedirs(save_dir, exist_ok=True)
                        load_game_file_dialog = UIFileDialog(
                            pygame.Rect(400, 150, 700, 600),
                            ui_manager,
                            window_title='Load Game State...',
                            initial_file_path=save_dir + '/',
                            allow_existing_files_only=True,
                            allowed_suffixes={".json"},
                        )
                        load_game_button.disable()
                if event.ui_element == deck_builder_button:
                    shcg_ui_deck_builder.build_deck_builder_window()
                # Deck builder buttons
                shcg_ui_deck_builder.handle_button_pressed(event)
                # Zone viewer buttons (< and > pagination)
                shcg_ui_zone_viewer.handle_button_pressed(event)
                # AI toggle buttons
                current_ai_manager = global_vars_bf_ai_manager
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
                shcg_ui_deck_builder.handle_selection_event(event)

            if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                if event.ui_element == theme_selection_menu:
                    change_theme()
                if event.ui_element == cuets_player_turn_dropdown:
                    global_vars_cuets_player_turn_set_option = int(cuets_player_turn_dropdown.selected_option[0])
                    global_vars_bf_ai_manager.set_new_cuets(global_vars_cuets_player_turn_set_option,
                                                global_vars_cuets_opp_turn_set_option)
                if event.ui_element == cuets_opp_turn_dropdown:
                    global_vars_cuets_opp_turn_set_option = int(cuets_opp_turn_dropdown.selected_option[0])
                    global_vars_bf_ai_manager.set_new_cuets(global_vars_cuets_player_turn_set_option,
                                                global_vars_cuets_opp_turn_set_option)
                if event.ui_element == unique_states_max_player_turn_dropdown:
                    global_vars_unique_states_max_player_turn = int(unique_states_max_player_turn_dropdown.selected_option[0])
                    global_vars_bf_ai_manager.set_new_unique_states_max(global_vars_unique_states_max_player_turn,
                                                global_vars_unique_states_max_opp_turn)
                if event.ui_element == unique_states_max_opp_turn_dropdown:
                    global_vars_unique_states_max_opp_turn = int(unique_states_max_opp_turn_dropdown.selected_option[0])
                    global_vars_bf_ai_manager.set_new_unique_states_max(global_vars_unique_states_max_player_turn,
                                                global_vars_unique_states_max_opp_turn)

                # Deck selection in settings
                if settings_p1_deck_dropdown and event.ui_element == settings_p1_deck_dropdown:
                    shcg_ui_deck_builder.deck_builder_selected_decks[1] = settings_p1_deck_dropdown.selected_option[0]
                    shcg_ui_deck_builder.save_decks_to_file()
                if settings_p2_deck_dropdown and event.ui_element == settings_p2_deck_dropdown:
                    shcg_ui_deck_builder.deck_builder_selected_decks[2] = settings_p2_deck_dropdown.selected_option[0]
                    shcg_ui_deck_builder.save_decks_to_file()

            if event.type == pygame_gui.UI_FILE_DIALOG_PATH_PICKED:
                if load_game_file_dialog and event.ui_element == load_game_file_dialog:
                    try:
                        with open(event.text, "r", encoding="utf-8") as f:
                            state_string = f.read()
                        global_vars_shcg.load_from_string(state_string)
                        global_vars_shcg.redraw_all_ui()
                        _turn_start_state_string = global_vars_shcg.serialize_to_string()
                        text_box.set_text(text_box_introduction_text)
                        text_box.append_html_text(f"ロード:{os.path.basename(event.text)}\n")
                        text_box.append_html_text(f"プレイヤー{global_vars_shcg.current_player}のターンなのじゃ。\n")
                        text_box.append_html_text(f"ターン{global_vars_shcg.turn}\n")
                    except Exception as e:
                        text_box.append_html_text(f"ロードに失敗したのじゃ: {e}\n")

            if event.type == pygame_gui.UI_WINDOW_CLOSE:
                if card_selection_window and event.ui_element == card_selection_window:
                    _cancel_pending_selection()
                if load_game_file_dialog and event.ui_element == load_game_file_dialog:
                    load_game_button.enable()
                    load_game_file_dialog = None

            ui_manager_lower.process_events(event)
            ui_manager.process_events(event)
            ui_manager_overlay.process_events(event)

        # AI Turn Logic - use appropriate AI manager based on toggle
        active_ai_manager = global_vars_bf_ai_manager
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
                        _turn_start_state_string = global_vars_shcg.serialize_to_string()

        shcg_ui_zone_viewer.refresh()
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
