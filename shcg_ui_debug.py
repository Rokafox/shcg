"""
Debug Window module for Super Hard Card Game.

Provides debug utilities: add cards to deck, modify foxtail/HP, clear hand.
Call init() after pygame and UI managers are set up to inject dependencies.
"""
import pygame
import pygame_gui
import shcg_core_cards


# =====================================
# Dependencies (set via init())
# =====================================

_ui_manager = None
_get_game_state = None  # callable that returns current SHCGGameState
_get_text_box = None    # callable that returns the text_box for logging


def init(ui_manager, get_game_state, get_text_box):
    """
    Initialize debug module with dependencies from the main module.
    get_game_state: callable returning the current SHCGGameState instance.
    get_text_box: callable returning the text_box UITextBox for logging.
    """
    global _ui_manager, _get_game_state, _get_text_box
    _ui_manager = ui_manager
    _get_game_state = get_game_state
    _get_text_box = get_text_box


# =====================================
# State
# =====================================

_debug_window = None
_debug_card_selection_dropdown = None
_debug_add_card_button = None
_debug_add_foxtail_button = None
_debug_add_hp_button = None
_debug_reduce_hp_button = None
_debug_rid_of_all_hand_button = None


# =====================================
# Public API
# =====================================

def build_debug_window():
    """
    Build the debug window with card selection dropdown and action buttons.
    """
    global _debug_window, _debug_card_selection_dropdown, _debug_add_card_button
    global _debug_add_foxtail_button
    global _debug_add_hp_button, _debug_reduce_hp_button
    global _debug_rid_of_all_hand_button

    try:
        _debug_window.kill()
    except Exception:
        pass

    _debug_window = pygame_gui.elements.UIWindow(pygame.Rect((600, 250), (280, 400)),
                                        _ui_manager,
                                        window_display_title="Debug Window",
                                        object_id="#debug_window",
                                        resizable=False)

    debug_card_selection_label = pygame_gui.elements.UILabel(pygame.Rect((10, 10), (50, 35)),
                                        "Card:",
                                        _ui_manager,
                                        container=_debug_window)
    all_card_names = [card_type().name for card_type in shcg_core_cards.all_card_types + shcg_core_cards.debug_card_types]
    _debug_card_selection_dropdown = pygame_gui.elements.UIDropDownMenu(all_card_names,
                                                        all_card_names[0],
                                                        pygame.Rect((70, 10), (200, 35)),
                                                        _ui_manager,
                                                        container=_debug_window,)
    _debug_add_card_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 55), (260, 50)),
                                        text="Add to Top of Deck",
                                        manager=_ui_manager,
                                        container=_debug_window,
                                        object_id="#debug_add_card_button",
                                        command=debug_add_card_to_top_of_deck)

    _debug_add_foxtail_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 110), (260, 50)),
                                        text="Add Foxtail to Current Player",
                                        manager=_ui_manager,
                                        container=_debug_window,
                                        object_id="#debug_add_foxtail_player_1_button",
                                        command=debug_add_foxtail_to_current_player)

    _debug_add_hp_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 165), (125, 50)),
                                        text="Add 1 HP",
                                        manager=_ui_manager,
                                        container=_debug_window,
                                        object_id="#debug_add_player_1_hp_button",
                                        command=debug_add_1_hp_to_current_player)

    _debug_reduce_hp_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((145, 165), (125, 50)),
                                        text="Reduce 1 HP",
                                        manager=_ui_manager,
                                        container=_debug_window,
                                        object_id="#debug_reduce_player_1_hp_button",
                                        command=debug_reduce_1_hp_from_current_player)

    _debug_rid_of_all_hand_button = pygame_gui.elements.UIButton(
                                        relative_rect=pygame.Rect((10, 220), (260, 50)),
                                        text="Get Rid of All Hand",
                                        manager=_ui_manager,
                                        container=_debug_window,
                                        object_id="#debug_rid_of_all_hand_button",
                                        command=get_rid_of_all_hand)


# =====================================
# Debug Helper Functions
# =====================================

def debug_add_card_to_top_of_deck():
    game = _get_game_state()
    text_box = _get_text_box()
    if game.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    card_to_add = None
    card_name = _debug_card_selection_dropdown.selected_option[0]
    for card_type in shcg_core_cards.all_card_types:
        if card_type().name == card_name:
            card_to_add = card_type()
            break
    if card_to_add:
        cp = game.current_player
        game.decks[cp].append(card_to_add)
        game.draw_deck_ui(cp)
        text_box.append_html_text(f"DEBUG:カード「{card_name}」をプレイヤー{cp}のデッキの一番上に追加したのじゃ。\n")
    else:
        raise ValueError(f"Card not found: {card_name}")


def debug_add_foxtail_to_current_player():
    game = _get_game_state()
    text_box = _get_text_box()
    if game.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    cp = game.current_player
    if game.foxtail[cp] < 9:
        game.foxtail[cp] += 1
        game.draw_tail_ui(cp)
        text_box.append_html_text(f"DEBUG:プレイヤーに狐尾を1つ追加したのじゃ。\n")
    else:
        text_box.append_html_text(f"DEBUG:プレイヤーの狐尾は最大数に達しているのじゃ。\n")


def debug_add_1_hp_to_current_player():
    game = _get_game_state()
    text_box = _get_text_box()
    if game.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    cp = game.current_player
    game.hp[cp] = min(game.hp[cp] + 1, game.max_hp[cp])
    game.draw_player_hp_ui()
    text_box.append_html_text(f"DEBUG:プレイヤー{cp}のHPを1追加したのじゃ。\n")


def debug_reduce_1_hp_from_current_player():
    game = _get_game_state()
    text_box = _get_text_box()
    if game.concluded:
        text_box.append_html_text(f"DEBUG:ゲームが終了しているのじゃ。\n")
        return
    cp = game.current_player
    game.hp[cp] = max(game.hp[cp] - 1, 1)
    game.draw_player_hp_ui()
    text_box.append_html_text(f"DEBUG:プレイヤー{cp}のHPを1減らしたのじゃ。\n")


def get_rid_of_all_hand():
    game = _get_game_state()
    text_box = _get_text_box()
    cp = game.current_player
    game.hands[cp] = []
    game.draw_hand_ui(cp)
    text_box.append_html_text(f"DEBUG:プレイヤー{cp}の手札を全てなくしたのじゃ。\n")
