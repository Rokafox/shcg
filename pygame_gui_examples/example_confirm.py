import pygame
import pygame_gui

from pygame_gui.elements import UIButton, UIImage
from pygame_gui.windows import UIFileDialog
from pygame_gui.core.utility import create_resource_path


class ImageLoadApp:
    def __init__(self):
        pygame.init()

        pygame.display.set_caption('Confirm App')
        self.window_surface = pygame.display.set_mode((800, 600))
        self.ui_manager = pygame_gui.UIManager((800, 600), 'data/themes/image_load_app_theme.json')

        self.background = pygame.Surface((800, 600))
        self.background.fill(self.ui_manager.ui_theme.get_colour('dark_bg'))

        self.load_button = UIButton(relative_rect=pygame.Rect(-180, -60, 150, 30),
                                    text='Load Image',
                                    manager=self.ui_manager,
                                    anchors={'left': 'right',
                                             'right': 'right',
                                             'top': 'bottom',
                                             'bottom': 'bottom'})

        self.file_dialog = None

        # scale images, if necessary so that their largest dimension does not exceed these values
        self.max_image_display_dimensions = (400, 400)
        self.display_loaded_image = None

        self.clock = pygame.time.Clock()
        self.is_running = True

    def run(self):
        while self.is_running:
            time_delta = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False

                if (event.type == pygame_gui.UI_BUTTON_PRESSED and
                        event.ui_element == self.load_button):
                    self.confirm_window = pygame_gui.windows.UIConfirmationDialog(rect=pygame.Rect(250, 200, 300, 200),
                                                                      manager=self.ui_manager,
                                                                      window_title="Confirm",
                                                                      action_long_desc="Are you sure you want to load an image?",
                                                                      action_short_name="Yes",
                                                                      blocking=True)
                    self.load_button.disable()

                if (event.type == pygame_gui.UI_WINDOW_CLOSE
                        and event.ui_element == self.confirm_window):
                    self.load_button.enable()
                    self.confirm_window = None

                if event.type == pygame_gui.UI_CONFIRMATION_DIALOG_CONFIRMED:
                    if self.display_loaded_image is not None:
                        self.display_loaded_image.kill()
                    print("User confirmed to load image.")
                    self.load_button.enable()


                self.ui_manager.process_events(event)

            self.ui_manager.update(time_delta)

            self.window_surface.blit(self.background, (0, 0))
            self.ui_manager.draw_ui(self.window_surface)

            pygame.display.update()


if __name__ == "__main__":
    app = ImageLoadApp()
    app.run()