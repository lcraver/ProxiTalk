"""A small incremental romaji -> hiragana converter — a real IME-style
mora-by-mora parser, not the whole-string keyword-heuristic in
utils/japanese.py (which only fires on a handful of known words/patterns
and can't handle partial/in-progress input).

convert_romaji(buffer) re-parses the full buffer from scratch on every
call (cheap for short phrases) and returns (kana_so_far, pending_tail):
  - kana_so_far: every mora that's been unambiguously resolved to kana.
  - pending_tail: the trailing, not-yet-resolved romaji (e.g. a lone
    consonant waiting for its vowel) — rendered as-is in Latin until it
    resolves, which is what gives the "converts as you keep typing" feel.

Handles the cases a naive substring-replace can't:
  - Sokuon (doubled consonant -> っ): "kka" -> "っか", "tte" -> "って"
  - The "n" ambiguity: "nn" -> "ん" explicitly; a single "n" followed by a
    consonant (not a/i/u/e/o/y) also commits to "ん" ("konnichiwa"'s first
    "n" via "nn", but "senkou"-style "n"+consonant works too); a lone
    trailing "n" stays pending until it's disambiguated.
  - Digraphs (consonant + y/h + vowel) in multiple common romanizations:
    both Hepburn ("sha", "chu") and kunrei-shiki ("sya", "tyu"), plus the
    "cy" alternate spelling some IMEs accept ("cyu" -> "ちゅ").
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# 1-character mora: bare vowels.
_MORA_1: Dict[str, str] = {
    'a': 'あ', 'i': 'い', 'u': 'う', 'e': 'え', 'o': 'お',
}

# 2-character mora: consonant + vowel, plus common 2-char alternate spellings.
_MORA_2: Dict[str, str] = {
    'ka': 'か', 'ki': 'き', 'ku': 'く', 'ke': 'け', 'ko': 'こ',
    'sa': 'さ', 'si': 'し', 'su': 'す', 'se': 'せ', 'so': 'そ',
    'ta': 'た', 'ti': 'ち', 'tu': 'つ', 'te': 'て', 'to': 'と',
    'na': 'な', 'ni': 'に', 'nu': 'ぬ', 'ne': 'ね', 'no': 'の',
    'ha': 'は', 'hi': 'ひ', 'hu': 'ふ', 'he': 'へ', 'ho': 'ほ', 'fu': 'ふ',
    'ma': 'ま', 'mi': 'み', 'mu': 'む', 'me': 'め', 'mo': 'も',
    'ya': 'や', 'yu': 'ゆ', 'yo': 'よ',
    'ra': 'ら', 'ri': 'り', 'ru': 'る', 're': 'れ', 'ro': 'ろ',
    'wa': 'わ', 'wo': 'を',
    'ga': 'が', 'gi': 'ぎ', 'gu': 'ぐ', 'ge': 'げ', 'go': 'ご',
    'za': 'ざ', 'zi': 'じ', 'zu': 'ず', 'ze': 'ぜ', 'zo': 'ぞ', 'ji': 'じ',
    'da': 'だ', 'di': 'ぢ', 'du': 'づ', 'de': 'で', 'do': 'ど',
    'ba': 'ば', 'bi': 'び', 'bu': 'ぶ', 'be': 'べ', 'bo': 'ぼ',
    'pa': 'ぱ', 'pi': 'ぴ', 'pu': 'ぷ', 'pe': 'ぺ', 'po': 'ぽ',
    'ja': 'じゃ', 'ju': 'じゅ', 'jo': 'じょ',
}

# 3-character mora: the 3-letter alternate spellings of a few 2-char base
# syllables ("shi"/"chi"/"tsu"), plus consonant/digraph + small-y kana in
# Hepburn ("sha"), kunrei-shiki ("sya"), and common alternate ("cya")
# spellings. These are genuinely 3 characters long -- putting them in the
# 2-char table (as an earlier version of this file did) meant the fixed-
# length slice in _match_mora would never find them.
_MORA_3: Dict[str, str] = {
    'shi': 'し', 'chi': 'ち', 'tsu': 'つ',
}


def _add_digraph(base_kana: str, small: str, *romaji_prefixes: str) -> None:
    for prefix in romaji_prefixes:
        _MORA_3[prefix + 'a'] = base_kana + small + 'ゃ'
        _MORA_3[prefix + 'u'] = base_kana + small + 'ゅ'
        _MORA_3[prefix + 'o'] = base_kana + small + 'ょ'


_add_digraph('き', '', 'ky')
_add_digraph('し', '', 'sy', 'sh')
_add_digraph('ち', '', 'ty', 'ch', 'cy')
_add_digraph('に', '', 'ny')
_add_digraph('ひ', '', 'hy')
_add_digraph('み', '', 'my')
_add_digraph('り', '', 'ry')
_add_digraph('ぎ', '', 'gy')
_add_digraph('じ', '', 'zy', 'jy')
_add_digraph('び', '', 'by')
_add_digraph('ぴ', '', 'py')
_add_digraph('ぢ', '', 'dy')

# Consonants that participate in sokuon (doubled-consonant -> っ). Vowels
# and 'n' are excluded -- 'n' doubling is the separate "nn" -> "ん" rule.
_SOKUON_CONSONANTS = set('kstpgzdbcfjhmry')


def _match_mora(text: str, i: int) -> Optional[Tuple[str, int]]:
    """Longest-match mora lookup starting at text[i:]. Returns (kana, length)."""
    for table, length in ((_MORA_3, 3), (_MORA_2, 2), (_MORA_1, 1)):
        chunk = text[i:i + length]
        if len(chunk) == length and chunk in table:
            return table[chunk], length
    return None


def convert_romaji(buffer: str) -> Tuple[str, str]:
    """Parse `buffer` (raw typed romaji) into (kana_so_far, pending_tail)."""
    s = buffer.lower()
    n = len(s)
    out = []
    i = 0

    while i < n:
        ch = s[i]

        # Sokuon: doubled consonant (not 'n') followed by a mora -> っ + mora.
        if ch in _SOKUON_CONSONANTS and i + 1 < n and s[i + 1] == ch:
            matched = _match_mora(s, i + 1)
            if matched:
                kana, length = matched
                out.append('っ')
                out.append(kana)
                i += 1 + length
                continue

        # A run of 2+ consecutive n's collapses to exactly ONE ん, no matter
        # how long the run is -- there's no standard romaji convention for
        # a second, distinct ん here, so "nnn"/"nnnn"/... are treated the
        # same as "nn" (almost always an accidental extra keystroke, not an
        # intentional extra mora).
        #
        # An earlier version only looked one character ahead (just "is the
        # NEXT char also n"), which meant a run of 3 n's triggered this
        # rule TWICE -- once for n1+n2, then again for n2+n3 -- producing
        # "こんんにちは" instead of "こんにちは" for "konnnichiwa".
        if ch == 'n' and i + 1 < n and s[i + 1] == 'n':
            run_len = 1
            while i + run_len < n and s[i + run_len] == 'n':
                run_len += 1
            out.append('ん')
            next_idx = i + run_len
            # Leave exactly one 'n' unconsumed ONLY when it can combine
            # with a following vowel/y mora ("nn"+"i" -> ん + "ni" -> んに)
            # -- that's the entire reason "nn" is used instead of a single
            # n in standard romaji. If nothing follows, or what follows is
            # a consonant, a single n there is already unambiguous on its
            # own (see the lone-n rule below), so leaving one behind just
            # produces a second, spurious ん -- verified: "sashinnwo"
            # (sa-shi-nn-wo, no vowel after the run) produced さしんんを
            # instead of さしんを, because the leftover n hit the lone-n
            # rule and became its own ん on top of the one already emitted
            # for the run.
            if next_idx < n and s[next_idx] in 'aiueoy':
                i += run_len - 1
            else:
                i += run_len
            continue

        matched = _match_mora(s, i)
        if matched:
            kana, length = matched
            out.append(kana)
            i += length
            continue

        # A lone 'n' not followed by a vowel/y/n is unambiguous -> ん
        # (can't be the start of na/ni/nu/ne/no/nya/nyu/nyo/nn at this point).
        if ch == 'n' and i + 1 < n and s[i + 1] not in 'aiueoyn':
            out.append('ん')
            i += 1
            continue

        # A character that can never start a mora (punctuation, spaces,
        # digits, already-kana/kanji, ...) isn't "waiting for more
        # keystrokes" -- pass it through as-is and keep converting what
        # comes after it. Without this, a single "?"/"!"/space partway
        # through a finished sentence hit the pending-tail break below and
        # silently left the rest of the sentence as unconverted romaji.
        if ch not in 'abcdefghijklmnopqrstuvwxyz':
            out.append(buffer[i])
            i += 1
            continue

        # Nothing resolves from here on (an incomplete Latin-letter mora,
        # e.g. a lone consonant awaiting its vowel) -- leave the rest
        # pending; this only fires for genuinely in-progress typing.
        break

    return ''.join(out), s[i:]


def convert_romaji_full(buffer: str) -> str:
    """Convenience: convert as much as possible, keeping any unresolved
    trailing romaji as-is (e.g. a lone consonant with no vowel yet)."""
    kana, pending = convert_romaji(buffer)
    return kana + pending
