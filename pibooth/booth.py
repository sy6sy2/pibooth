#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Pibooth main module.
"""

import argparse
import logging
import multiprocessing
import os
import os.path as osp
import shutil
import subprocess
import tempfile
from warnings import filterwarnings

import pibooth
import pygame
from gpiozero import ButtonBoard, Device, LEDBoard, pi_info
from gpiozero.exc import BadPinFactory, PinFactoryFallback
from pibooth import fonts, language
from pibooth.config import PiConfigMenu, PiConfigParser
from pibooth.counters import Counters
from pibooth.plugins import create_plugin_manager
from pibooth.printer import PRINTER_TASKS_UPDATED, Printer
from pibooth.states import StateMachine
from pibooth.utils import (LOGGER, PoolingTimer, configure_logging,
                           get_crash_message, get_event_pos, set_logging_level)
from pibooth.view import PiWindow

# Set the default pin factory to a mock factory if pibooth is not started a Raspberry Pi
try:
    filterwarnings("ignore", category=PinFactoryFallback)
    GPIO_INFO = "on Raspberry pi {0}".format(pi_info().model)
except BadPinFactory:
    from gpiozero.pins.mock import MockFactory
    Device.pin_factory = MockFactory()
    GPIO_INFO = "without physical GPIO, fallback to GPIO mock"

BUTTONDOWN = pygame.USEREVENT + 1


class PiApplication(object):

    """Main class representing the ``pibooth`` software.
    The following attributes are available for use in plugins:

    :attr capture_nbr: number of capture to be done in the current sequence
    :type capture_nbr: int
    :attr capture_date: date (%Y-%m-%d-%H-%M-%S) of the first capture of the current sequence
    :type capture_date: str
    :attr capture_choices: possible choices of captures numbers.
    :type capture_choices: tuple
    :attr previous_picture: picture generated during last sequence
    :type previous_picture: :py:class:`PIL.Image`
    :attr previous_animated: infinite list of picture to display during animation
    :type previous_animated: :py:func:`itertools.cycle`
    :attr previous_picture_file: file name of the picture generated during last sequence
    :type previous_picture_file: str
    :attr count: holder for counter values
    :type count: :py:class:`pibooth.counters.Counters`
    :attr camera: camera used
    :type camera: :py:class:`pibooth.camera.base.BaseCamera`
    :attr buttons: access to hardware buttons ``capture`` and ``printer``
    :type buttons: :py:class:`gpiozero.ButtonBoard`
    :attr leds: access to hardware LED ``capture`` and ``printer``
    :attr leds: :py:class:`gpiozero.LEDBoard`
    :attr printer: printer used
    :type printer: :py:class:`pibooth.printer.Printer`
    """

    def __init__(self, config, plugin_manager):
        self._pm = plugin_manager
        self._config = config

        # Create directories where pictures are saved
        for savedir in config.gettuple('GENERAL', 'directory', 'path'):
            if osp.isdir(savedir) and config.getboolean('GENERAL', 'debug'):
                shutil.rmtree(savedir)
            if not osp.isdir(savedir):
                os.makedirs(savedir)

        # Create window of (width, height)
        init_size = self._config.gettyped('WINDOW', 'size')
        init_debug = self._config.getboolean('GENERAL', 'debug')
        init_color = self._config.gettyped('WINDOW', 'background')
        init_text_color = self._config.gettyped('WINDOW', 'text_color')
        if not isinstance(init_color, (tuple, list)):
            init_color = self._config.getpath('WINDOW', 'background')

        title = 'Pibooth v{}'.format(pibooth.__version__)
        if not isinstance(init_size, str):
            self._window = PiWindow(title, init_size, color=init_color,
                                    text_color=init_text_color, debug=init_debug)
        else:
            self._window = PiWindow(title, color=init_color,
                                    text_color=init_text_color, debug=init_debug)

        self._menu = None
        # self._multipress_timer = PoolingTimer(config.getfloat('CONTROLS', 'multi_press_delay'), False)
        self._fingerdown_events = []

        # Define states of the application
        self._machine = StateMachine(self._pm, self._config, self, self._window)
        self._machine.add_state('wait')
        self._machine.add_state('choose')
        self._machine.add_state('chosen')
        self._machine.add_state('preview')
        self._machine.add_state('capture')
        self._machine.add_state('processing')
        self._machine.add_state('print')
        self._machine.add_state('finish')

        # ---------------------------------------------------------------------
        # Variables shared with plugins
        # Change them may break plugins compatibility
        self.capture_nbr = None
        self.capture_date = None
        self.capture_choices = (1, 2, 4)
        self.previous_picture = None
        self.previous_animated = None
        self.previous_picture_file = None

        self.count = Counters(self._config.join_path("counters.pickle"),
                              taken=0, printed=0, forgotten=0,
                              remaining_duplicates=self._config.getint('PRINTER', 'max_duplicates'))

        self.enable_flash = self._config.getboolean('FLASH', 'enable')

        self.camera = self._pm.hook.pibooth_setup_camera(cfg=self._config)

        self.buttons = ButtonBoard(right="BOARD" + config.get('CONTROLS', 'right_btn_pin'),
                                   left="BOARD" + config.get('CONTROLS', 'left_btn_pin'),
                                   center="BOARD" + config.get('CONTROLS', 'center_btn_pin'),
                                   hold_time=config.getfloat('CONTROLS', 'debounce_delay'),
                                   pull_up=True)

        self.buttons.right.when_held = self._on_button_right_held
        self.buttons.left.when_held = self._on_button_left_held
        self.buttons.center.when_held = self._on_button_center_held

        self.leds = LEDBoard(capture="BOARD" + config.get('CONTROLS', 'picture_led_pin'),
                             printer="BOARD" + config.get('CONTROLS', 'print_led_pin'))

        self.printer = Printer(config.get('PRINTER', 'printer_name'),
                               config.getint('PRINTER', 'max_pages'),
                               config.gettyped('PRINTER', 'printer_options'),
                               self.count)
        self.tirage_number = 1
        # ---------------------------------------------------------------------

    def _initialize(self):
        """Restore the application with initial parameters defined in the
        configuration file.
        Only parameters that can be changed at runtime are restored.
        """
        # Handle the language configuration
        language.CURRENT = self._config.get('GENERAL', 'language')
        fonts.CURRENT = fonts.get_filename(self._config.get('WINDOW', 'font'))

        # Set the captures choices
        choices = self._config.gettuple('PICTURE', 'captures', int)
        for chx in choices:
            if chx not in [1, 2, 3, 4]:
                LOGGER.warning("Invalid captures number '%s' in config, fallback to '%s'",
                               chx, self.capture_choices)
                choices = self.capture_choices
                break
        self.capture_choices = choices

        # Handle autostart of the application
        self._config.handle_autostart()

        self._window.arrow_location = self._config.get('WINDOW', 'arrows')
        self._window.arrow_offset = self._config.getint('WINDOW', 'arrows_x_offset')
        self._window.text_color = self._config.gettyped('WINDOW', 'text_color')
        self._window.drop_cache()

        # Handle window size
        size = self._config.gettyped('WINDOW', 'size')
        if isinstance(size, str) and size.lower() == 'fullscreen':
            if not self._window.is_fullscreen:
                self._window.toggle_fullscreen()
        else:
            if self._window.is_fullscreen:
                self._window.toggle_fullscreen()
        self._window.debug = self._config.getboolean('GENERAL', 'debug')

        # Handle debug mode
        if not self._config.getboolean('GENERAL', 'debug'):
            set_logging_level()  # Restore default level
            self._machine.add_failsafe_state('failsafe')
        else:
            set_logging_level(logging.DEBUG)
            self._machine.remove_state('failsafe')

        # Reset the print counter (in case of max_pages is reached)
        self.printer.max_pages = self._config.getint('PRINTER', 'max_pages')

    def _on_button_left_held(self):
        """Called when the left button is pressed.
        """
        event = pygame.event.Event(BUTTONDOWN, left=1, center=0, right=0,
                                   button=self.buttons.left)
        LOGGER.debug("BUTTONDOWN: generate LEFT event")
        pygame.event.post(event)

    def _on_button_right_held(self):
        """Called when the left button is pressed.
        """
        event = pygame.event.Event(BUTTONDOWN, left=0, center=0, right=1,
                                   button=self.buttons.right)
        LOGGER.debug("BUTTONDOWN: generate RIGHT event")
        pygame.event.post(event)

    def _on_button_center_held(self):
        """Called when the center button is pressed.
        """

        event = pygame.event.Event(BUTTONDOWN, left=0, center=1, right=0,
                                   button=self.buttons.center)
        LOGGER.debug("BUTTONDOWN: generate CENTER event")
        pygame.event.post(event)

    @property
    def picture_filename(self):
        """Return the final picture file name.
        """
        if not self.capture_date:
            raise EnvironmentError("The 'capture_date' attribute is not set yet")
        return "{}_pibooth.jpg".format(self.capture_date)

    def find_quit_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == pygame.QUIT:
                return event
            # Quit on ESC key press
            elif event.type == pygame.KEYDOWN and event.key in [pygame.K_ESCAPE, pygame.K_q]:
                return event
        return None

    def find_settings_event(self, events):
        """Return the first found event if found in the list.
        """
        # DISABLE SETTINGS MENU
        # for event in events:
        #     if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
        #         return event
        #     if event.type == BUTTONDOWN and event.capture and event.printer:
        #         return event
        #     if event.type == pygame.FINGERDOWN:
        #         # Press but not release
        #         self._fingerdown_events.append(event)
        #     if event.type == pygame.FINGERUP:
        #         # Resetting touch_events
        #         self._fingerdown_events = []
        #     if len(self._fingerdown_events) > 3:
        #         # 4 fingers on the screen trigger the menu
        #         self._fingerdown_events = []
        #         return pygame.event.Event(BUTTONDOWN, capture=1, printer=1,
        #                                   button=self.buttons)
        return None

    def find_fullscreen_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == pygame.KEYDOWN and \
                    event.key == pygame.K_f:
                return event
        return None

    def find_unpause_printer_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == pygame.KEYDOWN and \
                    event.key == pygame.K_p:
                return event
        return None

    def find_resize_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == pygame.VIDEORESIZE:
                return event
        return None

    def find_left_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_LEFT:
                return event
            if (event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3)) or event.type == pygame.FINGERUP:
                pos = get_event_pos(self._window.display_size, event)
                rect = self._window.get_rect()
                if pygame.Rect(0, 0, rect.width // 3, rect.height).collidepoint(pos):
                    return event
            if event.type == BUTTONDOWN and event.left:
                return event
        return None

    def find_right_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT:
                return event
            if (event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3)) or event.type == pygame.FINGERUP:
                pos = get_event_pos(self._window.display_size, event)
                rect = self._window.get_rect()
                # if pygame.Rect(rect.width // 2, 0, rect.width // 2, rect.height).collidepoint(pos):
                if pygame.Rect((rect.width // 3) * 2, 0, rect.width // 3, rect.height).collidepoint(pos):
                    return event
            if event.type == BUTTONDOWN and event.right:
                return event
        return None

    def find_center_event(self, events):
        """Return the first found event if found in the list. (CENTER)
        """
        for event in events:
            if event.type == pygame.KEYDOWN and (event.key == pygame.K_UP or event.key == pygame.K_DOWN):
                return event
            if (event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3)) or event.type == pygame.FINGERUP:
                pos = get_event_pos(self._window.display_size, event)
                rect = self._window.get_rect()
                if pygame.Rect(rect.width // 3, 0, rect.width // 3, rect.height).collidepoint(pos):
                    return event
            if event.type == BUTTONDOWN and event.center:
                return event
        return None

    def find_print_status_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == PRINTER_TASKS_UPDATED:
                return event
        return None

    def find_choice_event(self, events):
        """Return the first found event if found in the list.
        """
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_LEFT:
                return event
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT:
                return event
            if event.type == pygame.KEYDOWN and (event.key == pygame.K_UP or event.key == pygame.K_DOWN):
                return event
            if (event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3)) or event.type == pygame.FINGERUP:
                pos = get_event_pos(self._window.display_size, event)
                rect = self._window.get_rect()
                if pygame.Rect(0, 0, rect.width // 3, rect.height).collidepoint(pos):
                    event.key = pygame.K_LEFT
                elif pygame.Rect(rect.width // 3, 0, rect.width // 3, rect.height).collidepoint(pos):
                    event.key = pygame.K_DOWN
                else:
                    event.key = pygame.K_RIGHT
                return event
            if event.type == BUTTONDOWN:
                if event.left:
                    event.key = pygame.K_LEFT
                elif event.center:
                    event.key = pygame.K_DOWN
                else:
                    event.key = pygame.K_RIGHT
                return event
        return None

    def main_loop(self):
        try:
            fps = 40
            clock = pygame.time.Clock()
            self._initialize()
            self._pm.hook.pibooth_startup(cfg=self._config, app=self)
            self._machine.set_state('wait')

            while True:
                events = list(pygame.event.get())

                if self.find_quit_event(events):
                    break

                if self.find_fullscreen_event(events):
                    self._window.toggle_fullscreen()

                if self.find_unpause_printer_event(events):
                    LOGGER.info("BUTTON P: unpause printer")
                    try:
                        subprocess.run("/home/pi/scripts/unpause_printer.py", stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    except Exception:
                        LOGGER.warning("Failed to unpause printer")

                event = self.find_resize_event(events)
                if event:
                    self._window.resize(event.size)

                if not self._menu and self.find_settings_event(events):
                    self.camera.stop_preview()
                    self.leds.off()
                    self._menu = PiConfigMenu(self._pm, self._config, self, self._window)
                    self._menu.show()
                    self.leds.blink(on_time=0.1, off_time=1)
                elif self._menu and self._menu.is_shown():
                    self._menu.process(events)
                elif self._menu and not self._menu.is_shown():
                    self.leds.off()
                    self._initialize()
                    self._machine.set_state('wait')
                    self._menu = None
                else:
                    self._machine.process(events)

                pygame.display.update()
                clock.tick(fps)  # Ensure the program will never run at more than <fps> frames per second

        except Exception as ex:
            LOGGER.error(str(ex), exc_info=True)
            LOGGER.error(get_crash_message())
        finally:
            self._pm.hook.pibooth_cleanup(app=self)
            pygame.quit()


def main():
    """Application entry point.
    """
    if hasattr(multiprocessing, 'set_start_method'):
        # Avoid use 'fork': safely forking a multithreaded process is problematic
        multiprocessing.set_start_method('spawn')

    parser = argparse.ArgumentParser(usage="%(prog)s [options]", description=pibooth.__doc__)

    parser.add_argument("config_directory", nargs='?', default="~/.config/pibooth",
                        help=u"path to configuration directory (default: %(default)s)")

    parser.add_argument('--version', action='version', version=pibooth.__version__,
                        help=u"show program's version number and exit")

    parser.add_argument("--config", action='store_true',
                        help=u"edit the current configuration and exit")

    parser.add_argument("--translate", action='store_true',
                        help=u"edit the GUI translations and exit")

    parser.add_argument("--reset", action='store_true',
                        help=u"restore the default configuration/translations and exit")

    parser.add_argument("--nolog", action='store_true', default=False,
                        help=u"don't save console output in a file (avoid filling the /tmp directory)")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("-v", "--verbose", dest='logging', action='store_const', const=logging.DEBUG,
                       help=u"report more information about operations", default=logging.INFO)
    group.add_argument("-q", "--quiet", dest='logging', action='store_const', const=logging.WARNING,
                       help=u"report only errors and warnings", default=logging.INFO)

    options = parser.parse_args()

    if not options.nolog:
        filename = osp.join(tempfile.gettempdir(), 'pibooth.log')
    else:
        filename = None
    configure_logging(options.logging, '[ %(levelname)-8s] %(name)-18s: %(message)s', filename=filename)

    plugin_manager = create_plugin_manager()

    # Load the configuration
    config = PiConfigParser(osp.join(options.config_directory, "pibooth.cfg"), plugin_manager, not options.reset)

    # Register plugins
    plugin_manager.load_all_plugins(config.gettuple('GENERAL', 'plugins', 'path'),
                                    config.gettuple('GENERAL', 'plugins_disabled', str))
    LOGGER.info("Installed plugins: %s", ", ".join(
        [plugin_manager.get_friendly_name(p) for p in plugin_manager.list_external_plugins()]))

    # Load the languages
    language.init(config.join_path("translations.cfg"), options.reset)

    # Update configuration with plugins ones
    plugin_manager.hook.pibooth_configure(cfg=config)

    # Ensure config files are present in case of first pibooth launch
    if not options.reset:
        if not osp.isfile(config.filename):
            config.save(default=True)
        plugin_manager.hook.pibooth_reset(cfg=config, hard=False)

    if options.config:
        LOGGER.info("Editing the pibooth configuration...")
        config.edit()
    elif options.translate:
        LOGGER.info("Editing the GUI translations...")
        language.edit()
    elif options.reset:
        config.save(default=True)
        plugin_manager.hook.pibooth_reset(cfg=config, hard=True)
    else:
        LOGGER.info("Starting the photo booth application %s", GPIO_INFO)
        app = PiApplication(config, plugin_manager)
        app.main_loop()


if __name__ == '__main__':
    main()
