"""Windows keyboard key-name -> KEY_* map, owned by the emulator_windows
backend (the only consumer), independent of the old OS's
config/emulator/win_keycodes.py."""

from __future__ import annotations

WIN_TO_LINUX_KEYCODE = {
    'a': 'KEY_A',
    'b': 'KEY_B',
    'c': 'KEY_C',
    'd': 'KEY_D',
    'e': 'KEY_E',
    'f': 'KEY_F',
    'g': 'KEY_G',
    'h': 'KEY_H',
    'i': 'KEY_I',
    'j': 'KEY_J',
    'k': 'KEY_K',
    'l': 'KEY_L',
    'm': 'KEY_M',
    'n': 'KEY_N',
    'o': 'KEY_O',
    'p': 'KEY_P',
    'q': 'KEY_Q',
    'r': 'KEY_R',
    's': 'KEY_S',
    't': 'KEY_T',
    'u': 'KEY_U',
    'v': 'KEY_V',
    'w': 'KEY_W',
    'x': 'KEY_X',
    'y': 'KEY_Y',
    'z': 'KEY_Z',

    '1': 'KEY_1',
    '2': 'KEY_2',
    '3': 'KEY_3',
    '4': 'KEY_4',
    '5': 'KEY_5',
    '6': 'KEY_6',
    '7': 'KEY_7',
    '8': 'KEY_8',
    '9': 'KEY_9',
    '0': 'KEY_0',

    'space': 'KEY_SPACE',
    'tab': 'KEY_TAB',
    'enter': 'KEY_ENTER',
    'backspace': 'KEY_BACKSPACE',
    'minus': 'KEY_MINUS',
    'equal': 'KEY_EQUAL',
    'left bracket': 'KEY_LEFTBRACE',
    'right bracket': 'KEY_RIGHTBRACE',
    'semicolon': 'KEY_SEMICOLON',
    'apostrophe': 'KEY_APOSTROPHE',
    'comma': 'KEY_COMMA',
    'dot': 'KEY_DOT',
    'slash': 'KEY_SLASH',
    '/': 'KEY_SLASH',
    '?': 'KEY_SLASH',
    'grave': 'KEY_GRAVE',  # The backtick key `
    'backslash': 'KEY_BACKSLASH',
    '\\': 'KEY_BACKSLASH',
    '|': 'KEY_BACKSLASH',
    "'": 'KEY_APOSTROPHE',
    '"': 'KEY_QUOTE',
    '_': 'KEY_UNDERSCORE',
    '+': 'KEY_PLUS',
    '=': 'KEY_EQUAL',
    '-': 'KEY_MINUS',

    # The `keyboard` library sometimes reports a key's SHIFTED character as
    # its name instead of the physical key (already true for '?' above) --
    # these map that shifted character back to the same base physical
    # keycode as its unshifted digit/symbol, so shift state stays purely a
    # matter of tracking KEY_LEFTSHIFT and is resolved once, centrally, in
    # bootstrap.py (see core_os/packages/input/keymap.py's shift_key_map)
    # rather than here.
    '!': 'KEY_1',
    '@': 'KEY_2',
    '#': 'KEY_3',
    '$': 'KEY_4',
    '%': 'KEY_5',
    '^': 'KEY_6',
    '&': 'KEY_7',
    '*': 'KEY_8',
    '(': 'KEY_9',
    ')': 'KEY_0',
    '{': 'KEY_LEFTBRACE',
    '}': 'KEY_RIGHTBRACE',
    '<': 'KEY_COMMA',
    '>': 'KEY_DOT',

    'volume up': 'KEY_VOLUMEUP',
    'volume down': 'KEY_VOLUMEDOWN',

    'esc': 'KEY_ESC',
    'escape': 'KEY_ESC',
    'f10': 'KEY_F10',

    # Modifiers
    'left shift': 'KEY_LEFTSHIFT',
    'right shift': 'KEY_LEFTSHIFT',
    'shift': 'KEY_LEFTSHIFT',

    'left ctrl': 'KEY_LEFTCTRL',
    'right ctrl': 'KEY_RIGHTCTRL',
    'ctrl': 'KEY_LEFTCTRL',

    'left alt': 'KEY_LEFTALT',
    'right alt': 'KEY_RIGHTALT',
    'alt': 'KEY_LEFTALT',

    # No FN key on a normal keyboard -- the device has two (FN1/FN2, one at
    # each end of the bottom row), stand-ins bound to the two Windows keys
    # so the fn symbol layer (core_os/packages/input/keymap.py's
    # fn_key_map) is reachable in the emulator too.
    'left windows': 'KEY_FN1',
    'right windows': 'KEY_FN2',
    'windows': 'KEY_FN1',

    # arrow keys
    'up': 'KEY_UP',
    'down': 'KEY_DOWN',
    'left': 'KEY_LEFT',
    'right': 'KEY_RIGHT',
}
