"""
Zone Viewer module for Super Hard Card Game.

Displays paginated card grids for graveyard, banished, and deck zones.
Call init() after pygame and UI managers are set up to inject dependencies.
"""
import pygame
import pygame_gui


# =====================================
# Dependencies (set via init())
# =====================================

_ui_manager = None
_draw_card_fn = None
_get_game_state = None  # callable that returns current SHCGGameState


def init(ui_manager, draw_card_fn, get_game_state):
    """
    Initialize zone viewer with dependencies from the main module.
    get_game_state: callable returning the current SHCGGameState instance.
    """
    global _ui_manager, _draw_card_fn, _get_game_state
    _ui_manager = ui_manager
    _draw_card_fn = draw_card_fn
    _get_game_state = get_game_state


# =====================================
# State
# =====================================

_viewer_window = None
_prev_button = None
_next_button = None
_page_label = None
_card_ui_images: list[pygame_gui.elements.UIImage] = []

_current_player: int = 1
_current_zone: str = "graveyard"  # "graveyard", "banished", or "deck"
_current_page: int = 0
_last_snapshot: list = []  # snapshot of card IDs for auto-update detection

CARDS_PER_ROW = 6
ROWS_PER_PAGE = 2
CARDS_PER_PAGE = CARDS_PER_ROW * ROWS_PER_PAGE
_DEFAULT_POS = (400, 150)


# =====================================
# Public API
# =====================================

def open_viewer(player: int, zone: str):
    """Open the zone viewer for a player's graveyard, banished, or deck zone."""
    global _current_player, _current_zone, _current_page
    _current_player = player
    _current_zone = zone
    _current_page = 0
    _build_window()


def handle_button_pressed(event) -> bool:
    """
    Handle UI_BUTTON_PRESSED events for zone viewer buttons.
    Returns True if the event was consumed.
    """
    if _prev_button and event.ui_element == _prev_button:
        _change_page(-1)
        return True
    if _next_button and event.ui_element == _next_button:
        _change_page(1)
        return True
    return False


def update():
    """
    Call once per frame from the main loop.
    Detects game-state changes and refreshes the viewer automatically.
    """
    global _current_page
    if _viewer_window is None or not _viewer_window.alive():
        return
    card_list = _get_card_list()
    current = _snapshot(card_list)
    if current != _last_snapshot:
        # Clamp the page in case cards were removed
        total = max(1, (len(card_list) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)
        if _current_page >= total:
            _current_page = max(0, total - 1)
        _build_window()


# =====================================
# Internal
# =====================================

def _get_card_list() -> list:
    """Get the card list for the current player and zone."""
    game = _get_game_state()
    if _current_zone == "graveyard":
        return game.graveyard[_current_player]
    elif _current_zone == "banished":
        return game.banished[_current_player]
    elif _current_zone == "deck":
        return game.decks[_current_player]
    return []


def _zone_title() -> str:
    """Build the window title for the current zone."""
    card_list = _get_card_list()
    zone_names = {
        "graveyard": "墓場",
        "banished": "消滅",
        "deck": "デッキ",
    }
    zone_label = zone_names.get(_current_zone, _current_zone)
    return f"P{_current_player} {zone_label} ({len(card_list)})"


def _total_pages() -> int:
    """Compute total number of pages."""
    card_list = _get_card_list()
    if not card_list:
        return 1
    return max(1, (len(card_list) + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE)


def _snapshot(card_list: list) -> list:
    """Return a lightweight identity list used to detect zone changes."""
    return [id(c) for c in card_list]


def _build_window():
    """Build or rebuild the viewer window for the current page."""
    global _viewer_window, _prev_button, _next_button, _page_label, _card_ui_images, _last_snapshot

    # Preserve current window position before killing
    win_pos = _DEFAULT_POS
    try:
        if _viewer_window and _viewer_window.alive():
            win_pos = (_viewer_window.rect.x, _viewer_window.rect.y)
        _viewer_window.kill()
    except Exception:
        pass

    card_list = _get_card_list()
    _last_snapshot = _snapshot(card_list)
    total = _total_pages()

    card_w, card_h = 100, 145
    pad_x, pad_y = 10, 10
    nav_height = 45
    grid_height = ROWS_PER_PAGE * (card_h + pad_y) + pad_y
    win_width = CARDS_PER_ROW * (card_w + pad_x) + pad_x + 40  # extra for window chrome
    win_height = grid_height + nav_height + 40  # extra for title bar

    _viewer_window = pygame_gui.elements.UIWindow(
        pygame.Rect(win_pos, (win_width, win_height)),
        _ui_manager,
        window_display_title=_zone_title(),
        object_id="#zone_viewer_window",
        resizable=False
    )

    _card_ui_images = []

    if not card_list:
        pygame_gui.elements.UILabel(
            pygame.Rect((10, 10), (win_width - 40, 35)),
            "カードなし",
            _ui_manager,
            container=_viewer_window
        )
    else:
        start = _current_page * CARDS_PER_PAGE
        end = min(start + CARDS_PER_PAGE, len(card_list))
        page_cards = card_list[start:end]

        for i, card in enumerate(page_cards):
            row = i // CARDS_PER_ROW
            col = i % CARDS_PER_ROW
            x = pad_x + col * (card_w + pad_x)
            y = pad_y + row * (card_h + pad_y)
            card_ui = pygame_gui.elements.UIImage(
                pygame.Rect((x, y), (card_w, card_h)),
                pygame.Surface((card_w, card_h)),
                _ui_manager,
                container=_viewer_window
            )
            card_ui.set_image(_draw_card_fn(card))
            card_ui.set_tooltip(card.tooltip_str(), delay=0.1, wrap_width=300)
            _card_ui_images.append(card_ui)

    # Navigation bar at the bottom
    nav_y = grid_height + 5

    _prev_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((10, nav_y), (60, 35)),
        text="<",
        manager=_ui_manager,
        container=_viewer_window,
        object_id="#zone_viewer_prev"
    )

    _page_label = pygame_gui.elements.UILabel(
        pygame.Rect((80, nav_y), (200, 35)),
        f"Page {_current_page + 1} / {total}",
        _ui_manager,
        container=_viewer_window
    )

    _next_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((290, nav_y), (60, 35)),
        text=">",
        manager=_ui_manager,
        container=_viewer_window,
        object_id="#zone_viewer_next"
    )


def _change_page(delta: int):
    """Change page by delta and rebuild the card display."""
    global _current_page
    total = _total_pages()
    new_page = _current_page + delta
    if 0 <= new_page < total:
        _current_page = new_page
        _build_window()
