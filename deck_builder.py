"""
Deck Builder module for Super Hard Card Game.

Handles deck creation, editing, saving/loading, and the deck builder UI window.
Call init() after pygame and UI managers are set up to inject dependencies.
"""
import os
import json
import random
import pygame
import pygame_gui
import cards


# =====================================
# Dependencies (set via init())
# =====================================

_ui_manager = None
_image_405_card_slot = None
_draw_card_fn = None  # reference to draw_card() from main module


def init(ui_manager, image_405_card_slot, draw_card_fn):
    """
    Initialize deck builder with dependencies from the main module.
    Must be called before build_deck_builder_window() or any UI function.
    """
    global _ui_manager, _image_405_card_slot, _draw_card_fn
    _ui_manager = ui_manager
    _image_405_card_slot = image_405_card_slot
    _draw_card_fn = draw_card_fn


# =====================================
# Deck Builder State
# =====================================

deck_builder_window = None
deck_builder_deck: dict[str, int] = {}  # card_name -> copy count (1-3)
deck_builder_saved_decks: dict[str, dict[str, int]] = {}  # deck_name -> recipe
deck_builder_selected_decks: dict[int, str] = {1: "Random", 2: "Random"}  # player -> deck name or "Random"

DECKS_SAVE_FILE = "saved_decks.json"

# UI element references
deck_builder_collection_list: pygame_gui.elements.UISelectionList | None = None
deck_builder_deck_list: pygame_gui.elements.UISelectionList | None = None
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

# Mapping from display string to card type class
deck_builder_collection_map: dict[str, type] = {}
deck_builder_deck_item_to_name: dict[str, str] = {}

global_vars_db_deck_max_copies = 3
global_vars_db_where_currently_selected: str = "collection"  # or "deck"
global_vars_db_recently_selected_card: cards.Card | None = None


# =====================================
# Save / Load
# =====================================

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


def get_deck_options_list() -> list[str]:
    """Get list of deck names for dropdowns, with 'Random' as first option."""
    return ["Random"] + sorted(deck_builder_saved_decks.keys())


# Load saved decks on startup
load_decks_from_file()


# =====================================
# Deck Utilities
# =====================================

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


def build_deck_from_recipe(recipe: dict[str, int]) -> list[cards.Card]:
    """Build a list of Card instances from a deck recipe."""
    deck = []
    for card_type in cards.all_card_types:
        card = card_type()
        if card.name in recipe:
            for _ in range(recipe[card.name]):
                deck.append(card_type())
    random.shuffle(deck)
    return deck


# =====================================
# Deck Builder Window
# =====================================

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
        _ui_manager,
        window_display_title="Deck Builder",
        object_id="#deck_builder_window",
        resizable=False
    )

    # === Left Panel: Card Collection ===
    pygame_gui.elements.UILabel(
        pygame.Rect((10, 5), (380, 25)),
        "Card Collection",
        _ui_manager,
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
        _ui_manager,
        container=deck_builder_window,
        allow_multi_select=False
    )

    # === Center Panel: Preview & Controls ===
    deck_builder_card_preview = pygame_gui.elements.UIImage(
        pygame.Rect((405, 35), (200, 290)),
        pygame.transform.scale(_image_405_card_slot, (200, 290)),
        _ui_manager,
        container=deck_builder_window
    )

    deck_builder_card_info_label = pygame_gui.elements.UILabel(
        pygame.Rect((405, 330), (200, 40)),
        "",
        _ui_manager,
        container=deck_builder_window
    )

    deck_builder_add_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 375), (120, 35)),
        text="Add x1",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_add"
    )

    deck_builder_add3_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 415), (120, 35)),
        text="Add x3",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_add3"
    )

    deck_builder_remove_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 455), (120, 35)),
        text="Remove x1",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_remove"
    )

    deck_builder_remove3_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 495), (120, 35)),
        text="Remove x3",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_remove3"
    )

    deck_builder_clear_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 535), (120, 35)),
        text="Clear Deck",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_clear"
    )

    deck_builder_randomize_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((405, 575), (120, 35)),
        text="Random",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_random"
    )

    # === Right Panel: Deck Contents ===
    deck_builder_deck_count_label = pygame_gui.elements.UILabel(
        pygame.Rect((620, 5), (380, 25)),
        "Deck: 0 cards (0 types)",
        _ui_manager,
        container=deck_builder_window
    )

    deck_builder_deck_list = pygame_gui.elements.UISelectionList(
        pygame.Rect((620, 35), (380, 370)),
        [],
        _ui_manager,
        container=deck_builder_window,
        allow_multi_select=False
    )

    # === Bottom: Deck Name Entry + Save/Load/Delete/Rename + Saved Decks List ===
    pygame_gui.elements.UILabel(
        pygame.Rect((10, 515), (80, 30)),
        "Deck Name:",
        _ui_manager,
        container=deck_builder_window
    )

    deck_builder_name_entry = pygame_gui.elements.UITextEntryLine(
        pygame.Rect((95, 515), (290, 30)),
        _ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_name_entry"
    )
    deck_builder_name_entry.set_text("My Deck")

    deck_builder_save_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((10, 555), (180, 35)),
        text="Save Deck",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_save"
    )

    deck_builder_rename_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((200, 555), (180, 35)),
        text="Rename Deck",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_rename"
    )

    deck_builder_delete_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((10, 600), (180, 35)),
        text="Delete Deck",
        manager=_ui_manager,
        container=deck_builder_window,
        object_id="#deck_builder_delete"
    )

    # Saved decks list
    pygame_gui.elements.UILabel(
        pygame.Rect((540, 410), (200, 25)),
        "Saved Decks:",
        _ui_manager,
        container=deck_builder_window
    )

    deck_builder_saved_list = pygame_gui.elements.UISelectionList(
        pygame.Rect((540, 440), (380, 195)),
        _get_saved_decks_display_list(),
        _ui_manager,
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


# =====================================
# Saved Decks List Helpers
# =====================================

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


# =====================================
# Card Selection / Preview
# =====================================

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
        preview_surface = _draw_card_fn(card)
        deck_builder_card_preview.set_image(preview_surface)
        deck_builder_card_preview.set_tooltip(card.tooltip_str(), delay=0.1, wrap_width=300)
        count = deck_builder_deck.get(card.name, 0)
        deck_builder_card_info_label.set_text(f"In deck: {count}/{global_vars_db_deck_max_copies}")
    else:
        deck_builder_card_preview.set_image(
            _image_405_card_slot
        )
        deck_builder_card_preview.set_tooltip("", delay=0.1, wrap_width=300)
        deck_builder_card_info_label.set_text("")


# =====================================
# Deck Editing Operations
# =====================================

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


# =====================================
# Deck Save / Load / Delete / Rename
# =====================================

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
# Event Handling (called from main loop)
# =====================================

def handle_button_pressed(event) -> bool:
    """
    Handle UI_BUTTON_PRESSED events for deck builder buttons.
    Returns True if the event was consumed by the deck builder.
    """
    if deck_builder_add_button and event.ui_element == deck_builder_add_button:
        deck_builder_add_card(1)
        return True
    if deck_builder_add3_button and event.ui_element == deck_builder_add3_button:
        deck_builder_add_card(3)
        return True
    if deck_builder_remove_button and event.ui_element == deck_builder_remove_button:
        deck_builder_remove_card(1)
        return True
    if deck_builder_remove3_button and event.ui_element == deck_builder_remove3_button:
        deck_builder_remove_card(3)
        return True
    if deck_builder_clear_button and event.ui_element == deck_builder_clear_button:
        deck_builder_clear()
        return True
    if deck_builder_randomize_button and event.ui_element == deck_builder_randomize_button:
        deck_builder_randomize()
        return True
    if deck_builder_save_button and event.ui_element == deck_builder_save_button:
        deck_builder_save_deck()
        return True
    if deck_builder_delete_button and event.ui_element == deck_builder_delete_button:
        deck_builder_delete_deck()
        return True
    if deck_builder_rename_button and event.ui_element == deck_builder_rename_button:
        deck_builder_rename_deck()
        return True
    return False


def handle_selection_event(event) -> bool:
    """
    Handle UI_SELECTION_LIST_NEW_SELECTION events for deck builder lists.
    Returns True if the event was consumed by the deck builder.
    """
    if deck_builder_collection_list and event.ui_element == deck_builder_collection_list:
        _update_deck_builder_card_info('collection')
        return True
    if deck_builder_deck_list and event.ui_element == deck_builder_deck_list:
        _update_deck_builder_card_info('deck')
        return True
    if deck_builder_saved_list and event.ui_element == deck_builder_saved_list:
        name = _get_saved_list_selected_name()
        if name and deck_builder_name_entry:
            deck_builder_name_entry.set_text(name)
        # load
        deck_builder_load_deck()
        return True
    return False
