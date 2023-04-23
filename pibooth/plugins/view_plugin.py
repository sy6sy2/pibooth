# -*- coding: utf-8 -*-

import pibooth
from pibooth.utils import LOGGER, PoolingTimer, get_crash_message


class ViewPlugin(object):

    """Plugin to manage the pibooth window dans transitions.
    """

    name = 'pibooth-core:view'

    def __init__(self, plugin_manager):
        self._pm = plugin_manager
        self.count = 0
        # Seconds to display the failed message
        self.failed_view_timer = PoolingTimer(2)
        # Seconds between each animated frame
        self.animated_frame_timer = PoolingTimer(0)
        # Seconds before going back to the start
        self.choose_timer = PoolingTimer(30)
        # Seconds to display the selected layout
        self.layout_timer = PoolingTimer(4)
        # Seconds to display the selected layout
        self.print_view_timer = PoolingTimer(0)
        # Seconds to display the selected layout
        self.finish_timer = PoolingTimer(1)

    @pibooth.hookimpl
    def state_failsafe_enter(self, win):
        win.show_oops()
        self.failed_view_timer.start()
        LOGGER.error(get_crash_message())

    @pibooth.hookimpl
    def state_failsafe_validate(self):
        if self.failed_view_timer.is_timeout():
            return 'wait'

#############################################
#
# WAIT STATE (premier écran)
#
#############################################

    @pibooth.hookimpl
    def state_wait_enter(self, cfg, app, win):
        # if app.previous_animated:
        #     previous_picture = next(app.previous_animated)
        #     # Reset timeout in case of settings changed
        #     self.animated_frame_timer.timeout = cfg.getfloat('WINDOW', 'animate_delay')
        #     self.animated_frame_timer.start()
        # else:
        LOGGER.debug("PREVIOUS PICTURE: %s", str(app.previous_picture))
        LOGGER.debug("PREVIOUS PREVIOUS PICTURE: %s", str(app.previous_previous_picture))
        previous_picture = app.previous_picture
        previous_previous_picture = app.previous_previous_picture

        win.show_intro(previous_picture, previous_previous_picture, app.printer.is_ready())
        if app.printer.is_installed():
            win.set_print_number(len(app.printer.get_all_tasks()), not app.printer.is_ready())

    @pibooth.hookimpl
    def state_wait_do(self, app, win, events):
        previous_picture = app.previous_picture
        previous_previous_picture = app.previous_previous_picture

        event = app.find_print_status_event(events)
        if event and app.printer.is_installed():
            tasks = app.printer.get_all_tasks()
            win.set_print_number(len(tasks), not app.printer.is_ready())

        if app.find_right_event(events):
            win.show_intro(previous_picture, previous_previous_picture, app.printer.is_ready())
        elif app.find_left_event(events):
            win.show_intro(previous_picture, previous_previous_picture, app.printer.is_ready())

    @pibooth.hookimpl
    def state_wait_validate(self, cfg, app, events):
        if app.find_center_event(events):
            return 'choose'
            # if len(app.capture_choices) > 1:
            #     return 'choose'
            # if cfg.getfloat('WINDOW', 'chosen_delay') > 0:
            #     return 'chosen'
            # return 'preview'

    @pibooth.hookimpl
    def state_wait_exit(self, win):
        self.count = 0
        win.show_image(None)  # Clear currently displayed image

#############################################
#
# CHOOSE STATE (choix du nombre de photos)
#
#############################################

    @pibooth.hookimpl
    def state_choose_enter(self, app, win):
        LOGGER.info("Show picture choice (nothing selected)")
        win.set_print_number(0, False)  # Hide printer status
        win.show_choice(app.capture_choices)
        self.choose_timer.start()

    @pibooth.hookimpl
    def state_choose_validate(self, cfg, app):
        if app.capture_nbr:
            if cfg.getfloat('WINDOW', 'chosen_delay') > 0:
                return 'chosen'
            else:
                return 'preview'
        elif self.choose_timer.is_timeout():
            return 'wait'

#############################################
#
# CHOSEN STATE (Juste pour montrer le choix qui a été fait)
#
#############################################

    @pibooth.hookimpl
    def state_chosen_enter(self, cfg, app, win):
        LOGGER.info("Show picture choice (%s captures selected)", app.capture_nbr)
        win.show_choice(app.capture_choices, selected=app.capture_nbr)

        # Reset timeout in case of settings changed
        self.layout_timer.timeout = cfg.getfloat('WINDOW', 'chosen_delay')
        self.layout_timer.start()

    @pibooth.hookimpl
    def state_chosen_validate(self):
        if self.layout_timer.is_timeout():
            return 'preview'

#############################################
#
# PREVIEW STATE (Pour prendre les photos (alterne avec CAPTURE STATE))
#
#############################################

    @pibooth.hookimpl
    def state_preview_enter(self, app, win):
        self.count += 1
        win.set_capture_number(self.count, app.capture_nbr)

    @pibooth.hookimpl
    def state_preview_validate(self):
        return 'capture'

#############################################
#
# CAPTURE STATE (Pour prendre les photos (alterne avec PREVIEW STATE))
#
#############################################

    @pibooth.hookimpl
    def state_capture_do(self, app, win):
        win.set_capture_number(self.count, app.capture_nbr)

    @pibooth.hookimpl
    def state_capture_validate(self, app):
        if self.count >= app.capture_nbr:
            return 'processing'
        return 'preview'

#############################################
#
# PROCESSING STATE (Pour générer la photo finale)
#
#############################################

    @pibooth.hookimpl
    def state_processing_enter(self, win):
        win.show_work_in_progress()

    @pibooth.hookimpl
    def state_processing_validate(self, cfg, app):
        if app.printer.is_ready() and cfg.getfloat('PRINTER', 'printer_delay') > 0:
            return 'print'
        # return 'finish'  # Can not print
        return 'wait'

#############################################
#
# PRINT STATE (Pour afficher la photo prise et proposer l'impression)
#
#############################################

    @pibooth.hookimpl
    def state_print_enter(self, cfg, app, win):
        LOGGER.info("Display the final picture")
        win.show_print(app.previous_picture)
        win.set_print_number(len(app.printer.get_all_tasks()), not app.printer.is_ready())

        # Reset timeout in case of settings changed
        self.print_view_timer.timeout = cfg.getfloat('PRINTER', 'printer_delay')
        self.print_view_timer.start()

    @pibooth.hookimpl
    def state_print_validate(self, app, win, events):
        printed = app.find_right_event(events)
        if self.print_view_timer.is_timeout() or printed :
            if printed:
                win.set_print_number(len(app.printer.get_all_tasks()), not app.printer.is_ready())
            # return 'finish'
            return 'wait'

    # @pibooth.hookimpl
    # def state_finish_enter(self, cfg, app, win):
    #     if cfg.getfloat('WINDOW', 'finish_picture_delay') > 0 and not self.forgotten:
    #         win.show_finished(app.previous_picture)
    #         timeout = cfg.getfloat('WINDOW', 'finish_picture_delay')
    #     else:
    #         win.show_finished()
    #         timeout = 1

    #     # Reset timeout in case of settings changed
    #     self.finish_timer.timeout = timeout
    #     self.finish_timer.start()

    # @pibooth.hookimpl
    # def state_finish_validate(self):
    #     if self.finish_timer.is_timeout():
    #         return 'wait'
