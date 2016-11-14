"""Hexeditor program classes."""

import random
from enum import Enum, unique
from . import program


class HexEditor(program.TerminalProgram):

    """Program class for the hex-editor puzzle."""

    @unique
    class States(Enum):
        QUERY_ROW = 0
        ENTER_COL = 1
        ENTER_VAL = 2
        FINISHED = 3

    _MIN_FILE_LENGTH = 3
    _MAX_FILE_LENGTH = 5

    _ROW_PROMPT = 'Edit line {}? (y/n)'
    _COL_PROMPT = 'Edit col num: '
    _VAL_PROMPT = 'Change {:#04x} to (leave empty to cancel): '

    # How long is the freeze time (in ms) when a mistake is made
    _FREEZE_TIME = 5 * 1000

    def __init__(self, terminal):
        """Initialize the class."""
        super().__init__(terminal)
        self._completed = False
        self._row = 0
        self._col = 0
        self._state = HexEditor.States.QUERY_ROW
        self._start_data = []
        self._end_data = []

    @property
    def help(self):
        """Return the help string."""
        return "Modify raw software data."

    @property
    def security_type(self):
        """Return the security type."""
        return "software lock"

    @property
    def prompt(self):
        """Return the prompt based on the current state."""
        if self._state == HexEditor.States.QUERY_ROW:
            return HexEditor._ROW_PROMPT.format(self._row)
        elif self._state == HexEditor.States.ENTER_COL:
            return HexEditor._COL_PROMPT
        elif self._state == HexEditor.States.ENTER_VAL:
            return HexEditor._VAL_PROMPT.format(
                self._start_data[self._row][self._col])

    def start(self):
        """Start the program."""
        self._row = 0
        self._col = 0
        self._state = HexEditor.States.QUERY_ROW
        self._start_data = HexEditor._generate_data()
        self._end_data = list(self._start_data)
        self._output_data()

    def completed(self):
        """Indicate whether the user has guessed the password."""
        return self._completed

    def exited(self):
        """Indicate whether the current instance has exited."""
        return self._state == HexEditor.States.FINISHED

    def text_input(self, line):
        """Handle editor commands."""
        # Remove any leading whitespace and convert to lowercase.
        line = line.lstrip().lower()

        if self._state == HexEditor.States.QUERY_ROW:
            if line.startswith('y'):
                self._state = HexEditor.States.ENTER_COL
            else:
                self._row += 1
        elif self._state == HexEditor.States.ENTER_COL:
            try:
                self._col = int(line)
            except ValueError:
                raise program.BadInput('Not a number')

            if self._col < 0 or self._col >= len(self._start_data[0]):
                raise program.BadInput('Column out of range')

            self._state = HexEditor.States.ENTER_VAL
        elif self._state == HexEditor.States.ENTER_VAL:
            # If the user has cancelled, go back to the row query.
            if not line:
                self._state = HexEditor.States.QUERY_ROW
            else:
                try:
                    self._end_data[self._row][self._col] = int(line, 16)
                except ValueError:
                    raise program.BadInput('Not a number')

                self._row += 1
                self._state = HexEditor.States.QUERY_ROW

        # Check if we've reached the end of the file, and if so see if the edits
        # were correct.
        self._check_finished()

    def _check_finished(self):
        """Determine if edits are finished, and whether they were successful."""
        if self._row == len(self._start_data):
            self._state = HexEditor.States.FINISHED
            if self._data_correct():
                self._completed = True
            else:
                self._terminal.output([self.failure_prefix +
                                       "corruption detected "
                                       "in system file, repairing!"])
                self._terminal.freeze(HexEditor._FREEZE_TIME)

    @staticmethod
    def _generate_random_line():
        return [random.randrange(0x10) for _ in range(6)]

    @staticmethod
    def _generate_data():
        """Generate the data for the puzzle."""
        return [HexEditor._generate_random_line() for _ in
                range(random.randrange(HexEditor._MIN_FILE_LENGTH,
                                       HexEditor._MAX_FILE_LENGTH))]

    def _output_data(self):
        """Output the data on the screen."""
        col_count = len(self._start_data[0])
        self._terminal.output([""] +
                              [" " * 2 + " | " +
                               "  ".join("{:4}".format(i)
                                         for i in range(col_count))] +
                              ["-" * (5 + 6 * col_count)])
        self._terminal.output(
            ["{:2} | ".format(idx) + "  ".join(
                "{:#04x}".format(c) for c in row)
             for idx, row in enumerate(self._start_data)] + [""])

    def _data_correct(self):
        """Determine if the edits made to the data were correct."""
        edited_previous = False
        edits, edited_idx, edited_old, edited_new = [0, 0, 0]
        for idx, (start, end) in enumerate(zip(self._start_data,
                                               self._end_data)):
            expect_edit = True
            if idx == 0 or not edited_previous:
                # This is the first line, or we didn't edit the previous line.
                if start[0] < 7:
                    # (d) in the manual
                    if end[start[0]] != 0:
                        return False
                elif start.count(0) > 0:
                    # (e) in the manual
                    if end[start.index(0)] != 0xf:
                        return False
                else:
                    # Count odd numbers.
                    odds = [(i, v) for i, v in enumerate(start) if i % 2 == 1]
                    if len(odds) > 3:
                        # (f) in the manual
                        if end[odds[0][0]] != start[odds[0][0]] - 1:
                            return False
                    else:
                        # (x) in the manual - don't edit.
                        expect_edit = False
            elif idx + 1 == len(self._start_data):
                # This is the last line - (j) in the manual
                # The last value should match the total number of lines, and
                # the rest of the line should be unedited.
                if end[-1] != edits or end[:-1] != start[:-1]:
                    return False
            else:
                # A middle line, and we edited the previous line.
                if start[-1] < 7:
                    # (g) in the manual
                    if end[start[-1]] != edited_old:
                        return False
                elif start.count(0xf):
                    # (h) in the manual
                    if end[start.index(0xf)] != edited_idx:
                        return False
                elif start.count(edited_new):
                    # (i) in the manual
                    if end[start.index(edited_new)] != 0:
                        return False
                else:
                    # (x) in the manual - don't edit.
                    expect_edit = False

            edited_previous = start != end
            if edited_previous:
                edits += 1
                edited_idx = [i for i, (s, e) in enumerate(zip(start, end))
                              if s != e][0]
                edited_old = start[edited_idx]
                edited_new = end[edited_idx]

            # Check that we didn't edit a line we didn't expect to.
            # Note this doens't check that we didn't edit one we expected to -
            # the lines might have matched originally.
            if edited_previous and not expect_edit:
                return False

        return True
