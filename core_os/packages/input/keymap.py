"""core_os's own keycode -> character map, independent of the old OS's
config/keymap.py."""

from __future__ import annotations

key_map = {
    'KEY_A': 'a', 'KEY_B': 'b', 'KEY_C': 'c', 'KEY_D': 'd',
    'KEY_E': 'e', 'KEY_F': 'f', 'KEY_G': 'g', 'KEY_H': 'h',
    'KEY_I': 'i', 'KEY_J': 'j', 'KEY_K': 'k', 'KEY_L': 'l',
    'KEY_M': 'm', 'KEY_N': 'n', 'KEY_O': 'o', 'KEY_P': 'p',
    'KEY_Q': 'q', 'KEY_R': 'r', 'KEY_S': 's', 'KEY_T': 't',
    'KEY_U': 'u', 'KEY_V': 'v', 'KEY_W': 'w', 'KEY_X': 'x',
    'KEY_Y': 'y', 'KEY_Z': 'z',
    'KEY_1': '1', 'KEY_2': '2', 'KEY_3': '3', 'KEY_4': '4',
    'KEY_5': '5', 'KEY_6': '6', 'KEY_7': '7', 'KEY_8': '8',
    'KEY_9': '9', 'KEY_0': '0',
    'KEY_SPACE': ' ', 'KEY_ENTER': '\n', 'KEY_BACKSPACE': '',
    'KEY_MINUS': '-', 'KEY_EQUAL': '=', 'KEY_LEFTBRACE': '[',
    'KEY_RIGHTBRACE': ']', 'KEY_SEMICOLON': ';', 'KEY_APOSTROPHE': '\'',
    'KEY_COMMA': ',', 'KEY_DOT': '.', 'KEY_SLASH': '/', 'KEY_BACKSLASH': '\\',
    'KEY_QUOTE': '"', 'KEY_QUESTION': '?', 'KEY_EXCLAMATION': '!',
    'KEY_AT': '@', 'KEY_HASH': '#', 'KEY_DOLLAR': '$',
    'KEY_PIPE': '|', 'KEY_GRAVE': '`', 'KEY_TILDE': '~',
    'KEY_UNDERSCORE': '_', 'KEY_PLUS': '+',
    'KEY_PERCENT': '%', 'KEY_CARET': '^', 'KEY_AMPERSAND': '&',
    'KEY_ASTERISK': '*', 'KEY_LEFTPAREN': '(', 'KEY_RIGHTPAREN': ')',
    'KEY_COLON': ':', 'KEY_LESS': '<', 'KEY_GREATER': '>',
    'KEY_LEFTCURLY': '{', 'KEY_RIGHTCURLY': '}',
}

# Every shifted symbol reachable from a physical key that exists on either
# platform (Windows emulator's full keyboard, or the device's 5x10 matrix,
# which only has digits/shift/comma/colon among these) -- resolved centrally
# in bootstrap.py's dispatch loop via input.apply_shift_mapping(), the same
# place proxitalk.py (V1) resolves shift for the same reason: a physical key
# only identifies itself once, shift is a second, simultaneous key.
shift_key_map = {
    'KEY_SLASH': 'KEY_QUESTION',
    'KEY_BACKSLASH': 'KEY_PIPE',
    'KEY_GRAVE': 'KEY_TILDE',
    'KEY_SPACE': 'KEY_TAB',
    'KEY_MINUS': 'KEY_UNDERSCORE',
    'KEY_EQUAL': 'KEY_PLUS',
    'KEY_1': 'KEY_EXCLAMATION',
    'KEY_2': 'KEY_AT',
    'KEY_3': 'KEY_HASH',
    'KEY_4': 'KEY_DOLLAR',
    'KEY_5': 'KEY_PERCENT',
    'KEY_6': 'KEY_CARET',
    'KEY_7': 'KEY_AMPERSAND',
    'KEY_8': 'KEY_ASTERISK',
    'KEY_9': 'KEY_LEFTPAREN',
    'KEY_0': 'KEY_RIGHTPAREN',
    'KEY_COMMA': 'KEY_LESS',
    'KEY_DOT': 'KEY_GREATER',
    'KEY_LEFTBRACE': 'KEY_LEFTCURLY',
    'KEY_RIGHTBRACE': 'KEY_RIGHTCURLY',
}
