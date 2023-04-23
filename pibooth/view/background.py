# -*- coding: utf-8 -*-

import os.path as osp

import pygame
from pibooth import fonts, pictures
from pibooth.language import get_translated_text
from pibooth.utils import LOGGER

ARROW_TOP = 'top'
ARROW_BOTTOM = 'bottom'
ARROW_BOTTOM_THIRD = 'bottom-third'
ARROW_HIDDEN = 'hidden'
ARROW_TOUCH = 'touchscreen'


def multiline_text_to_surfaces(text, color, rect, align='center'):
    """Return a list of surfaces corresponding to each line of the text.
    The surfaces are next to each others in order to fit the given rect.

    The ``align`` parameter can be one of:
       * top-left
       * top-center
       * top-right
       * center-left
       * center
       * center-right
       * bottom-left
       * bottom-center
       * bottom-right
    """
    surfaces = []
    lines = text.splitlines()

    font = fonts.get_pygame_font(max(lines, key=len), fonts.CURRENT,
                                 rect.width, rect.height / len(lines))
    for i, line in enumerate(lines):
        surface = font.render(line, True, color)

        if align.endswith('left'):
            x = rect.left
        elif align.endswith('center'):
            x = rect.centerx - surface.get_rect().width / 2
        elif align.endswith('right'):
            x = rect.right - surface.get_rect().width / 2
        else:
            raise ValueError("Invalid horizontal alignment '{}'".format(align))

        height = surface.get_rect().height
        if align.startswith('top'):
            y = rect.top + i * height
        elif align.startswith('center'):
            y = rect.centery - len(lines) * height / 2 + i * height
        elif align.startswith('bottom'):
            y = rect.bottom - (len(lines) - i) * height
        else:
            raise ValueError("Invalid vertical alignment '{}'".format(align))

        surfaces.append((surface, surface.get_rect(x=x, y=y)))
    return surfaces


class Background(object):

    def __init__(self, image_name, color=(0, 0, 0), text_color=(255, 255, 255)):
        self._rect = None
        self._name = image_name
        self._need_update = False

        self._background = None
        self._background_color = color
        self._background_image = None

        self._overlay = None

        self._texts = []  # List of (surface, rect)
        self._text_border = 20  # Distance to other elements
        self._text_color = text_color

        # Build rectangles around some areas for debuging purpose
        self._show_outlines = True
        self._outlines = []

    def __str__(self):
        """Return background final name.

        It is used in the main window to distinguish backgrounds in the cache
        thus each background string shall be uniq.
        """
        return "{}({})".format(self.__class__.__name__, self._name)

    def _make_outlines(self, size):
        """Return a red rectangle surface.
        """
        outlines = pygame.Surface(size, pygame.SRCALPHA, 32)
        pygame.draw.rect(outlines, pygame.Color(255, 0, 0), outlines.get_rect(), 2)
        return outlines

    def _write_text(self, text, rect=None, align='center'):
        """Write a text in the given rectangle.
        """
        if not rect:
            rect = self._rect.inflate(-self._text_border, -self._text_border)
        if self._show_outlines:
            self._outlines.append((self._make_outlines(rect.size), rect))
        self._texts.extend(multiline_text_to_surfaces(text, self._text_color, rect, align))

    def set_color(self, color_or_path):
        """Set background color (RGB tuple) or path to an image that used to
        fill the background.

        :param color_or_path: RGB color tuple or image path
        :type color_or_path: tuple or str
        """
        if isinstance(color_or_path, (tuple, list)):
            assert len(color_or_path) == 3, "Length of 3 is required for RGB tuple"
            if color_or_path != self._background_color:
                self._background_color = color_or_path
                self._need_update = True
        else:
            assert osp.isfile(color_or_path), "Invalid image for window background: '{}'".format(color_or_path)
            if color_or_path != self._background_image:
                self._background_image = color_or_path
                self._background_color = (0, 0, 0)
                self._need_update = True

    def get_color(self):
        """Return the background color (RGB tuple).
        """
        return self._background_color

    def set_text_color(self, color):
        """Set text color (RGB tuple) used to write the texts.

        :param color: RGB color tuple
        :type color: tuple
        """
        assert len(color) == 3, "Length of 3 is required for RGB tuple"
        if color != self._text_color:
            self._text_color = color
            self._need_update = True

    def set_outlines(self, outlines=True):
        """Draw outlines for each rectangle available for drawing
        texts.

        :param outlines: enable / disable outlines
        :type outlines: bool
        """
        if outlines != self._show_outlines:
            self._show_outlines = outlines
            self._need_update = True

    def resize(self, screen):
        """Resize objects to fit to the screen.
        """
        if self._rect != screen.get_rect():
            self._rect = screen.get_rect()
            self._outlines = []

            if self._background_image:
                self._background = pictures.get_pygame_image(
                    self._background_image, (self._rect.width, self._rect.height), crop=True, color=None)
                self._background_color = pictures.get_pygame_main_color(self._background)

            overlay_name = "{}.png".format(self._name)
            if osp.isfile(pictures.get_filename(overlay_name)):
                self._overlay = pictures.get_pygame_image(
                    pictures.get_filename(overlay_name), (self._rect.width, self._rect.height), color=self._text_color, bg_color=self._background_color)

            self.resize_texts()
            self._need_update = True

    def resize_texts(self, rect=None, align='center'):
        """Update text surfaces.
        """
        self._texts = []
        text = get_translated_text(self._name)
        if text:
            self._write_text(text, rect, align)

    def paint(self, screen):
        """Paint and animate the surfaces on the screen.
        """
        if self._background:
            screen.blit(self._background, (0, 0))
        else:
            screen.fill(self._background_color)
        if self._overlay:
            screen.blit(self._overlay, self._overlay.get_rect(center=self._rect.center))
        for text_surface, pos in self._texts:
            screen.blit(text_surface, pos)
        for outline_surface, pos in self._outlines:
            screen.blit(outline_surface, pos)
        self._need_update = False


class IntroBackground(Background):

    def __init__(self, arrow_location=ARROW_BOTTOM, arrow_offset=0):
        Background.__init__(self, "intro")
        self.arrow_location = arrow_location
        self.arrow_offset = arrow_offset
        self.center_arrow = None
        self.center_arrow_pos = None

    def __str__(self):
        """Return background final name.

        It is used in the main window to distinguish backgrounds in the cache
        thus each background string shall be uniq.
        """
        return "{}({})".format(self.__class__.__name__, "intro")

    def resize(self, screen):
        LOGGER.debug("IntroBackground --> resize")
        Background.resize(self, screen)
        if self._need_update:

            # ALSO MODIFY FOR CHOOSE VIEWS
            # Center arrow size
            size = (self._rect.width * 0.3, self._rect.height * 0.3)
            vflip = False
            angle = 10

            # Arrow image
            self.center_arrow = pictures.get_pygame_image("arrow.png", size, vflip=vflip, color=self._text_color, angle=angle)

            arrow_w = self.center_arrow.get_rect().width
            x = int(self._rect.width // 2 - arrow_w // 2)

            y = int(self._rect.top + 2 * self._rect.height // 3)

            # IL FAUT DU INT ICI, PAS DU FLOAT
            self.center_arrow_pos = (x, y)

    def resize_texts(self):
        """Update text surfaces.
        """
        if self.arrow_location == ARROW_HIDDEN:
            rect = pygame.Rect(self._text_border, self._text_border,
                               self._rect.width / 2 - 2 * self._text_border,
                               self._rect.height - 2 * self._text_border)
            align = 'center'
        elif self.arrow_location == ARROW_BOTTOM:
            rect = pygame.Rect(self._text_border, self._text_border,
                               self._rect.width / 2 - 2 * self._text_border,
                               self._rect.height * 0.6 - self._text_border)
            align = 'bottom-center'

        # NOTRE CAS : le texte du milieu pour faire un photo
        elif self.arrow_location == ARROW_BOTTOM_THIRD:
            width = ((self._rect.width / 3) - 2 * self._text_border) - 50
            height = (self._rect.height * 0.6) - 2 * self._text_border
            # Rect(left, top, width, height)
            rect = pygame.Rect((self._rect.width / 2 - width / 2),
                               self._text_border,
                               width,
                               height)
            align = 'center'
        elif self.arrow_location == ARROW_TOUCH:
            rect = pygame.Rect(self._text_border, self._text_border,
                               self._rect.width / 2 - 2 * self._text_border,
                               self._rect.height * 0.4 - self._text_border)
            align = 'bottom-center'
        else:
            rect = pygame.Rect(self._text_border, self._rect.height * 0.4,
                               self._rect.width / 2 - 2 * self._text_border,
                               self._rect.height * 0.6 - self._text_border)
            align = 'top-center'
        Background.resize_texts(self, rect, align)

    def paint(self, screen):
        Background.paint(self, screen)
        screen.blit(self.center_arrow, self.center_arrow_pos)


class IntroWithPrintBackground(IntroBackground):
    # Background quand il y a une image à droite
    def __init__(self, arrow_location=ARROW_BOTTOM, arrow_offset=0):
        IntroBackground.__init__(self, arrow_location, arrow_offset)
        # self.right_arrow = None
        # self.right_arrow_pos = None

    def __str__(self):
        """Return background final name.

        It is used in the main window to distinguish backgrounds in the cache
        thus each background string shall be uniq.
        """
        return "{}({})".format(self.__class__.__name__, "intro_print")

    def resize(self, screen):
        LOGGER.debug("IntroWithPrintBackground --> resize")
        IntroBackground.resize(self, screen)
        # DISABLE RIGHT ARROW
        # if self._need_update and self.arrow_location != ARROW_HIDDEN:
        #     # Mise en place de la fleche de droite
        #     size = (self._rect.width * 0.1, self._rect.height * 0.1)
        #     vflip = False
        #     angle = 20

        #     self.right_arrow = pictures.get_pygame_image(
        #         "arrow.png",
        #         size,
        #         hflip=False,
        #         vflip=vflip,
        #         angle=angle,
        #         color=self._text_color)

        #     x = int((self._rect.width // 3) * 2 + ((self._rect.width // 3) // 2)
        #             - self.right_arrow.get_rect().width // 2)
        #     y = int(self._rect.bottom - self.right_arrow.get_rect().height * 1.1)

        #     self.right_arrow_pos = (x - self.arrow_offset, y)

    def resize_texts(self):
        """Update text surfaces.
        """
        # Mise en place du texte
        IntroBackground.resize_texts(self)
        text = get_translated_text("intro_print")
        if text:
            width = 250  # self._rect.width * 0.20  # - 2 * self._text_border
            height = 90  # self._rect.height * 0.3  # - 2 * self._text_border

            # Rect(left, top, width, height)
            w = self._rect.width
            k1 = (w * 9) // 48
            k2 = w - k1

            rect = pygame.Rect(
                k2 - width // 2,
                self._rect.height - height - self._text_border,
                width,
                height)
            self._write_text(text, rect)

    def paint(self, screen):
        IntroBackground.paint(self, screen)
        # DISABLE RIGHT ARROW
        # screen.blit(self.right_arrow, self.right_arrow_pos)


class IntroWithPrintBackgroundBis(IntroWithPrintBackground):

    def __init__(self, arrow_location=ARROW_BOTTOM, arrow_offset=0):
        IntroWithPrintBackground.__init__(self, arrow_location, arrow_offset)
        self.left_arrow = None
        self.left_arrow_pos = None

    def __str__(self):
        """Return background final name.

        It is used in the main window to distinguish backgrounds in the cache
        thus each background string shall be uniq.
        """
        return "{}({})".format(self.__class__.__name__, "intro_print_bis")

    def resize(self, screen):
        LOGGER.debug("IntroWithPrintBackgroundBis --> resize")
        IntroWithPrintBackground.resize(self, screen)
        # DISABLE LEFT ARROW
        # if self._need_update and self.arrow_location != ARROW_HIDDEN:
        #     size = (self._rect.width * 0.1, self._rect.height * 0.1)
        #     if self.arrow_location == ARROW_TOUCH:
        #         self.left_arrow = pictures.get_pygame_image("hand.png", size, hflip=False,
        #                                                     vflip=False, angle=-70, color=self._text_color)
        #     else:
        #         vflip = True if self.arrow_location == ARROW_TOP else False

        #         if self.arrow_location == ARROW_BOTTOM_THIRD:
        #             angle = -20
        #         else:
        #             angle = 70 if self.arrow_location == ARROW_TOP else -70
        #         self.left_arrow = pictures.get_pygame_image("arrow.png", size, hflip=False,
        #                                                     vflip=vflip, angle=angle, color=self._text_color)

        #     if self.arrow_location == ARROW_BOTTOM_THIRD:
        #         x = int(((self._rect.width // 3) // 2)
        #                 - self.right_arrow.get_rect().width // 2)
        #     else:
        #         x = int(self._rect.left + self._rect.width // 2
        #                 - self.right_arrow.get_rect().width // 2)
        #     if self.arrow_location == ARROW_TOP:
        #         y = self._rect.top + 10
        #     else:
        #         y = int(self._rect.bottom - self.right_arrow.get_rect().height * 1.1)
        #     self.left_arrow_pos = (x - self.arrow_offset, y)

    def resize_texts(self):
        """Update text surfaces.
        """
        IntroWithPrintBackground.resize_texts(self)
        text = get_translated_text("intro_print")
        if text:
            width = 250  # self._rect.width * 0.20  # - 2 * self._text_border
            height = 90  # self._rect.height * 0.3  # - 2 * self._text_border

            # Rect(left, top, width, height)
            w = self._rect.width
            k1 = (w * 9) // 48

            rect = pygame.Rect(
                k1 - width // 2,
                self._rect.height - height - self._text_border,
                width,
                height)
            self._write_text(text, rect)

    def paint(self, screen):
        IntroWithPrintBackground.paint(self, screen)
        # DISABLE LEFT ARROW
        # if self.arrow_location != ARROW_HIDDEN:
        #     screen.blit(self.left_arrow, self.left_arrow_pos)


class ChooseBackground(Background):

    def __init__(self, choices, arrow_location=ARROW_BOTTOM, arrow_offset=0):
        Background.__init__(self, "choose")
        self.arrow_location = arrow_location
        self.arrow_offset = arrow_offset
        self.choices = choices

        self.layout0 = None
        self.layout0_pos = None

        self.layout1 = None
        self.layout1_pos = None

        self.layout2 = None
        self.layout2_pos = None

        self.left_arrow = None
        self.left_arrow_pos = None

        self.right_arrow = None
        self.right_arrow_pos = None

        self.center_arrow = None
        self.center_arrow_pos = None

    def resize(self, screen):
        Background.resize(self, screen)
        if self._need_update:
            size = (self._rect.width * 0.3, self._rect.height * 0.4)

            self.layout_left = pictures.get_pygame_layout_image(
                self._text_color, self._background_color, self.choices[0], size)

            self.layout_center = pictures.get_pygame_layout_image(
                self._text_color, self._background_color, self.choices[1], size)

            self.layout_right = pictures.get_pygame_layout_image(
                self._text_color, self._background_color, self.choices[2], size)

            # inter = (self._rect.width - 2 * self.layout0.get_rect().width) // 3

            w = self._rect.width
            k1 = (w * 9) // 48
            k2 = w - k1

            # PICTURES

            y = int(self._rect.top + self._rect.height * 0.3 - 40)

            pic_width = self.layout_left.get_rect().width
            # s = (self._rect.width - 3 * pic_width) / 4

            x_left = int(k1 - pic_width // 2)
            self.layout_left_pos = (x_left, y)

            x_center = w // 2 - pic_width // 2
            self.layout_center_pos = (x_center, y)

            x_right = int(k2 - pic_width // 2)
            self.layout_right_pos = (x_right, y)

            # ARROWS

            # COMMON
            y = int(self._rect.top + 2 * self._rect.height // 3)
            size = (self._rect.width * 0.3, self._rect.height * 0.3)

            # Left
            self.left_arrow = pictures.get_pygame_image("arrow.png", size, vflip=False,
                                                        color=self._text_color, angle=10)

            arrow_width = self.left_arrow.get_rect().width
            x_left = int(k1 - arrow_width // 2)
            self.left_arrow_pos = (x_left, y)

            # Center
            self.center_arrow = pictures.get_pygame_image("arrow.png", size, hflip=False,
                                                          vflip=False, color=self._text_color, angle=10)

            arrow_width = self.center_arrow.get_rect().width
            x_center = int(w // 2 - arrow_width // 2)
            self.center_arrow_pos = (x_center, y)

            # Right
            self.right_arrow = pictures.get_pygame_image("arrow.png", size, hflip=False,
                                                         vflip=False, color=self._text_color, angle=10)

            arrow_width = self.right_arrow.get_rect().width
            x_right = int(k2 - arrow_width // 2)
            self.right_arrow_pos = (x_right, y)

    def resize_texts(self):
        """Update text surfaces.
        """
        rect = pygame.Rect(self._text_border, self._text_border,
                           self._rect.width - 2 * self._text_border, self._rect.height * 0.2)
        Background.resize_texts(self, rect)

    def paint(self, screen):
        Background.paint(self, screen)
        screen.blit(self.layout_left, self.layout_left_pos)
        screen.blit(self.layout_center, self.layout_center_pos)
        screen.blit(self.layout_right, self.layout_right_pos)

        # if self.arrow_location in [ARROW_TOP, ARROW_BOTTOM]:
        screen.blit(self.left_arrow, self.left_arrow_pos)
        screen.blit(self.center_arrow, self.center_arrow_pos)
        screen.blit(self.right_arrow, self.right_arrow_pos)


class ChosenBackground(Background):

    def __init__(self, choices, selected):
        Background.__init__(self, "chosen")
        self.choices = choices
        self.selected = selected
        self.layout = None
        self.layout_pos = None

    def __str__(self):
        """Return background final name.
        It is used in the main window to distinguish background in the cache.
        """
        return "{}({}{})".format(self.__class__.__name__, self._name, self.selected)

    def resize(self, screen):
        Background.resize(self, screen)
        if self._need_update:
            size = (self._rect.width * 0.6, self._rect.height * 0.6)

            self.layout = pictures.get_pygame_layout_image(
                self._text_color, self._background_color, self.selected, size)

            x = self.layout.get_rect(center=self._rect.center).left
            y = int(self._rect.top + self._rect.height * 0.3)

            self.layout_pos = (x, y)

    def resize_texts(self):
        """Update text surfaces.
        """
        rect = pygame.Rect(self._text_border, self._text_border,
                           self._rect.width - 2 * self._text_border, self._rect.height * 0.2)
        Background.resize_texts(self, rect)

    def paint(self, screen):
        Background.paint(self, screen)
        screen.blit(self.layout, self.layout_pos)


class CaptureBackground(Background):

    def __init__(self):
        Background.__init__(self, "capture")
        self.left_people = None
        self.left_people_pos = None
        self.right_people = None
        self.right_people_pos = None

    def resize(self, screen):
        Background.resize(self, screen)
        # if self._need_update:
        #     images_height = self._rect.height / 4
        #     size = (images_height * 2, images_height)

        #     self.left_people = pictures.get_pygame_image("capture_left.png", size=size,
        #                                                  color=self._text_color)
        #     self.right_people = pictures.get_pygame_image("capture_right.png", size=size,
        #                                                   color=self._text_color)

        #     x = int(self._rect.right - size[0])
        #     y = int(self._rect.bottom - images_height)

        #     self.left_people_pos = (0, y)
        #     self.right_people_pos = (x + size[0] - 1.5 * self.right_people.get_rect().width, y)

        #     if self._show_outlines:
        #         self._outlines.append((self._make_outlines(size), (0, y)))
        #         self._outlines.append((self._make_outlines(size), (x, y)))

    def paint(self, screen):
        Background.paint(self, screen)
        # screen.blit(self.left_people, self.left_people_pos)
        # screen.blit(self.right_people, self.right_people_pos)


class ProcessingBackground(Background):

    def __init__(self):
        Background.__init__(self, "processing")

    def resize_texts(self):
        """Update text surfaces.
        """
        rect = pygame.Rect(self._text_border, self._rect.height * 0.8 - self._text_border,
                           self._rect.width - 2 * self._text_border, self._rect.height * 0.2)
        Background.resize_texts(self, rect)


class PrintBackground(Background):

    def __init__(self, arrow_location=ARROW_BOTTOM, arrow_offset=0):
        Background.__init__(self, "print")
        self.arrow_location = arrow_location
        self.arrow_offset = arrow_offset
        self.right_arrow = None
        self.right_arrow_pos = None

    def resize(self, screen):
        Background.resize(self, screen)
        if self._need_update:

            w = self._rect.width
            k1 = (w * 9) // 48
            k2 = w - k1

            y = int(self._rect.top + 2 * self._rect.height // 3)
            size = (self._rect.width * 0.3, self._rect.height * 0.3)

            # Right arrow
            self.right_arrow = pictures.get_pygame_image("arrow.png", size, hflip=False,
                                                         vflip=False, color=self._text_color, angle=0)

            arrow_width = self.right_arrow.get_rect().width
            x_right = int(k2 - arrow_width // 2 + 15)
            self.right_arrow_pos = (x_right, y)

    def resize_texts(self):
        """Update text surfaces.
        """
        width = 300  # self._rect.width * 0.20  # - 2 * self._text_border
        height = 300  # self
        w = self._rect.width
        h = self._rect.height
        k1 = (w * 9) // 48
        k2 = w - k1

        rect = pygame.Rect(
            k2 - width // 2 + 50,
            h // 2 - height // 2 - 100,
            width,
            height)
        align = 'bottom-center'
        Background.resize_texts(self, rect, align)

    def paint(self, screen):
        Background.paint(self, screen)
        screen.blit(self.right_arrow, self.right_arrow_pos)


class FinishedBackground(Background):

    def __init__(self):
        Background.__init__(self, "finished")
        self.left_people = None
        self.left_people_pos = None
        self.right_people = None
        self.right_people_pos = None

    def resize(self, screen):
        Background.resize(self, screen)
        if self._need_update:
            left_rect = pygame.Rect(10, 0, self._rect.width * 0.4, self._rect.height * 0.5)
            left_rect.top = self._rect.centery - left_rect.centery
            right_rect = pygame.Rect(0, 0, self._rect.width * 0.3, self._rect.height * 0.5)
            right_rect.top = self._rect.centery - right_rect.centery
            right_rect.right = self._rect.right - 10

            self.left_people = pictures.get_pygame_image("finished_left.png", size=left_rect.size,
                                                         color=self._text_color)
            self.right_people = pictures.get_pygame_image("finished_right.png", size=right_rect.size,
                                                          color=self._text_color)

            self.left_people_pos = self.left_people.get_rect(center=left_rect.center).topleft
            self.right_people_pos = self.right_people.get_rect(center=right_rect.center).topleft

            if self._show_outlines:
                self._outlines.append((self._make_outlines(left_rect.size), left_rect.topleft))
                self._outlines.append((self._make_outlines(right_rect.size), right_rect.topleft))

    def resize_texts(self):
        """Update text surfaces.
        """
        rect = pygame.Rect(0, 0, self._rect.width * 0.35, self._rect.height * 0.4)
        rect.center = self._rect.center
        rect.bottom = self._rect.bottom - 10
        Background.resize_texts(self, rect)

    def paint(self, screen):
        Background.paint(self, screen)
        if self.left_people:
            screen.blit(self.left_people, self.left_people_pos)
        if self.right_people:
            screen.blit(self.right_people, self.right_people_pos)


class FinishedWithImageBackground(FinishedBackground):

    def __init__(self, foreground_size):
        FinishedBackground.__init__(self)
        self._name = "finishedwithimage"
        self.foreground_size = foreground_size

    def resize(self, screen):
        Background.resize(self, screen)
        if self._need_update:
            # Note: '0.9' ratio comes from PiWindow._update_foreground() method which
            # lets a margin between window borders and fullscreen foreground picture
            frgnd_rect = pygame.Rect(0, 0, *pictures.sizing.new_size_keep_aspect_ratio(
                self.foreground_size, (self._rect.size[0] * 0.9, self._rect.size[1]*0.9)))
            xmargin = abs(self._rect.width - frgnd_rect.width) // 2
            ymargin = abs(self._rect.height - frgnd_rect.height) // 2

            if xmargin > 50:
                margin = min(xmargin, self._rect.height // 3)
            elif ymargin > 50:
                margin = min(ymargin, self._rect.width // 3)
            else:  # Too small
                self.left_people = None
                self.right_people = None
                return

            left_rect = pygame.Rect(0, 0, margin, margin)
            right_rect = pygame.Rect(0, 0, margin, margin)
            left_rect.bottom = self._rect.bottom
            right_rect.right = self._rect.right

            self.left_people = pictures.get_pygame_image("finished_left.png", size=left_rect.size,
                                                         color=self._text_color)
            self.right_people = pictures.get_pygame_image("finished_right.png", size=right_rect.size,
                                                          color=self._text_color)

            self.left_people_pos = self.left_people.get_rect(center=left_rect.center).topleft
            self.right_people_pos = self.right_people.get_rect(center=right_rect.center).topleft

            if self._show_outlines and left_rect and right_rect:
                self._outlines.append((self._make_outlines(left_rect.size), left_rect.topleft))
                self._outlines.append((self._make_outlines(right_rect.size), right_rect.topleft))


class OopsBackground(Background):

    def __init__(self):
        Background.__init__(self, "oops")
