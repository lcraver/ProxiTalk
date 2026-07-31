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

    # Synthetic keycodes for SHIFT+letter -- there's no separate physical key
    # for an uppercase letter, so shift_key_map remaps KEY_A -> KEY_A_SHIFT
    # the same way it remaps KEY_1 -> KEY_EXCLAMATION, keeping this dict the
    # only place any keycode turns into a character.
    'KEY_A_SHIFT': 'A', 'KEY_B_SHIFT': 'B', 'KEY_C_SHIFT': 'C', 'KEY_D_SHIFT': 'D',
    'KEY_E_SHIFT': 'E', 'KEY_F_SHIFT': 'F', 'KEY_G_SHIFT': 'G', 'KEY_H_SHIFT': 'H',
    'KEY_I_SHIFT': 'I', 'KEY_J_SHIFT': 'J', 'KEY_K_SHIFT': 'K', 'KEY_L_SHIFT': 'L',
    'KEY_M_SHIFT': 'M', 'KEY_N_SHIFT': 'N', 'KEY_O_SHIFT': 'O', 'KEY_P_SHIFT': 'P',
    'KEY_Q_SHIFT': 'Q', 'KEY_R_SHIFT': 'R', 'KEY_S_SHIFT': 'S', 'KEY_T_SHIFT': 'T',
    'KEY_U_SHIFT': 'U', 'KEY_V_SHIFT': 'V', 'KEY_W_SHIFT': 'W', 'KEY_X_SHIFT': 'X',
    'KEY_Y_SHIFT': 'Y', 'KEY_Z_SHIFT': 'Z',
}

# Every shifted symbol reachable from a physical key that exists on either
# platform (Windows emulator's full keyboard, or the device's 5x10 matrix,
# which only has digits/shift/comma/colon among these) -- resolved centrally
# in bootstrap.py's dispatch loop via input.apply_modifier_mapping(), the same
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

    'KEY_A': 'KEY_A_SHIFT', 'KEY_B': 'KEY_B_SHIFT', 'KEY_C': 'KEY_C_SHIFT', 'KEY_D': 'KEY_D_SHIFT',
    'KEY_E': 'KEY_E_SHIFT', 'KEY_F': 'KEY_F_SHIFT', 'KEY_G': 'KEY_G_SHIFT', 'KEY_H': 'KEY_H_SHIFT',
    'KEY_I': 'KEY_I_SHIFT', 'KEY_J': 'KEY_J_SHIFT', 'KEY_K': 'KEY_K_SHIFT', 'KEY_L': 'KEY_L_SHIFT',
    'KEY_M': 'KEY_M_SHIFT', 'KEY_N': 'KEY_N_SHIFT', 'KEY_O': 'KEY_O_SHIFT', 'KEY_P': 'KEY_P_SHIFT',
    'KEY_Q': 'KEY_Q_SHIFT', 'KEY_R': 'KEY_R_SHIFT', 'KEY_S': 'KEY_S_SHIFT', 'KEY_T': 'KEY_T_SHIFT',
    'KEY_U': 'KEY_U_SHIFT', 'KEY_V': 'KEY_V_SHIFT', 'KEY_W': 'KEY_W_SHIFT', 'KEY_X': 'KEY_X_SHIFT',
    'KEY_Y': 'KEY_Y_SHIFT', 'KEY_Z': 'KEY_Z_SHIFT',
}

# FN symbol layer -- every letter key remapped to the symbol printed on its
# second legend, resolved the same way as shift_key_map (letter keycode ->
# an existing symbol keycode, so key_map stays the single source of truth
# for the actual character). KEY_R/KEY_Z carry '.'/'_' rather than staying
# dead -- both recur multiple times per Python identifier/attribute chain
# (self.foo.bar, my_var_name), so they earn the single-modifier slot over
# lower-frequency symbols like '-'/'='/'+' that usually appear once per line
# (see fn_shift_key_map below for those).
fn_key_map = {
    'KEY_Q': 'KEY_EXCLAMATION', 'KEY_W': 'KEY_QUOTE', 'KEY_E': 'KEY_AT',
    'KEY_R': 'KEY_DOT',
    'KEY_T': 'KEY_DOLLAR', 'KEY_Y': 'KEY_PERCENT', 'KEY_U': 'KEY_CARET',
    'KEY_I': 'KEY_AMPERSAND', 'KEY_O': 'KEY_LEFTPAREN', 'KEY_P': 'KEY_RIGHTPAREN',
    'KEY_A': 'KEY_PIPE', 'KEY_S': 'KEY_HASH', 'KEY_D': 'KEY_COMMA',
    'KEY_F': 'KEY_QUESTION', 'KEY_G': 'KEY_APOSTROPHE', 'KEY_H': 'KEY_COLON',
    'KEY_J': 'KEY_SEMICOLON', 'KEY_K': 'KEY_LEFTCURLY', 'KEY_L': 'KEY_RIGHTCURLY',
    'KEY_Z': 'KEY_UNDERSCORE',
    'KEY_X': 'KEY_BACKSLASH', 'KEY_C': 'KEY_TILDE', 'KEY_V': 'KEY_LESS',
    'KEY_B': 'KEY_GREATER', 'KEY_N': 'KEY_LEFTBRACE', 'KEY_M': 'KEY_RIGHTBRACE',
}

# FN+SHIFT together: the QWERTYUIOP row is the digit row (Q=1 ... P=0).
# The rest of the alpha block carries the remaining coding symbols that
# don't have a physical key or an fn_key_map slot yet -- lower-usage-in-
# Python than fn_key_map's contents (each normally shows up once per line
# rather than repeatedly per identifier), which is why they're behind the
# extra modifier instead of on fn alone. Everything else stays absent/dead,
# same as before.
fn_shift_key_map = {
    'KEY_Q': 'KEY_1', 'KEY_W': 'KEY_2', 'KEY_E': 'KEY_3', 'KEY_R': 'KEY_4',
    'KEY_T': 'KEY_5', 'KEY_Y': 'KEY_6', 'KEY_U': 'KEY_7', 'KEY_I': 'KEY_8',
    'KEY_O': 'KEY_9', 'KEY_P': 'KEY_0',
    'KEY_S': 'KEY_MINUS', 'KEY_D': 'KEY_EQUAL', 'KEY_F': 'KEY_PLUS',
    'KEY_V': 'KEY_SLASH', 'KEY_C': 'KEY_GRAVE',
}
