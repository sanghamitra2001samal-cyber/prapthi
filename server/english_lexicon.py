"""English words for Indian voices, from how the word SOUNDS, not how it is spelt.

Indian-language engines cannot read Latin script (MMS deletes it, svara drifts),
so an English word inside Tamil, Telugu, Bengali or Marathi text is rewritten in
that script first. Spelling rules alone guess badly ("you" -> याउ, "Monday" ->
मोन्ड), so the pronunciation comes from the CMU Pronouncing Dictionary
(data/cmudict, BSD-2, 135k words) and is written the way Indian English says it:
D/T as retroflex ड/ट, /æ/ as in बैंक, "-day" as डे.

Each script writes the same sounds its own way:

    bank      बैंक    ব্যাংক    బ్యాంక్    பேங்க்
    online    ऑनलाइन  অনলাইন   ఆన్లైన్      ஆன்லைன்

Hindi, Bengali and Marathi drop a word's final vowel when they read; Telugu
and Tamil say every vowel that is written, so their words get explicit viramas
wherever the sound has none.

Public: `pronounce(word, script)` -> the word in `script` ("deva", "beng",
"telu", "taml"), or None if the dictionary does not know it.
"""

from __future__ import annotations

import os
import threading

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cmudict", "cmudict.dict")
_LEX: dict[str, list[str]] | None = None
_LOCK = threading.Lock()

# Indian English says these differently from the American entry.
_OVERRIDES = {
    "monday": "M AH N D EY", "tuesday": "T Y UW Z D EY", "wednesday": "W EH N Z D EY",
    "thursday": "TH ER Z D EY", "friday": "F R AY D EY", "saturday": "S AE T ER D EY",
    "sunday": "S AH N D EY", "today": "T UH D EY", "birthday": "B ER TH D EY",
    "holiday": "HH AA L IH D EY", "whatsapp": "W AA T S AE P", "app": "AE P",
}


def _load() -> dict[str, list[str]]:
    global _LEX
    if _LEX is None:
        with _LOCK:
            if _LEX is None:
                lex: dict[str, list[str]] = {}
                try:
                    with open(_PATH, encoding="utf-8") as f:
                        for line in f:
                            word, _, phones = line.partition(" ")
                            if "(" in word or not phones:      # keep the first variant
                                continue
                            phones = phones.split("#")[0].split()
                            lex[word] = ["".join(c for c in p if not c.isdigit()) for p in phones]
                except OSError:
                    pass                                         # no dictionary: callers fall back
                _LEX = lex
    return _LEX


# Devanagari as the common spelling; the other scripts map from it.
_CONS = {
    "B": "ब", "CH": "च", "D": "ड", "DH": "द", "F": "फ़", "G": "ग", "HH": "ह", "JH": "ज",
    "K": "क", "L": "ल", "M": "म", "N": "न", "P": "प", "R": "र", "S": "स", "SH": "श",
    "T": "ट", "TH": "थ", "V": "व", "W": "\ue009", "Y": "य", "Z": "ज़", "ZH": "ज़",
}
# W and V are one letter in Devanagari, Telugu and Tamil, but Bengali writes w
# as ওয় (ওয়াটস্যাপ) and v as ভ, so W travels as a marker too.
_W = "\ue009"
# Indian English says "pass, class, after, chance" with the long a of British
# English, where the dictionary's American entry has the vowel of "bank".
_BATH = {"S", "F", "TH"}
# Vowels as (sign after a consonant, letter on its own). "" = the inherent vowel.
# The four sounds the scripts write differently travel as private-use markers
# (U+E001..E007; U+E000 after one means "the vowel on its own").
_AE, _AY, _AW, _EH = "\ue001", "\ue003", "\ue005", "\ue007"
_VOW = {
    "AA": ("ा", "आ"), "AE": (_AE, _AE + "\ue000"), "AH": ("", "अ"), "AO": ("ॉ", "ऑ"),
    "AW": (_AW, _AW + "\ue000"), "AY": (_AY, _AY + "\ue000"), "EH": (_EH, _EH + "\ue000"),
    "ER": ("", "अ"), "EY": ("े", "ए"), "IH": ("ि", "इ"), "IY": ("ी", "ई"), "OW": ("ो", "ओ"),
    "OY": ("ॉय", "ऑय"), "UH": ("ु", "उ"), "UW": ("ू", "ऊ"),
}
_NASAL_BEFORE = {"K", "G", "T", "D", "CH", "JH", "P", "B", "TH", "DH"}

# How each script writes the marked sounds: (vowel sign, vowel on its own).
_MARKS = {
    "deva": {_AE: ("ै", "ऐ"), _AY: ("ाइ", "आइ"), _AW: ("ाउ", "आउ"), _EH: ("े", "ए"), _W: ("व", "व")},
    "beng": {_AE: ("্যা", "অ্যা"), _AY: ("াই", "আই"), _AW: ("াউ", "আউ"), _EH: ("ে", "এ"), _W: ("ওয়", "ওয়")},
    "telu": {_AE: ("్యా", "యా"), _AY: ("ై", "ఐ"), _AW: ("ౌ", "ఔ"), _EH: ("ె", "ఎ"), _W: ("వ", "వ")},
    "taml": {_AE: ("ே", "ஆ"), _AY: ("ை", "ஐ"), _AW: ("ௌ", "ஔ"), _EH: ("ெ", "எ"), _W: ("வ", "வ")},
}


def _devanagari(phones: list[str], keep_final_virama: bool) -> str:
    """Write a phone sequence in Devanagari. A consonant with no vowel after it
    gets a virama, except word-finally in scripts that drop that vowel anyway.
    A nasal before a stop after a vowel is an anusvara (बैंक, अकाउंट); NG is
    anusvara + ग unless a K/G follows (मीटिंग, बैंक)."""
    out: list[str] = []
    n = len(phones)
    after_vowel = False
    phones = list(phones)
    for i in range(n - 1):
        if phones[i] == "AE" and (phones[i + 1] in _BATH or (
                phones[i + 1] == "N" and i + 2 < n and phones[i + 2] in ("T", "S", "CH"))):
            phones[i] = "AA"
    for i, p in enumerate(phones):
        nxt = phones[i + 1] if i + 1 < n else None
        if p in _VOW:
            sign, alone = _VOW[p]
            if p == "AH" and nxt is None:          # a final "a" is said: डेटा, कैमरा
                sign, alone = "ा", "आ"
            if p in ("IY", "IH") and nxt in _VOW:   # India: इंडिया, a y between the vowels
                out.append("ि" if out and not after_vowel else "इ")
                out.append("य")
                after_vowel = False
                continue
            out.append(sign if out and not after_vowel else alone)
            after_vowel = True
            if p == "ER":                       # "manager" -> मैनेजर: a vowel then र
                p = "R"
            else:
                continue
        elif after_vowel and p in ("N", "M", "NG") and nxt in _NASAL_BEFORE:
            out.append("ं")
            continue
        elif p == "NG":
            if after_vowel:
                out.append("ं")
            p = "G"
        out.append(_CONS[p])
        after_vowel = False
        if nxt is None:
            if keep_final_virama:
                out.append("्")
        elif nxt not in _VOW:
            out.append("्")
    return "".join(out)


def pronounce(word: str, script: str) -> str | None:
    """`word` in `script`, spelt from its pronunciation; None if unknown."""
    w = word.lower()
    phones = _OVERRIDES.get(w)
    phones = phones.split() if phones else _load().get(w)
    if not phones:
        return None
    dev = _devanagari(phones, keep_final_virama=script in ("telu", "taml"))
    from hinglish import dev_to_script            # hinglish imports us only lazily
    return fill_marks(dev_to_script(dev, script), script)


def fill_marks(text: str, script: str) -> str:
    """Replace the vowel markers with how `script` writes those sounds."""
    for mark, (sign, alone) in _MARKS[script].items():
        text = text.replace(mark + "\ue000", alone).replace(mark, sign)
    return text
