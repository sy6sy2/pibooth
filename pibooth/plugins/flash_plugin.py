# -*- coding: utf-8 -*-

import pibooth
from gpiozero import LEDBoard


class FlashPlugin(object):
    """Plugin to manage the flash via GPIO.
    """

    name = 'pibooth-core:flash'

    def __init__(self, plugin_manager):
        self._pm = plugin_manager
        self.led = LEDBoard("BCM26")

    @pibooth.hookimpl
    def state_chosen_enter(self, app):
        if app.enable_flash:
            self.led.on()

    @pibooth.hookimpl
    def state_processing_enter(self, app):
        if app.enable_flash:
            self.led.off()
