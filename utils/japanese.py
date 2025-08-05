"""
Japanese text processing utilities for ProxiTalk
Handles romanji detection and conversion to hiragana
"""

def detect_and_convert_romanji(text):
    """
    Detect Japanese romanji text and convert to hiragana for preview/synthesis
    
    Args:
        text (str): Input text to analyze
        
    Returns:
        tuple: (converted_text, is_japanese_detected)
            - converted_text: Hiragana conversion if Japanese detected, None otherwise
            - is_japanese_detected: Boolean indicating if Japanese was detected
    """
    # Common romanji to hiragana mappings
    romanji_map = {
        # Basic vowels
        'a': 'あ', 'i': 'い', 'u': 'う', 'e': 'え', 'o': 'お',
        
        # K sounds
        'ka': 'か', 'ki': 'き', 'ku': 'く', 'ke': 'け', 'ko': 'こ',
        'kya': 'きゃ', 'kyu': 'きゅ', 'kyo': 'きょ',
        
        # G sounds
        'ga': 'が', 'gi': 'ぎ', 'gu': 'ぐ', 'ge': 'げ', 'go': 'ご',
        'gya': 'ぎゃ', 'gyu': 'ぎゅ', 'gyo': 'ぎょ',
        
        # S sounds
        'sa': 'さ', 'shi': 'し', 'su': 'す', 'se': 'せ', 'so': 'そ',
        'sha': 'しゃ', 'shu': 'しゅ', 'sho': 'しょ',
        
        # Z sounds
        'za': 'ざ', 'ji': 'じ', 'zu': 'ず', 'ze': 'ぜ', 'zo': 'ぞ',
        'ja': 'じゃ', 'ju': 'じゅ', 'jo': 'じょ',
        
        # T sounds
        'ta': 'た', 'chi': 'ち', 'tsu': 'つ', 'te': 'て', 'to': 'と',
        'cha': 'ちゃ', 'chu': 'ちゅ', 'cho': 'ちょ',
        
        # D sounds
        'da': 'だ', 'di': 'ぢ', 'du': 'づ', 'de': 'で', 'do': 'ど',
        
        # N sounds
        'na': 'な', 'ni': 'に', 'nu': 'ぬ', 'ne': 'ね', 'no': 'の',
        'nya': 'にゃ', 'nyu': 'にゅ', 'nyo': 'にょ',
        
        # H sounds
        'ha': 'は', 'hi': 'ひ', 'fu': 'ふ', 'he': 'へ', 'ho': 'ほ',
        'hya': 'ひゃ', 'hyu': 'ひゅ', 'hyo': 'ひょ',
        
        # B sounds
        'ba': 'ば', 'bi': 'び', 'bu': 'ぶ', 'be': 'べ', 'bo': 'ぼ',
        'bya': 'びゃ', 'byu': 'びゅ', 'byo': 'びょ',
        
        # P sounds
        'pa': 'ぱ', 'pi': 'ぴ', 'pu': 'ぷ', 'pe': 'ぺ', 'po': 'ぽ',
        'pya': 'ぴゃ', 'pyu': 'ぴゅ', 'pyo': 'ぴょ',
        
        # M sounds
        'ma': 'ま', 'mi': 'み', 'mu': 'む', 'me': 'め', 'mo': 'も',
        'mya': 'みゃ', 'myu': 'みゅ', 'myo': 'みょ',
        
        # Y sounds
        'ya': 'や', 'yu': 'ゆ', 'yo': 'よ',
        
        # R sounds
        'ra': 'ら', 'ri': 'り', 'ru': 'る', 're': 'れ', 'ro': 'ろ',
        'rya': 'りゃ', 'ryu': 'りゅ', 'ryo': 'りょ',
        
        # W sounds
        'wa': 'わ', 'wo': 'を',
        
        # N
        'n': 'ん',
        
        # Common words
        'konnichiwa': 'こんにちは',
        'arigatou': 'ありがとう',
        'ohayou': 'おはよう',
        'sayounara': 'さようなら',
        'hajimemashite': 'はじめまして',
        'yoroshiku': 'よろしく',
        'sumimasen': 'すみません',
        'gomen': 'ごめん',
        'watashi': 'わたし',
        'anata': 'あなた',
        'kore': 'これ',
        'sore': 'それ',
        'are': 'あれ',
        'koko': 'ここ',
        'soko': 'そこ',
        'asoko': 'あそこ',
        'desu': 'です',
        'masu': 'ます',
        'dayo': 'だよ',
        'dane': 'だね',
        'nani': 'なに',
        'doko': 'どこ',
        'dare': 'だれ',
        'itsu': 'いつ',
        'naze': 'なぜ',
        'doushite': 'どうして',
        'pen': 'ペン',
        'aishiteru': 'あいしてる',
        'suki': 'すき',
        'kirai': 'きらい',
        'genki': 'げんき',
        'tanoshii': 'たのしい',
        'ureshii': 'うれしい',
        'kanashii': 'かなしい',
        'oishi': 'おいし',
        'atatakai': 'あたたかい',
        'samui': 'さむい',
        'atsui': 'あつい',
        'tsukue': 'つくえ',
        'hon': 'ほん',
        'mizu': 'みず',
        'gohan': 'ごはん',
        'neko': 'ねこ',
        'inu': 'いぬ',
        'tori': 'とり',
        'sakana': 'さかな',
        'kuruma': 'くるま',
        'densha': 'でんしゃ',
        'hikouki': 'ひこうき',
    }
    
    # Check if text is likely romanji (contains only ASCII and common romanji patterns)
    if not text:
        return None, False
        
    # If text already contains Japanese characters, don't convert
    if any('\u3040' <= char <= '\u309F' or '\u30A0' <= char <= '\u30FF' or '\u4E00' <= char <= '\u9FAF' for char in text):
        return None, False
    
    # Check if text looks like romanji (lowercase ASCII with common Japanese sounds)
    text_lower = text.lower()
    
    # More selective romanji detection - look for common Japanese word patterns
    strong_romanji_indicators = [
        'konnichiwa', 'arigatou', 'ohayou', 'sayounara', 'hajimemashite',
        'yoroshiku', 'sumimasen', 'gomen', 'watashi', 'anata', 'genki',
        'desu', 'masu', 'suki', 'kirai', 'oishi', 'tanoshii', 'ureshii',
        'kore wa', 'sore wa', 'are wa', 'kore desu', 'sore desu', 'are desu',
        'nani desu', 'doko desu', 'dare desu', 'itsu desu', 'naze desu',
        'pen desu', 'hon desu', 'mizu desu', 'gohan desu'
    ]
    
    # Check for strong indicators first
    has_strong_indicator = any(indicator in text_lower for indicator in strong_romanji_indicators)
    
    # If no strong indicators, check for syllable patterns but be more conservative
    syllable_indicators = ['ka', 'ki', 'ku', 'ke', 'ko', 'sa', 'shi', 'su', 'se', 'so', 
                        'ta', 'chi', 'tsu', 'te', 'to', 'na', 'ni', 'nu', 'ne', 'no',
                        'ha', 'hi', 'fu', 'ma', 'mi', 'mu', 'me', 'mo',
                        'ya', 'yu', 'yo', 'ra', 'ri', 'ru', 're', 'ro']
    
    # Count how many syllables match and require higher threshold for pure syllable detection
    syllable_matches = sum(1 for indicator in syllable_indicators if indicator in text_lower)
    
    # Also check if text contains obvious English words
    common_english_words = ['hello', 'world', 'thank', 'you', 'the', 'and', 'but', 'with', 'have', 'this', 'that', 'from', 'they', 'know', 'want', 'been', 'good', 'much', 'some', 'time', 'very', 'when', 'come', 'here', 'just', 'like', 'long', 'make', 'many', 'over', 'such', 'take', 'than', 'them', 'well', 'were', 'what']
    has_english_words = any(word in text_lower for word in common_english_words)
    
    # Check if individual words look like romanji (for spaced romanji text)
    words = text_lower.split()
    romanji_word_count = 0
    for word in words:
        # Check if word contains romanji syllables or is in our romanji map
        word_syllable_matches = sum(1 for indicator in syllable_indicators if indicator in word)
        if word in romanji_map or word_syllable_matches >= 1:
            romanji_word_count += 1
    
    # Calculate romanji word ratio
    romanji_word_ratio = romanji_word_count / len(words) if words else 0
    
    # Determine if text is likely romanji
    if has_strong_indicator:
        is_likely_romanji = True
    elif has_english_words:
        is_likely_romanji = False  # Don't convert obvious English
    elif syllable_matches >= 2 and len(words) <= 3:  # Multiple syllables in short text
        is_likely_romanji = True
    elif romanji_word_ratio >= 0.5 and syllable_matches >= 2:  # At least half the words look like romanji
        is_likely_romanji = True
    else:
        is_likely_romanji = False
    
    if not is_likely_romanji:
        return None, False
    
    # Convert the text
    converted_text = text_lower
    
    # Sort by length (longest first) to handle multi-character combinations
    sorted_romanji = sorted(romanji_map.keys(), key=len, reverse=True)
    
    for romanji in sorted_romanji:
        if romanji in converted_text:
            converted_text = converted_text.replace(romanji, romanji_map[romanji])
    
    return converted_text, True


def convert_romanji_to_hiragana(text):
    """
    Convert romanized Japanese to hiragana for synthesis (legacy interface)
    
    Args:
        text (str): Input text to convert
        
    Returns:
        str: Converted text (original if not detected as Japanese)
    """
    converted_text, is_japanese = detect_and_convert_romanji(text)
    if is_japanese and converted_text:
        print(f"[Japanese] Detected romanji text: '{text}'")
        print(f"[Japanese] Converted to hiragana: '{converted_text}'")
        
        # Remove spaces from converted Japanese text for TTS synthesis
        # Japanese TTS engines typically work better without spaces
        converted_text_no_spaces = converted_text.replace(' ', '')
        print(f"[Japanese] Removed spaces for TTS: '{converted_text_no_spaces}'")
        
        return converted_text_no_spaces
    return text


def is_japanese_text(text):
    """
    Check if text contains Japanese characters
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if text contains Japanese characters
    """
    if not text:
        return False
    return any('\u3040' <= char <= '\u309F' or '\u30A0' <= char <= '\u30FF' or '\u4E00' <= char <= '\u9FAF' for char in text)


def is_romanji_text(text):
    """
    Check if text is likely romanized Japanese
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if text is likely romanji
    """
    _, is_japanese = detect_and_convert_romanji(text)
    return is_japanese
