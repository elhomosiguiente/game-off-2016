"""Implementation of the core gameplay."""

import pygame

import timer
import util
from gamestate import GameState
from terminal import Terminal
import menu
import constants


class SuccessState(GameState):

    """Gamestate implementation for the success screen."""

    _FONT = constants.TERMINAL_FONT
    _WAIT_TIME = 1000
    _MAIN_TEXT_HEIGHT = 50
    _CONTINUE_TEXT_HEIGHT = 20

    def __init__(self, mgr, terminal):
        """Initialize the class."""
        self._mgr = mgr
        self._timer = timer.Timer()
        self._terminal = terminal

        font = pygame.font.Font(SuccessState._FONT,
                                SuccessState._MAIN_TEXT_HEIGHT)
        self._login_text = font.render('Access Granted', True,
                                       constants.TEXT_COLOUR)

        font = pygame.font.Font(SuccessState._FONT,
                                SuccessState._CONTINUE_TEXT_HEIGHT)
        self._continue_text = font.render('Press any key to continue', True,
                                          constants.TEXT_COLOUR)

        self._login_text_coords = util.center_align(
            self._login_text.get_rect().w,
            self._login_text.get_rect().h + self._continue_text.get_rect().h)
        coords = util.center_align(self._continue_text.get_rect().w, 0)
        self._continue_text_coords = (coords[0],
                                      self._login_text_coords[1] +
                                      self._login_text.get_rect().h)

    def draw(self):
        """Draw the losing screen."""
        self._terminal.draw_bezel()
        pygame.display.get_surface().blit(self._login_text,
                                          self._login_text_coords)

        if self._timer.time >= SuccessState._WAIT_TIME:
            pygame.display.get_surface().blit(self._continue_text,
                                              self._continue_text_coords)

    def run(self, events):
        """Run the lost-game screen."""
        self._timer.update()
        if self._timer.time >= SuccessState._WAIT_TIME:
            if len([e for e in events if e.type == pygame.KEYDOWN]) > 0:
                # Return to the main menu.
                self._mgr.pop_until(menu.MainMenu)


class LostState(GameState):

    """Gamestate implementation for the defeat screen."""

    _WAIT_TIME = 2000

    def __init__(self, mgr, terminal):
        """Initialize the class."""
        self._mgr = mgr
        self._timer = timer.Timer()
        self._terminal = terminal

    def draw(self):
        """Draw the losing screen."""
        self._terminal.draw_bezel()
        font = pygame.font.Font(None, 30)
        text = font.render('You have been locked out', True, (255, 255, 255))
        pygame.display.get_surface().blit(text, (0, 0))

        if self._timer.time >= LostState._WAIT_TIME:
            text = font.render('Press any key to continue...', True,
                               (255, 255, 255))
            pygame.display.get_surface().blit(text, (0, 30))

    def run(self, events):
        """Run the lost-game screen."""
        self._timer.update()
        if self._timer.time >= LostState._WAIT_TIME:
            if len([e for e in events if e.type == pygame.KEYDOWN]) > 0:
                # Return to the main menu.
                self._mgr.pop_until(menu.MainMenu)


class GameplayState(GameState):

    """Gamestate implementation for the core gameplay."""

    def __init__(self, mgr, level_info):
        """Initialize the class."""
        self._terminal = Terminal(
            programs=level_info['programs'],
            time=level_info['time'],
            depends=level_info['depends'])
        self._mgr = mgr

    def run(self, events):
        """Run the game."""
        for e in events:
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self._terminal.paused = True
                    self._mgr.push(menu.PauseMenu(self._mgr,
                                                  self._terminal))
                else:
                    self._terminal.on_keypress(e.key, e.unicode)
            elif e.type == pygame.KEYUP:
                self._terminal.on_keyrelease()
            elif e.type == pygame.MOUSEBUTTONDOWN:
                self._terminal.on_mouseclick(e.button, e.pos)
            elif e.type == pygame.MOUSEMOTION:
                self._terminal.on_mousemove(e.pos)
            elif e.type == pygame.ACTIVEEVENT:
                self._terminal.on_active_event(util.ActiveEvent(e.state,
                                                                e.gain))

        if not self._terminal.paused:
            self._terminal.run()

        # The player is locked out, switch to the Lost gamestate.
        if self._terminal.locked:
            # Push so that we can restart the game if required by just popping
            # again.
            self._mgr.push(LostState(self._mgr, self._terminal))

        # The player has succeeded, switch to the success gamestate.
        if self._terminal.completed():
            # Don't need to return to the game, so replace this gamestate with
            # the success screen.
            self._mgr.replace(SuccessState(self._mgr, self._terminal))

    def draw(self):
        """Draw the game."""
        self._terminal.draw()
