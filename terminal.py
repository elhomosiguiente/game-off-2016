"""Module containing the terminal class, the main gameplay logic."""

import re
import itertools
import random
import string
import os
from collections import deque

import pygame

import constants
import timer
import mouse
from resources import load_font
from programs.program import BadInput
from util import render_bezel


class Terminal:

    """The main terminal class."""

    _ACCEPTED_CHARS = (string.ascii_letters + string.digits +
                       string.punctuation + " ")
    _BUF_SIZE = 100
    _HISTORY_SIZE = 50

    _TIMER_POS = (0, 0)
    _TIMER_WARNING_SECS = 30

    # Constants related to drawing the terminal text.
    _VISIBLE_LINES = 29
    _TEXT_FONT = constants.TERMINAL_FONT
    _TEXT_SIZE = constants.TERMINAL_TEXT_SIZE
    _TEXT_COLOUR = constants.TEXT_COLOUR
    _TEXT_COLOURS = {
        "g": constants.TEXT_COLOUR,
        "r": constants.TEXT_COLOUR_RED,
        "w": constants.TEXT_COLOUR_WHITE,
    }

    # Constants related to cursor
    _CURSOR_WIDTH = 6
    _CURSOR_ON_MS = 800
    _CURSOR_OFF_MS = 600

    # The coordinates to start drawing text.
    _TEXT_START = (45, 541)

    # Freeze progress bar size
    _PROGRESS_BAR_SIZE = 30

    # Key repeat delay
    _KEY_REPEAT_DELAY = 50
    _KEY_REPEAT_INITIAL_DELAY = 500

    def __init__(self, programs, prompt='$ ', time=300, depends=None):
        """Initialize the class."""
        # Public attributes
        self.locked = False
        self.id_string = ''.join(
            random.choice(string.ascii_uppercase + string.digits)
            for _ in range(4))

        # Current line without prompt. If current line with prompt is required,
        # use get_current_line(True)
        self._current_line = ""
        self._buf = deque(maxlen=Terminal._BUF_SIZE)
        self._prompt = prompt
        self._cmd_history = CommandHistory(self, maxlen=Terminal._HISTORY_SIZE)
        self._font = load_font(Terminal._TEXT_FONT, Terminal._TEXT_SIZE)
        self._has_focus = True

        # Timer attributes
        self._timer = timer.Timer()
        self._countdown_timer = CountdownTimer(time,
                                               Terminal._TIMER_WARNING_SECS)

        # Freeze attributes
        self._freeze_start = None
        self._freeze_time = None

        # Reboot attributes
        self._rebooting = False
        self._reboot_update_time = 0
        self._reboot_buf = deque()

        # Repeat key presses when certain keys are held.
        # Held key is a tuple of (key, key_unicode, start time)
        self._held_key = None
        self._key_last_repeat = None

        # Create instances of the programs that have been registered.
        self._programs = {c: p(self) for c, p in programs.items()}
        self._current_program = None
        self._depends = {} if depends is None else depends

        # Draw the monitor bezel
        self._bezel = render_bezel(self.id_string)
        self._bezel_off = render_bezel(self.id_string, power_off=True)

        self.reboot()

    def _process_command(self, cmd):
        """Process a completed command."""
        if cmd in self._programs:
            # Check dependencies for this command
            if self._is_cmd_runnable(cmd):
                # Create a new instance of the program
                self._current_program = self._programs[cmd]

                # Don't run the program if it is already completed
                if not self._current_program.completed():
                    self._current_program.start()
                else:
                    self.output(["{} already completed!"
                                 .format(self._current_program.security_type)
                                 .capitalize()])
                    self._current_program = None

        elif cmd in ('help', '?'):
            sorted_cmds = sorted(self._programs.items(),
                                 key=lambda i: i[0])
            self.output(["Available commands:"] +
                        ["  {:10}   {}".format(c, p.help)
                         for c, p in sorted_cmds])

        # Easter egg!
        elif cmd.startswith("colour "):
            args = cmd.split(" ")[1:]
            if len(args) == 3:
                try:
                    # Get colour and try a render to make sure code correct
                    colour = tuple(int(a) for a in args)
                    self._font.render("test", True, colour)
                    Terminal._TEXT_COLOUR = colour
                except (ValueError, TypeError):
                    self.output(["I am not familiar with that colour code."])
                else:
                    self.output(["Enjoy your new colour!"])

        # Freeze test
        elif cmd.startswith("freeze "):
            try:
                self.freeze(int(cmd.split(" ")[1]))
            except ValueError:
                self.output(["Invalid time"])

        elif cmd:
            self.output(["Unknown command '{}'.".format(cmd)])

    def _is_cmd_runnable(self, cmd):
        depends_list = self._depends.get(cmd)
        if depends_list is None:
            blocked_on = []
        else:
            # Get blocked-on list
            blocked_on = [self._programs[c] for c in depends_list
                          if not self._programs[c].completed()]

        if len(blocked_on) == 0:
            return True
        else:
            self.output(["{} currently blocked by: {}".format(
                cmd, ", ".join(p.security_type for p in blocked_on)
            )])
            return False

    def _add_to_buf(self, lines):
        """Add lines to the display buffer."""
        for line in lines:
            # The buffer is ordered left to right from newest to oldest.
            # This will push old lines off the end of the buffer if it is full.
            self._buf.appendleft(line)

    def _complete_input(self):
        """Process a line of input from the user."""
        # Add the current line to the buffer
        self._add_to_buf([self.get_current_line(True)])

        if self._current_program:
            # Handle bad input errors
            try:
                self._current_program.text_input(self.get_current_line())
            except BadInput as e:
                self.output(["Error: {}".format(str(e))])
        else:
            # Skip the prompt and any leading/trailing whitespace to get
            # the command.
            cmd = self.get_current_line().lstrip().rstrip()

            # Add to command history, skipping repeated entries
            if cmd:
                self._cmd_history.add_command(cmd)
            self._process_command(cmd)

        # Reset the prompt
        self._reset_prompt()

    def _reset_prompt(self):
        # Current line doesn't have prompt, so we don't have to worry about
        # adding it.
        self._current_line = ""

    def _tab_complete(self):
        # Only works outside programs for now
        if self._current_program is None:
            partial = self.get_current_line()

            # Find the command being typed
            matches = [c for c in list(self._programs.keys()) + ["help"]
                       if c.startswith(partial)]
            if len(matches) == 1:
                self.set_current_line(matches[0])
            elif len(matches) > 1:
                # Get the common prefix. If this is more than what is typed
                # then complete up till that, else display options
                common_prefix = os.path.commonprefix(matches)
                if common_prefix != partial:
                    self.set_current_line(common_prefix)
                else:
                    self.output([self.get_current_line(True),
                                 "  ".join(matches)])

    def _run_reboot(self):
        """Handle scrolling text as part of a reboot."""
        if self._rebooting and self._reboot_update_time <= self._timer.time:
            pause, line = self._reboot_buf.popleft()
            self.output([line])

            if not self._reboot_buf:
                self._rebooting = False
            else:
                residual = self._timer.time - self._reboot_update_time
                self._reboot_update_time = self._timer.time + pause - residual

    @property
    def time(self):
        """Return the current time."""
        return self._timer.time

    def get_current_line(self, include_prompt=False):
        """Get the current input line."""
        if include_prompt:
            # See if the current program has a prompt. Will be None if it
            # doesn't.
            if self._current_program is not None:
                prompt = self._current_program.prompt
            else:
                prompt = self._prompt

            return (self._current_line if prompt is None
                    else prompt + self._current_line)
        else:
            return self._current_line

    def set_current_line(self, line):
        """Set the current input line."""
        # Don't need to add prompt - this gets added by get_current_line()
        self._current_line = line

    def on_keypress(self, key, key_unicode):
        """Handle a user keypress."""
        # Ignore all input if in freeze mode, or we are rebooting.
        if self._freeze_time is not None or self._rebooting:
            return

        # Any typing other than arrows reset history navigation
        if key not in (pygame.K_UP, pygame.K_DOWN):
            self._cmd_history.reset_navigation()

        # Abort whatever is running on ctrl+c
        if (key == pygame.K_c and
                pygame.key.get_mods() & pygame.KMOD_CTRL):
            current_line = self.get_current_line(True)

            # If we are in a program, then abort it
            if self._current_program:
                # If the current program doesn't allow ctrl+c then stop
                if not self._current_program.allow_ctrl_c:
                    return

                self._current_program.on_abort()
                self._current_program = None
            self.output([current_line + "^C"])
            self._reset_prompt()
            return

        # If we're displaying a graphical program, or the program wants to
        # handle its own keypresses, then pass key to them
        if (self._current_program is not None and
                (self._current_program.PROPERTIES.is_graphical or
                 self._current_program.PROPERTIES.intercept_keypress)):
            self._current_program.on_keypress(key, key_unicode)
            return

        # Now handle terminal keyboard input
        repeat_on_hold = False
        if key in [pygame.K_RETURN, pygame.K_KP_ENTER]:
            if self.get_current_line(True):
                self._complete_input()
        elif key == pygame.K_BACKSPACE:
            self._current_line = self._current_line[:-1]
            repeat_on_hold = True
        elif key in (pygame.K_UP, pygame.K_DOWN):
            # Currently not supported in a program
            if self._current_program is None:
                self._cmd_history.navigate(key == pygame.K_UP)
        elif key == pygame.K_TAB:
            self._tab_complete()
        elif key_unicode in Terminal._ACCEPTED_CHARS:
            self._current_line += key_unicode
            repeat_on_hold = True

        # If this is a key that should be repeated when held, then setup the
        # the attributes
        if repeat_on_hold:
            self._held_key = (key, key_unicode, self._timer.time)

    def on_keyrelease(self):
        """Handle the user releasing a key."""
        self._held_key = None
        self._key_last_repeat = None

    def on_mouseclick(self, button, pos):
        """Handle a user mouse click."""
        if self._current_program:
            self._current_program.on_mouseclick(button, pos)

    def on_mousemove(self, pos):
        """Handle a user mouse move."""
        if self._current_program:
            self._current_program.on_mousemove(pos)

    def on_active_event(self, active_event):
        """Handle a window active event."""
        if active_event.input_focus_change:
            self._has_focus = active_event.gained

    def output(self, output):
        """Add a list of lines to the displayed output."""
        # NB Output is expected to be a list of lines.
        self._add_to_buf(output)

    def freeze(self, time):
        """Freeze terminal for 'time' ms, displaying progress bar."""
        self._freeze_start = self._timer.time
        self._freeze_time = time

    def reduce_time(self, time):
        """Reduce the available time by 'time' seconds."""
        self._countdown_timer.update(time * 1000)

    def reboot(self, msg=""):
        """Simulate a reboot."""
        # Clear the buffer.
        self._buf.clear()

        self._rebooting = True
        self._reboot_update_time = self._timer.time

        # Display welcome message.
        PAUSE_LEN = 20
        self._reboot_buf.extend([
            (PAUSE_LEN, "-" * 60),
            (PAUSE_LEN, "Mainframe terminal"),
            (PAUSE_LEN, ""),
            (PAUSE_LEN,
             "You have {}s to login before terminal is locked down.".format(
                self._countdown_timer.secs_left)),
            (PAUSE_LEN, ""),
            (PAUSE_LEN,
             "Tip of the day: press ctrl+c to cancel current command."),
            (PAUSE_LEN, "-" * 60)])

        if msg:
            self._reboot_buf.extend([
                (PAUSE_LEN * 25, ""),
                (PAUSE_LEN * 50, msg)])

        if 'login' in self._programs:
            end_msgs = [(PAUSE_LEN,
                         "Type 'login' to log in, or 'help' to "
                         "list available commands")]
        else:
            end_msgs = [(PAUSE_LEN,
                         "Type 'help' to list available commands")]

        # Push banner to top, leaving space for end messages, and for
        # current line.
        blank_lines = (Terminal._VISIBLE_LINES -
                       len(self._reboot_buf) - len(end_msgs) - 1)
        self._reboot_buf.extend([(PAUSE_LEN, "")] * blank_lines + end_msgs)

    def draw(self):
        """Draw terminal."""
        # If the current program is a graphical one, draw it now, else draw
        # monitor contents.
        if (self._current_program and
                self._current_program.PROPERTIES.is_graphical):
            self._current_program.draw()
            if not self._current_program.PROPERTIES.skip_bezel:
                self.draw_bezel()
        else:
            self._draw_contents()
            self.draw_bezel()

        # Make sure cursor is an arrow if we are not in a program. This should
        # be a no-op if it is already an arrow.
        if self._current_program is None:
            mouse.current.set_cursor(mouse.Cursor.ARROW)

    def _draw_contents(self):
        """Draw the terminal."""
        if self._rebooting:
            # If we're rebooting, don't draw the prompt
            current_line = ""
        elif self._freeze_time is not None:
            # If terminal freeze is enabled, then update progress bar to
            # indicate how long there is left to wait, using this as the
            # current line.
            done = ((self._timer.time -
                     self._freeze_start) * 100) / self._freeze_time
            remain = int((100 - done) * self._PROGRESS_BAR_SIZE / 100)
            current_line = ("[" +
                            "!" * (self._PROGRESS_BAR_SIZE - remain) +
                            " " * remain + "]")
        else:
            current_line = self.get_current_line(True)

        # If program has its own buf, then use it
        if (self._current_program is not None and
                self._current_program.PROPERTIES.alternate_buf):
            buf = self._current_program.buf
        else:
            buf = self._buf

        # Draw the buffer.
        y_coord = Terminal._TEXT_START[1]
        first_line_height = None
        for line in list(itertools.chain(
                [current_line], buf))[:self._VISIBLE_LINES]:
            # Set defaults before checking whether the line overrides.
            colour = Terminal._TEXT_COLOUR
            size = Terminal._TEXT_SIZE
            fontname = ""

            # Look for any font commands at the start of the line.
            pattern = re.compile(r'<(. [^>]+?)>')
            m = pattern.match(line)
            while m:
                # Don't display the commands
                line = line[len(m.group(0)):]
                cmd, arg = m.group(1).split()
                if cmd == 'c':
                    # Change the colour code.
                    colour = Terminal._TEXT_COLOURS[arg]
                elif cmd == 's':
                    size = int(arg)
                elif cmd == 'f':
                    # Don't load the font yet, as we need to know which
                    # size to load, and the size cmd might come after the
                    # font command
                    fontname = arg

                m = pattern.match(line)

            if fontname:
                font = load_font(fontname, size)
            else:
                font = self._font

            # The height of the rendered text can sometimes be quite different
            # to the 'size' value used. So use the rendered height with a 2
            # pixel padding each side
            line_height = font.size(line)[1] + 4
            if first_line_height is None:
                first_line_height = line_height

            y_coord -= line_height

            text = font.render(line, True, colour)
            pygame.display.get_surface().blit(
                text, (Terminal._TEXT_START[0], y_coord))

        # Determine whether the cursor is on.
        if ((self._current_program is None or
                not self._current_program.PROPERTIES.hide_cursor) and
                not self._rebooting and
                (self._timer.time % (Terminal._CURSOR_ON_MS +
                                     Terminal._CURSOR_OFF_MS) <
                 Terminal._CURSOR_ON_MS)):
            first_line_size = self._font.size(current_line)
            pygame.draw.rect(pygame.display.get_surface(),
                             Terminal._TEXT_COLOUR,
                             (Terminal._TEXT_START[0] + first_line_size[0] + 1,
                              Terminal._TEXT_START[1] - first_line_height - 1,
                              Terminal._CURSOR_WIDTH, first_line_size[1]),
                             0 if self._has_focus else 1)

    def draw_bezel(self, power_off=False):
        """Draw the bezel."""
        bezel = self._bezel if not power_off else self._bezel_off
        pygame.display.get_surface().blit(bezel, bezel.get_rect())

        # Draw the countdown text.
        self._countdown_timer.draw(Terminal._TIMER_POS)

    def run(self):
        """Run terminal logic."""
        self._timer.update()

        if self.paused:
            return

        # Run the reboot if one is in progress.
        self._run_reboot()

        # Check whether the current program (if there is one) has exited.
        if self._current_program and self._current_program.exited():
            # If it exited because it was successfully completed, then display
            # syslog, unless the program is going to do it itself
            if (self._current_program.completed() and
                    not self._current_program.PROPERTIES.suppress_success):
                self.output([self._current_program.success_syslog])

            self._current_program = None

            # Display the prompt again.
            self._reset_prompt()

        # Check if the player ran out of time.
        self._countdown_timer.update(self._timer.frametime)
        if self._countdown_timer.ended:
            self.locked = True

        # See whether terminal can be unfrozen
        if (self._freeze_time is not None and
                self._timer.time > self._freeze_start + self._freeze_time):
            self._freeze_time = None
            self._freeze_start = None

            # Reset current line to prompt
            self._reset_prompt()

        # See whether a key is held, and repeat it
        if self._held_key is not None:
            key, key_unicode, start = self._held_key
            if self._key_last_repeat is None:
                last, delay = start, Terminal._KEY_REPEAT_INITIAL_DELAY
            else:
                last, delay = self._key_last_repeat, Terminal._KEY_REPEAT_DELAY

            if (self._timer.time - last) > delay:
                self._key_last_repeat = self._timer.time
                self.on_keypress(key, key_unicode)

        # Run the current program logic
        if self._current_program is not None:
            self._current_program.run()

    def completed(self):
        """Indicate whether the player has been successful."""
        return len([p for p in self._programs.values()
                    if not p.completed()]) == 0

    @property
    def paused(self):
        """Pause the game."""
        return self._timer.paused

    @paused.setter
    def paused(self, value):
        """Unpause the game."""
        self._timer.paused = value


class CommandHistory:

    """Class for storing and navigating a terminal's command history."""

    def __init__(self, terminal, maxlen):
        """Intialize the class."""
        self._terminal = terminal
        self._history = deque(maxlen=maxlen)
        self._pos = -1
        self._saved_line = None

    def add_command(self, cmd):
        """Add a command to the command history."""
        # Skip repeated commands
        if len(self._history) == 0 or self._history[0] != cmd:
            self._history.appendleft(cmd)

    def reset_navigation(self):
        """Reset the position in the command history."""
        self._pos = -1

    def navigate(self, up):
        """Navigate through the command history."""
        if up:
            if self._pos + 1 < len(self._history):
                # If we are starting a history navigation, then save current
                # line
                if self._pos == -1:
                    self._saved_line = self._terminal.get_current_line()
                self._pos += 1
                self._terminal.set_current_line(self._history[self._pos])
        else:
            if self._pos > 0:
                self._pos -= 1
                self._terminal.set_current_line(self._history[self._pos])
            elif self._pos == 0:
                # Restore saved line
                self._pos = -1
                self._terminal.set_current_line(self._saved_line)


class CountdownTimer:

    _TIMER_FONT = 'media/fonts/LCDMU___.TTF'
    _TIMER_SIZE = 20
    _TIMER_LARGE_SIZE = 30
    _TIMER_COLOUR = (255, 255, 255)
    _TIMER_WARNING_COLOUR = (200, 0, 0)
    _FLASH_TIME = 3000
    _FLASH_ON = 600
    _FLASH_OFF = 400

    """Class for the terminal countdown timer."""
    def __init__(self, time_in_s, warning_secs):
        self._timeleft = time_in_s * 1000
        self._timer_font = load_font(CountdownTimer._TIMER_FONT,
                                     CountdownTimer._TIMER_SIZE)
        self._timer_large_font = load_font(CountdownTimer._TIMER_FONT,
                                           CountdownTimer._TIMER_LARGE_SIZE)
        self._warning_secs = warning_secs

        # Are we currently flashing the timer, and if so what time did it start
        self._flash_start = None

        # The times at which the timer should be large and flashing!
        self._flash_times = [warning_secs, 15, 5, 4, 3, 2, 1]

    @property
    def secs_left(self):
        return self._timeleft // 1000

    @property
    def ended(self):
        return self._timeleft <= 0

    def update(self, ms_to_subtract):
        self._timeleft -= ms_to_subtract
        if self._timeleft <= 0:
            self._timeleft = 0
            self._flash_start = None
        else:
            # Should we end current flash time?
            if (self._flash_start is not None and
                    self._flash_start - self._timeleft > self._FLASH_TIME):
                self._flash_start = None

            # Should we start a new flash time?
            if (self._flash_start is None and
                    len(self._flash_times) > 0 and
                    self.secs_left <= self._flash_times[0]):
                self._flash_start = self._timeleft

                # Keep stripping until we reach a time larger than current
                while (len(self._flash_times) > 0 and
                        self.secs_left <= self._flash_times[0]):
                    self._flash_times = self._flash_times[1:]

    def draw(self, pos):
        # If we are flashing the text, then skip draw if we are in an 'off'
        if (self._flash_start is not None and
                self._timeleft % (self._FLASH_ON + self._FLASH_OFF)
                < self._FLASH_OFF):
            return

        # Are we using normal font or the large flashing font?
        font = self._timer_font
        if self._flash_start is not None:
            font = self._timer_large_font

        # Draw the countdown text on a semi transparent background
        colour = CountdownTimer._TIMER_COLOUR
        if self.secs_left <= self._warning_secs:
            colour = CountdownTimer._TIMER_WARNING_COLOUR
        minutes, seconds = divmod(self.secs_left, 60)
        text = font.render('{}:{:02}'.format(minutes, seconds), True, colour)
        surf = pygame.Surface((text.get_rect().w + 4, text.get_rect().h))
        surf.set_alpha(100)
        pygame.display.get_surface().blit(surf, pos)
        pygame.display.get_surface().blit(text, (pos[0] + 2, pos[1]))

    def _get_font(self):
        if self._flash_start is not None:
            return self._timer_large_font
        else:
            return self._timer_font
