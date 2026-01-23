import os
import more_itertools as mit
import itertools
import pygame, pygame_gui



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

# =====================================
# End of Color and UI Managers
# =====================================
# Example UI Components
# =====================================


image_slot_example = pygame_gui.elements.UIImage(pygame.Rect((100, 50), (156, 156)),
                                    pygame.Surface((156, 156)),
                                    ui_manager)
image_slot_example.set_image(image_others["404coyote"])
image_slot_example.set_tooltip("Example tooltip.", delay=0.1, wrap_width=300)

# =====================================
# End of Example UI Components
# =====================================



if __name__ == "__main__":
    pygame.display.set_caption("Super Hard Card Game")
    try:
        pygame.display.set_icon(pygame.image.load("icon.png"))
    except Exception as e:
        print(f"Error loading icon: {e}")

    print("Starting!")
    # Drag and Drop feature
    ui_drag_and_drop_target = None
    ui_drag_and_drop_target_orig_pos = (0, 0)
    ui_drag_and_drop_usage: str = ""
    running = True 

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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if image_slot_example.rect.collidepoint(event.pos):
                    ui_drag_and_drop_target_orig_pos = (image_slot_example.rect.x, image_slot_example.rect.y)
                    ui_drag_and_drop_usage = "example_usage"
                    ui_drag_and_drop_target = image_slot_example

            if event.type == pygame.MOUSEBUTTONUP:
                # example usage of drag and drop
                if ui_drag_and_drop_target != None:
                    ui_drag_and_drop_target.set_position(ui_drag_and_drop_target_orig_pos)
                    ui_drag_and_drop_target = None
                    ui_drag_and_drop_usage = ""
                    ui_drag_and_drop_target_orig_pos = (0, 0)

            if event.type == pygame.MOUSEMOTION:
                if ui_drag_and_drop_target != None:
                    ui_drag_and_drop_target.set_position((ui_drag_and_drop_target.rect.x + event.rel[0], ui_drag_and_drop_target.rect.y + event.rel[1]))

            if event.type == pygame_gui.UI_BUTTON_PRESSED:
                pass

            if event.type == pygame_gui.UI_TEXT_BOX_LINK_CLICKED:
                pass

            if event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
                pass

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
