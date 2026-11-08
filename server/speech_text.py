"""Say numbers the way a person would, for Hindi, Bhojpuri and English voices.

Every engine we serve reads digits badly in its own way. Measured on the live
demo (29 Oct 2026): Hindi voices turned "₹2,450" into an English "two four
five zero" or skipped the rupee sign, a phone number like "1800 123 4567" came
out as "eighteen hundred, one hundred twenty-three ...", and the IndicF5 and
svara models, which only know Devanagari, simply dropped what they could not
read. So the text is rewritten into words *before* it reaches any engine:

    ₹2,450         -> दो हज़ार चार सौ पचास रुपये   /  two thousand four hundred and fifty rupees
    1800 123 4567  -> एक आठ शून्य शून्य, एक दो तीन, ...  (digit by digit, grouped)
    10:30 am       -> सुबह साढ़े दस बजे           /  ten thirty a.m.
    15/08/2026     -> पंद्रह अगस्त दो हज़ार छब्बीस   /  fifteenth August twenty twenty-six
    18%            -> अठारह प्रतिशत               /  eighteen percent
    UPI            -> यू पी आई  (Hindi voices only; English voices spell it themselves)

Indian grouping (5,00,000) and anything in rupees is read in lakh and crore in
English too, because that is how Indian listeners say it. Western grouping
without a currency stays Western.

Tamil, Telugu, Bengali and Marathi get the same treatment (see _IndicLang).
Measured 6 Nov 2026 on the live voices: a sentence with "₹1,500", "15/08/2026",
"10:30" or "25%" came back 20-74% wrong (per-language Vakyansh recogniser,
character error) against 0-12% for the same sentence written out in words,
on every engine. The digits were read as invented words ("₹1,500" in Tamil
came out as "ஏய்த்தா பன்தீசா பஞ்சார"), or skipped (IndicF5 clips ran 25-53%
short).

Only `expand(text, lang)` is public. Other languages pass through unchanged.
"""

from __future__ import annotations

import re
import unicodedata

try:  # AI4Bharat's number tables (MIT); without them ta/te/bn/mr pass through
    from indic_numtowords import num2words as _indic_num2words
except Exception:  # noqa: BLE001 — a missing optional package must not stop speech
    _indic_num2words = None

# --------------------------------------------------------------------------- #
# Hindi number words. 1-99 are all irregular in Hindi, so they are a table.
# --------------------------------------------------------------------------- #
_HI_0_99 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ "
    "दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस "
    "तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस "
    "चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास "
    "पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ "
    "साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर "
    "सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी "
    "नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()
assert len(_HI_0_99) == 100

_HI_MONTHS = ("जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर "
              "नवंबर दिसंबर").split()


def _hi_int(n: int) -> str:
    if n < 100:
        return _HI_0_99[n]
    out = []
    crore, n = divmod(n, 10_000_000)
    if crore:
        out.append(f"{_hi_int(crore)} करोड़")
    lakh, n = divmod(n, 100_000)
    if lakh:
        out.append(f"{_HI_0_99[lakh]} लाख")
    thousand, n = divmod(n, 1000)
    if thousand:
        out.append(f"{_HI_0_99[thousand]} हज़ार")
    hundred, n = divmod(n, 100)
    if hundred:
        out.append(f"{_HI_0_99[hundred]} सौ")
    if n:
        out.append(_HI_0_99[n])
    return " ".join(out)


def _hi_number(n: int) -> str:
    """Like _hi_int, but 1100-1999 the way it is said aloud: उन्नीस सौ नब्बे."""
    if 1100 <= n <= 1999 and (n // 100) % 10:
        rest = n % 100
        return f"{_HI_0_99[n // 100]} सौ" + (f" {_HI_0_99[rest]}" if rest else "")
    return _hi_int(n)


def _hi_decimal(whole: int, frac: str) -> str:
    """3.5 -> साढ़े तीन, 1.5 -> डेढ़, 2.5 -> ढाई, 3.25 -> सवा तीन, else digit by digit."""
    if frac in ("5", "50"):
        if whole == 1:
            return "डेढ़"
        if whole == 2:
            return "ढाई"
        if whole >= 3:
            return f"साढ़े {_hi_number(whole)}"
    if frac == "25" and whole >= 1:
        return f"सवा {_hi_number(whole)}"
    return f"{_hi_number(whole)} दशमलव " + " ".join(_HI_0_99[int(d)] for d in frac)


# --------------------------------------------------------------------------- #
# English number words, Indian (lakh/crore) or Western grouping.
# --------------------------------------------------------------------------- #
_EN_0_19 = ("zero one two three four five six seven eight nine ten eleven twelve "
            "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_EN_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_EN_MONTHS = ("January February March April May June July August September "
              "October November December").split()
_EN_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth",
           "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def _en_0_99(n: int) -> str:
    if n < 20:
        return _EN_0_19[n]
    t, u = divmod(n, 10)
    return _EN_TENS[t] + (f"-{_EN_0_19[u]}" if u else "")


def _en_0_999(n: int) -> str:
    h, r = divmod(n, 100)
    if not h:
        return _en_0_99(r)
    return f"{_EN_0_19[h]} hundred" + (f" and {_en_0_99(r)}" if r else "")


def _en_int(n: int, indian: bool) -> str:
    if n < 1000:
        return _en_0_999(n)
    out = []
    if indian:
        crore, n = divmod(n, 10_000_000)
        if crore:
            out.append(f"{_en_int(crore, True)} crore")
        lakh, n = divmod(n, 100_000)
        if lakh:
            out.append(f"{_en_0_99(lakh)} lakh")
        thousand, n = divmod(n, 1000)
        if thousand:
            out.append(f"{_en_0_99(thousand)} thousand")
    else:
        for size, word in ((10**9, "billion"), (10**6, "million"), (1000, "thousand")):
            big, n = divmod(n, size)
            if big:
                out.append(f"{_en_0_999(big)} {word}")
    if n:
        # "two thousand and fifty", but "two thousand four hundred and fifty"
        out.append(("and " if n < 100 else "") + _en_0_999(n))
    return " ".join(out)


def _en_ordinal(n: int) -> str:
    words = _en_int(n, False)
    head, _, last = words.rpartition(" ")
    if "-" in last:
        a, b = last.rsplit("-", 1)
        last = f"{a}-{_en_ord_word(b)}"
    else:
        last = _en_ord_word(last)
    return f"{head} {last}".strip()


def _en_ord_word(w: str) -> str:
    if w in _EN_ORD:
        return _EN_ORD[w]
    if w.endswith("y"):
        return w[:-1] + "ieth"
    return w + "th"


def _en_year(n: int) -> str:
    if 2000 <= n <= 2009:
        return "two thousand" + (f" and {_EN_0_19[n % 10]}" if n % 10 else "")
    if 1100 <= n <= 2099:
        hi, lo = divmod(n, 100)
        if lo == 0:
            return f"{_en_0_99(hi)} hundred"
        return f"{_en_0_99(hi)} " + (f"oh {_EN_0_19[lo]}" if lo < 10 else _en_0_99(lo))
    return _en_int(n, False)


# --------------------------------------------------------------------------- #
# Per-language vocabulary
# --------------------------------------------------------------------------- #
_UNITS = {
    # unit: (hindi, english singular, english plural)
    "km": ("किलोमीटर", "kilometre", "kilometres"),
    "kg": ("किलो", "kilogram", "kilograms"),
    "g": ("ग्राम", "gram", "grams"),
    "gm": ("ग्राम", "gram", "grams"),
    "cm": ("सेंटीमीटर", "centimetre", "centimetres"),
    "mm": ("मिलीमीटर", "millimetre", "millimetres"),
    "m": ("मीटर", "metre", "metres"),
    "ml": ("मिलीलीटर", "millilitre", "millilitres"),
    "l": ("लीटर", "litre", "litres"),
    "kmph": ("किलोमीटर प्रति घंटा", "kilometre per hour", "kilometres per hour"),
    "km/h": ("किलोमीटर प्रति घंटा", "kilometre per hour", "kilometres per hour"),
    "hrs": ("घंटे", "hour", "hours"),
    "hr": ("घंटे", "hour", "hours"),
    "min": ("मिनट", "minute", "minutes"),
    "mins": ("मिनट", "minute", "minutes"),
    "sec": ("सेकंड", "second", "seconds"),
    "gb": ("जीबी", "gigabyte", "gigabytes"),
    "mb": ("एमबी", "megabyte", "megabytes"),
    "°c": ("डिग्री सेल्सियस", "degree Celsius", "degrees Celsius"),
}

_LETTERS_HI = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ("ए बी सी डी ई एफ़ जी एच आई जे के एल एम एन ओ पी क्यू आर एस टी यू वी डब्ल्यू "
     "एक्स वाई ज़ेड").split()))
# Acronyms Indians say as a word, not letter by letter.
_ACRONYM_WORDS_HI = {
    "NASA": "नासा", "ISRO": "इसरो", "AIIMS": "एम्स", "UNESCO": "यूनेस्को",
    "UNICEF": "यूनिसेफ़", "NATO": "नाटो", "COVID": "कोविड", "WIFI": "वाईफ़ाई",
    "PIN": "पिन", "OK": "ओके", "SIM": "सिम", "RAM": "रैम", "LED": "एलईडी",
}
_TITLES = {
    "dr.": ("डॉक्टर", "Doctor"), "mr.": ("मिस्टर", "Mister"),
    "mrs.": ("मिसेज़", "Missus"), "ms.": ("मिज़", "Miz"),
    "prof.": ("प्रोफ़ेसर", "Professor"), "st.": ("सेंट", "Saint"),
}


class _Lang:
    """What a language says for each piece. Bhojpuri shares Hindi's numerals
    (that is how they are written and read in Bhojpuri media), but it counts
    money in रुपया, not the Hindi oblique plural रुपये."""

    def __init__(self, code: str):
        self.code = code
        self.hi = code in ("hi", "bho")

    def int(self, n: int, indian: bool = True) -> str:
        if self.hi:
            return _hi_number(n)
        return _en_int(n, indian)

    def digit(self, d: str) -> str:
        return _HI_0_99[int(d)] if self.hi else _EN_0_19[int(d)]

    def money(self, whole: int, paise: int, indian: bool, symbol: str) -> str:
        if symbol == "$":
            unit = "डॉलर" if self.hi else ("dollar" if whole == 1 else "dollars")
            sub = "सेंट" if self.hi else ("cent" if paise == 1 else "cents")
        else:
            if self.code == "bho":
                unit = "रुपया"
            elif self.hi:
                unit = "रुपया" if whole == 1 else "रुपये"
            else:
                unit = "rupee" if whole == 1 else "rupees"
            sub = "पैसे" if self.hi else ("paisa" if paise == 1 else "paise")
        out = f"{self.int(whole, indian)} {unit}"
        if paise:
            joiner = " " if self.hi else " and "
            out += f"{joiner}{self.int(paise)} {sub}"
        return out

    def percent(self, num: str) -> str:
        return f"{self.decimal(num)} " + ("प्रतिशत" if self.hi else "percent")

    def decimal(self, num: str) -> str:
        num = num.replace(",", "")
        if "." not in num:
            return self.int(int(num), indian=False)
        whole, frac = num.split(".", 1)
        whole_i = int(whole or 0)
        if self.hi:
            return _hi_decimal(whole_i, frac)
        return f"{_en_int(whole_i, False)} point " + " ".join(_EN_0_19[int(d)] for d in frac)

    def date(self, d: int, m: int, y: int | None) -> str:
        if self.hi:
            out = f"{_hi_number(d)} {_HI_MONTHS[m - 1]}"
            return out + (f" {_hi_number(y)}" if y else "")
        out = f"{_en_ordinal(d)} {_EN_MONTHS[m - 1]}"
        return out + (f" {_en_year(y)}" if y else "")

    def time(self, h: int, m: int, ampm: str) -> str:
        ampm = ampm.lower().replace(".", "")
        if self.hi:
            h24 = h + 12 if ampm == "pm" and h < 12 else (0 if ampm == "am" and h == 12 else h)
            part = ""
            if ampm or h > 12:
                part = ("रात" if h24 < 4 or h24 >= 20 else "सुबह" if h24 < 12
                        else "दोपहर" if h24 < 16 else "शाम")
            h12 = h24 % 12 or 12
            nxt = h12 % 12 + 1
            if m == 0:
                spoken = f"{_hi_number(h12)} बजे"
            elif m == 30:
                spoken = {1: "डेढ़ बजे", 2: "ढाई बजे"}.get(h12, f"साढ़े {_hi_number(h12)} बजे")
            elif m == 15:
                spoken = f"सवा {_hi_number(h12)} बजे"
            elif m == 45:
                spoken = "पौने एक बजे" if nxt == 1 else f"पौने {_hi_number(nxt)} बजे"
            else:
                spoken = f"{_hi_number(h12)} बजकर {_hi_number(m)} मिनट"
            return f"{part} {spoken}".strip()
        if h > 12 and not ampm:
            h, ampm = h - 12, "pm"
        mins = "" if m == 0 else (f" oh {_EN_0_19[m]}" if m < 10 else f" {_en_0_99(m)}")
        tail = {"am": " a.m.", "pm": " p.m."}.get(ampm, "" if m else " o'clock")
        return f"{_en_0_99(h)}{mins}{tail}"

    def range_join(self) -> str:
        return " से " if self.hi else " to "

    def unit(self, key: str, n_text: str, n_value: float) -> str:
        hi, one, many = _UNITS[key]
        if self.hi:
            return f"{n_text} {hi}"
        return f"{n_text} {one if n_value == 1 else many}"

    # -- pieces expand() asks every language for -------------------------- #
    @property
    def plus(self) -> str:
        return "प्लस" if self.hi else "plus"

    @property
    def and_word(self) -> str:
        return "और" if self.hi else "and"

    def range(self, a: str, b: str) -> str:
        return f"{a}{self.range_join()}{b}"

    def year(self, n: int) -> str:
        return _hi_number(n) if self.hi else _en_year(n)

    def scaled_money(self, amount: str, scale: str, symbol: str) -> str:
        """₹5 lakh, $2 crore: the amount is already in words."""
        lakh = scale.startswith(("lakh", "लाख"))
        if self.hi:
            word = "लाख" if lakh else "करोड़"
            unit = "डॉलर" if symbol == "$" else ("रुपया" if self.code == "bho" else "रुपये")
        else:
            word = "lakh" if lakh else "crore"
            unit = "dollars" if symbol == "$" else "rupees"
        return f"{amount} {word} {unit}"

    def time_context(self, out: str, before: str, after: str) -> str:  # noqa: ARG002
        return out


# --------------------------------------------------------------------------- #
# Tamil, Telugu, Bengali, Marathi. Cardinals come from AI4Bharat's tables;
# everything a sentence wraps around them (rupees, months, percent, the way a
# time is said) is here, written the way it is read aloud, not as written in
# a form. Bengali and Marathi count money and time like Hindi (साडे / সাড়ে).
# --------------------------------------------------------------------------- #
_INDIC = {
    "ta": {
        "rupee": "ரூபாய்", "rupee1": "ரூபாய்", "paise": "பைசா",
        "dollar": "டாலர்", "cent": "சென்ட்", "percent": "சதவீதம்",
        "point": "புள்ளி", "plus": "பிளஸ்", "and": "மற்றும்",
        "lakh": "லட்சம்", "crore": "கோடி", "range": "{a} முதல் {b}",
        "months": "ஜனவரி பிப்ரவரி மார்ச் ஏப்ரல் மே ஜூன் ஜூலை ஆகஸ்ட் செப்டம்பர் "
                  "அக்டோபர் நவம்பர் டிசம்பர்",
        "day": ("காலை", "மதியம்", "மாலை", "இரவு"),
        "units": {"km": "கிலோமீட்டர்", "kg": "கிலோ", "g": "கிராம்", "gm": "கிராம்",
                  "cm": "சென்டிமீட்டர்", "mm": "மில்லிமீட்டர்", "m": "மீட்டர்",
                  "ml": "மில்லிலிட்டர்", "l": "லிட்டர்", "kmph": "கிலோமீட்டர் வேகம்",
                  "km/h": "கிலோமீட்டர் வேகம்", "hrs": "மணி நேரம்", "hr": "மணி நேரம்",
                  "min": "நிமிடம்", "mins": "நிமிடம்", "sec": "வினாடி", "gb": "ஜிபி",
                  "mb": "எம்பி", "°c": "டிகிரி செல்சியஸ்"},
    },
    "te": {
        "rupee": "రూపాయలు", "rupee1": "రూపాయి", "paise": "పైసలు",
        "dollar": "డాలర్లు", "cent": "సెంట్లు", "percent": "శాతం",
        "point": "పాయింట్", "plus": "ప్లస్", "and": "మరియు",
        "lakh": "లక్షల", "crore": "కోట్ల", "range": "{a} నుండి {b}",
        "months": "జనవరి ఫిబ్రవరి మార్చి ఏప్రిల్ మే జూన్ జూలై ఆగస్టు సెప్టెంబర్ "
                  "అక్టోబర్ నవంబర్ డిసెంబర్",
        "day": ("ఉదయం", "మధ్యాహ్నం", "సాయంత్రం", "రాత్రి"),
        "units": {"km": "కిలోమీటర్లు", "kg": "కిలోలు", "g": "గ్రాములు", "gm": "గ్రాములు",
                  "cm": "సెంటీమీటర్లు", "mm": "మిల్లీమీటర్లు", "m": "మీటర్లు",
                  "ml": "మిల్లీలీటర్లు", "l": "లీటర్లు", "kmph": "కిలోమీటర్ల వేగం",
                  "km/h": "కిలోమీటర్ల వేగం", "hrs": "గంటలు", "hr": "గంటలు",
                  "min": "నిమిషాలు", "mins": "నిమిషాలు", "sec": "సెకన్లు", "gb": "జీబీ",
                  "mb": "ఎంబీ", "°c": "డిగ్రీల సెల్సియస్"},
    },
    "bn": {
        "rupee": "টাকা", "rupee1": "টাকা", "paise": "পয়সা",
        "dollar": "ডলার", "cent": "সেন্ট", "percent": "শতাংশ",
        "point": "দশমিক", "plus": "প্লাস", "and": "এবং",
        "lakh": "লাখ", "crore": "কোটি", "range": "{a} থেকে {b}",
        "months": "জানুয়ারি ফেব্রুয়ারি মার্চ এপ্রিল মে জুন জুলাই আগস্ট সেপ্টেম্বর "
                  "অক্টোবর নভেম্বর ডিসেম্বর",
        "day": ("সকাল", "দুপুর", "বিকেল", "রাত"),
        "units": {"km": "কিলোমিটার", "kg": "কেজি", "g": "গ্রাম", "gm": "গ্রাম",
                  "cm": "সেন্টিমিটার", "mm": "মিলিমিটার", "m": "মিটার",
                  "ml": "মিলিলিটার", "l": "লিটার", "kmph": "কিলোমিটার প্রতি ঘণ্টা",
                  "km/h": "কিলোমিটার প্রতি ঘণ্টা", "hrs": "ঘণ্টা", "hr": "ঘণ্টা",
                  "min": "মিনিট", "mins": "মিনিট", "sec": "সেকেন্ড", "gb": "জিবি",
                  "mb": "এমবি", "°c": "ডিগ্রি সেলসিয়াস"},
    },
    "mr": {
        "rupee": "रुपये", "rupee1": "रुपया", "paise": "पैसे",
        "dollar": "डॉलर", "cent": "सेंट", "percent": "टक्के",
        "point": "पूर्णांक", "plus": "प्लस", "and": "आणि",
        "lakh": "लाख", "crore": "कोटी", "range": "{a} ते {b}",
        "months": "जानेवारी फेब्रुवारी मार्च एप्रिल मे जून जुलै ऑगस्ट सप्टेंबर "
                  "ऑक्टोबर नोव्हेंबर डिसेंबर",
        "day": ("सकाळी", "दुपारी", "संध्याकाळी", "रात्री"),
        "units": {"km": "किलोमीटर", "kg": "किलो", "g": "ग्रॅम", "gm": "ग्रॅम",
                  "cm": "सेंटीमीटर", "mm": "मिलीमीटर", "m": "मीटर",
                  "ml": "मिलीलीटर", "l": "लीटर", "kmph": "किलोमीटर प्रति तास",
                  "km/h": "किलोमीटर प्रति तास", "hrs": "तास", "hr": "तास",
                  "min": "मिनिटे", "mins": "मिनिटे", "sec": "सेकंद", "gb": "जीबी",
                  "mb": "एमबी", "°c": "डिग्री सेल्सिअस"},
    },
}
# Bengali reads a date's day as an ordinal: পয়লা, দোসরা, পনেরোই, একুশে.
_BN_DAY = {1: "পয়লা", 2: "দোসরা", 3: "তেসরা", 4: "চৌঠা"}
# The year in hundreds, as said aloud: উনিশশো / एकोणीसशे / పందొమ్మిది వందల.
_HUNDREDS_YEAR = {"bn": "{c}শো", "mr": "{c}शे", "te": "{c} వందల"}
# "One" before a noun is its own word in Tamil and Telugu: ஒரு ரூபாய், ఒక రూపాయి.
_ONE_BEFORE_NOUN = {"ta": "ஒரு", "te": "ఒక"}
# A noun after a Telugu number takes the oblique: వేలు -> వేల రూపాయలు.
_TE_OBLIQUE = re.compile(r"(వందలు|వేలు|లక్షలు|కోట్లు)$")
_INDIC_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯௦௧௨௩௪௫௬௭௮௯",
                              "0123456789" * 4)


class _IndicLang:
    """The _Lang interface for ta / te / bn / mr."""

    hi = False

    def __init__(self, code: str):
        self.code = code
        self.v = _INDIC[code]
        self.months = self.v["months"].split()

    def int(self, n: int, indian: bool = True) -> str:  # noqa: ARG002 — always Indian
        # The package handles up to 9 digits; beyond that it raises (it
        # iterates an int), which took whole requests down on 7 Nov 2026. A
        # number that long is an ID or account number: read it digit by digit.
        if n >= 10**9:
            return " ".join(self.int(int(d)) for d in str(n))
        words = _indic_num2words(n, lang=self.code).replace("\u200c", "")   # ZWNJ
        if self.code == "mr":
            words = words.replace("\u093c", "")    # Marathi writes हजार, not हज़ार
        elif self.code == "ta":
            words = words.replace("தொண்ணூரெட்டு", "தொண்ணூற்றெட்டு")   # 98, misspelt upstream
        # NFC: the tables spell some vowels decomposed (Telugu ై as ె + U+0C56),
        # which looks the same but is not the text an engine was trained on.
        return unicodedata.normalize("NFC", " ".join(words.split()))

    def digit(self, d: str) -> str:
        return self.int(int(d))

    def _noun(self, words: str) -> str:
        if self.code != "te":
            return words
        return _TE_OBLIQUE.sub(lambda m: m.group(1)[:-2] + "ల", words)

    def money(self, whole: int, paise: int, indian: bool, symbol: str) -> str:  # noqa: ARG002
        v = self.v
        if symbol == "$":
            unit, sub = v["dollar"], v["cent"]
        else:
            unit, sub = (v["rupee1"] if whole == 1 else v["rupee"]), v["paise"]
        amount = _ONE_BEFORE_NOUN.get(self.code) if whole == 1 else None
        out = f"{amount or self._noun(self.int(whole))} {unit}"
        if paise:
            out += f" {self.int(paise)} {sub}"
        return out

    def scaled_money(self, amount: str, scale: str, symbol: str) -> str:
        word = self.v["lakh" if scale.startswith(("lakh", "लाख")) else "crore"]
        return f"{amount} {word} {self.v['dollar'] if symbol == '$' else self.v['rupee']}"

    def percent(self, num: str) -> str:
        return f"{self.decimal(num)} {self.v['percent']}"

    def decimal(self, num: str) -> str:
        num = num.replace(",", "")
        if "." not in num:
            return self.int(int(num))
        whole, frac = num.split(".", 1)
        return (f"{self.int(int(whole or 0))} {self.v['point']} "
                + " ".join(self.digit(d) for d in frac))

    def year(self, n: int) -> str:
        if self.code in _HUNDREDS_YEAR and 1100 <= n <= 1999 and (n // 100) % 10:
            c, rest = divmod(n, 100)
            out = _HUNDREDS_YEAR[self.code].format(c=self.int(c))
            return out + (f" {self.int(rest)}" if rest else "")
        return self.int(n)

    def date(self, d: int, m: int, y: int | None) -> str:
        month = self.months[m - 1]
        year = f" {self.year(y)}" if y else ""
        if self.code == "bn":
            day = _BN_DAY.get(d) or self.int(d) + ("ই" if d <= 18 else "শে")
            return f"{day} {month}" + ("," + year if year else "")
        if self.code == "mr":
            return f"{self.int(d)} {month}{year}"
        return f"{month} {self.int(d)}" + ("," + year if year else "")    # ta, te

    def time(self, h: int, m: int, ampm: str) -> str:
        ampm = ampm.lower().replace(".", "")
        h24 = h + 12 if ampm == "pm" and h < 12 else (0 if ampm == "am" and h == 12 else h)
        part = ""
        if ampm or h > 12:
            morning, noon, evening, night = self.v["day"]
            part = (night if h24 < 4 or h24 >= 20 else morning if h24 < 12
                    else noon if h24 < 16 else evening)
        h12 = h24 % 12 or 12
        nxt = h12 % 12 + 1
        n = self.int
        if self.code == "bn":
            if m == 0:
                spoken = f"{n(h12)}টা"
            elif m == 30:
                spoken = {1: "দেড়টা", 2: "আড়াইটা"}.get(h12, f"সাড়ে {n(h12)}টা")
            elif m == 15:
                spoken = f"সোয়া {n(h12)}টা"
            elif m == 45:
                spoken = f"পৌনে {n(nxt)}টা"
            else:
                spoken = f"{n(h12)}টা বেজে {n(m)} মিনিট"
        elif self.code == "mr":
            if m == 0:
                spoken = n(h12)
            elif m == 30:
                spoken = {1: "दीड", 2: "अडीच"}.get(h12, f"साडे{n(h12)}")
            elif m == 15:
                spoken = f"सव्वा {n(h12)}"
            elif m == 45:
                spoken = f"पावणे {n(nxt)}"
            else:
                spoken = f"{n(h12)} वाजून {n(m)} मिनिटे"
        else:                                          # ta, te: "பத்து முப்பது"
            spoken = n(h12) if m == 0 else f"{n(h12)} {n(m)}"
        return f"\x03{part}\x03{spoken}" if part else spoken

    def time_context(self, out: str, before: str, after: str) -> str:
        """Drop what the customer already wrote around the time: the part of
        day before it ("காலை 10:30"), and in Bengali the টা in "10:30 টায়"."""
        if out.startswith("\x03"):
            _, part, rest = out.split("\x03", 2)
            out = rest if before.rstrip().endswith(part) else f"{part} {rest}"
        if self.code == "bn" and out.endswith("টা") and re.match(r"\s*টা", after):
            out = out[:-2] + "\x04"   # "সাড়ে দশটা" + " টায়" -> "সাড়ে দশটায়"
        return out

    def range(self, a: str, b: str) -> str:
        return self.v["range"].format(a=a, b=b)

    def unit(self, key: str, n_text: str, n_value: float) -> str:  # noqa: ARG002
        return f"{n_text} {self.v['units'][key]}"

    @property
    def plus(self) -> str:
        return self.v["plus"]

    @property
    def and_word(self) -> str:
        return self.v["and"]


# --------------------------------------------------------------------------- #
# Patterns, applied in this order (each consumes what it matches).
# --------------------------------------------------------------------------- #
# A number never ends in a comma: in "₹1,500, then" that comma is a pause.
_NUM = r"\d(?:[\d,]*\d)?(?:\.\d+)?"
# Grouped numbers count as a phone number from 10 digits (an Indian mobile;
# toll-free 1800 numbers have 11), so "2024-2025" stays a range of years.
_PHONE = re.compile(r"(?<![\d.,])\+?\d{2,5}(?:[ -]\d{2,5}){1,4}(?!\d|[.,]\d)|(?<![\d.,])\+?\d{7,}(?!\d|[.,]\d)")
_MONEY = re.compile(
    r"(₹|\bRs\.?|\bINR|\$)\s?(\d(?:[\d,]*\d)?)(?:\.(\d{1,2}))?(?!\d)"
    r"(?:\s?(lakhs?|crores?|लाख|करोड़|कोटी|லட்சம்|கோடி|లక్షల|లక్షలు|లక్ష|కోట్ల|కోట్లు|కోటి|লাখ|কোটি|k)"
    r"(?![A-Za-z\u0900-\u0DFF]))?", re.IGNORECASE)
_LAKH_WORDS = ("lakh", "लाख", "லட்ச", "లక్ష", "লাখ")
_SAYS_RUPEES = re.compile(r"\s*(?:rupee|रुपय|रुपए|ரூபா|రూపా|টাকা)", re.IGNORECASE)
_RUPEE_WORD = re.compile(r"\s(?:rupees?|रुपये|रुपया|ரூபாய்|రూపాయలు|రూపాయి|টাকা)(?=\s|$)")
_MONEY_AFTER = re.compile(r"(?<![\d.])(\d(?:[\d,]*\d)?)(?:\.(\d{1,2}))?\s?(?:/-|₹)")
_PERCENT = re.compile(r"(?<![\d.])(\d(?:[\d,]*\d)?(?:\.\d+)?)\s?%")
_TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)(?:\s?([ap]\.?m\.?)(?![a-z]))?", re.IGNORECASE)
_DATE = re.compile(r"(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?!\d|[/.-]\d)")
_DAY_MONTH_EN = re.compile(
    r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_EN_MONTHS) + r"|"
    + "|".join(m[:3] for m in _EN_MONTHS) + r")\b(?:(?<=\b[A-Za-z]{3})\.)?", re.IGNORECASE)
_MONTH_DAY_EN = re.compile(
    r"\b(" + "|".join(_EN_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?!\d)(?!:)", re.IGNORECASE)
_CODE = re.compile(
    r"((?:\b(?:OTP|PIN|code|CVV|ओटीपी|पिन|कोड)\b)(?:\s*(?:is|was|है|बा|:|-))?\s*)(\d{3,8})(?!\d)",
    re.IGNORECASE)
_ORDINAL_EN = re.compile(r"(?<!\d)(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
_RANGE = re.compile(r"(?<![\d.,/])(\d{1,4})\s?[-–]\s?(\d{1,4})(?!\d|[.,/]\d)")
_UNIT = re.compile(
    r"(?<![\d.])(" + _NUM + r")\s?(" + "|".join(
        re.escape(u) for u in sorted(_UNITS, key=len, reverse=True)) + r")(?![A-Za-z])",
    re.IGNORECASE)
_YEAR = re.compile(r"(?<![\d.,])(1[1-9]\d\d|20\d\d)(?!\d|[.,]\d)")
_PLAIN = re.compile(r"(?<![\d.])(" + _NUM + r")(?![\d])")
_ACRONYM = re.compile(r"\b[A-Z]{2,6}\b")
_TITLE = re.compile(r"(?i)\b(dr|mr|mrs|ms|prof|st)\.(?=\s)")
_AMP = re.compile(r"\s&\s")
_INDIAN_GROUPING = re.compile(r"^\d{1,2}(,\d\d)+,\d{3}$")


def _parse_int(s: str) -> int:
    return int(s.replace(",", "") or 0)


def expand(text: str, lang: str) -> str:
    """See _expand. Reading numbers aloud must never fail a request: if it
    raises, the text goes to the voice as written."""
    try:
        return _expand(text, lang)
    except Exception as e:  # noqa: BLE001
        print(f"[voxforge] speech_text.expand({lang!r}) failed, text left as written: {e!r}")
        return text


def _expand(text: str, lang: str) -> str:
    """Rewrite numbers, money, dates, times, units and (for Hindi) acronyms
    into words for `lang` ("hi", "bho", "en", "ta", "te", "bn" or "mr").
    Other languages pass through."""
    lang = (lang or "").lower().split("-")[0]
    if not text:
        return text
    if lang in _INDIC and _indic_num2words is not None:
        L = _IndicLang(lang)
        text = text.translate(_INDIC_DIGITS)      # ১৫ / १५ / ౧౫ / ௧௫ -> 15
    elif lang in ("hi", "bho", "en"):
        L = _Lang(lang)
    else:
        return text

    def phone(m: re.Match) -> str:
        s = m.group(0)
        digits = re.sub(r"\D", "", s)
        # A short spaced pair like "15 20" is two numbers, not a phone number.
        if len(digits) < 10 and not re.fullmatch(r"\+?\d{7,}", s):
            return s
        groups = re.findall(r"\+|\d+", s)
        spoken = []
        for g in groups:
            if g == "+":
                spoken.append(L.plus)
            else:
                spoken.append(" ".join(L.digit(d) for d in g))
        return ", ".join(spoken).replace(f"{L.plus},", L.plus)

    def code(m: re.Match) -> str:
        return m.group(1) + "\x01" + " ".join(L.digit(d) for d in m.group(2)) + "\x02"

    def money(m: re.Match) -> str:
        sym, whole, paise, scale = m.group(1), m.group(2), m.group(3), m.group(4)
        sym = "$" if sym == "$" else "₹"
        if scale:
            s = scale.lower()
            if s in ("k",):
                n = _parse_int(whole) * 1000
                return L.money(n, 0, True, sym)
            amount = L.decimal(whole + (f".{paise}" if paise else ""))
            lakh = s.startswith(_LAKH_WORDS)
            return L.scaled_money(amount, "lakh" if lakh else "crore", sym)
        p = int((paise or "0").ljust(2, "0")) if paise else 0
        indian = sym == "₹" or bool(_INDIAN_GROUPING.match(whole))
        return L.money(_parse_int(whole), p, indian, sym)

    def once(fn):
        """"₹500 रुपये" / "₹5 lakh টাকার": the customer already says the
        currency, so the amount is read as a bare number."""
        def run(m: re.Match) -> str:
            out = fn(m)
            if m.group(1) != "$" and not m.group(3) and _SAYS_RUPEES.match(m.string, m.end()):
                out = _RUPEE_WORD.sub("", out).rstrip()
            return out
        return run

    money = once(money)

    def money_after(m: re.Match) -> str:
        p = int((m.group(2) or "0").ljust(2, "0")) if m.group(2) else 0
        return L.money(_parse_int(m.group(1)), p, True, "₹")

    def time(m: re.Match) -> str:
        h, mi, ampm = int(m.group(1)), int(m.group(2)), m.group(3) or ""
        # "3.5" is a decimal, not a time: a dotted time needs am/pm or 2 digits
        if m.group(0)[len(m.group(1))] == "." and not ampm:
            return m.group(0)
        return L.time_context(L.time(h, mi, ampm), m.string[:m.start()], m.string[m.end():])

    def date(m: re.Match) -> str:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            return m.group(0)
        yr = int(y) + (2000 if len(y) == 2 else 0)
        return L.date(d, mo, yr)

    def day_month(m: re.Match) -> str:
        d = int(m.group(1))
        if not 1 <= d <= 31:
            return m.group(0)
        name = m.group(2)[:3].lower()
        mo = next(i for i, x in enumerate(_EN_MONTHS) if x[:3].lower() == name) + 1
        return L.date(d, mo, None)

    def month_day(m: re.Match) -> str:
        d = int(m.group(2))
        if not 1 <= d <= 31:
            return m.group(0)
        return f"{m.group(1)} {_en_ordinal(d)}"

    def rng(m: re.Match) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        if b <= a:
            return m.group(0)
        return L.range(L.int(a), L.int(b))

    def unit(m: re.Match) -> str:
        num, key = m.group(1), m.group(2).lower()
        if key == "m" and m.group(2) == "M":   # "5M" is five million, not metres
            return m.group(0)
        value = float(num.replace(",", ""))
        return L.unit(key, L.decimal(num), value)

    def year(m: re.Match) -> str:
        return L.year(int(m.group(1)))

    def plain(m: re.Match) -> str:
        s = m.group(1)
        if "." in s:
            return L.decimal(s)
        return L.int(_parse_int(s), indian=bool(_INDIAN_GROUPING.match(s)) or L.hi)

    def ordinal(m: re.Match) -> str:
        return _en_ordinal(int(m.group(1)))

    def title(m: re.Match) -> str:
        hi, en = _TITLES[m.group(0).lower()]
        return hi if L.hi else (en if lang == "en" else m.group(0))

    def acronym(m: re.Match) -> str:
        w = m.group(0)
        if w in _ACRONYM_WORDS_HI:
            return _ACRONYM_WORDS_HI[w]
        return " ".join(_LETTERS_HI[c] for c in w)

    # Every rewrite is fenced with \x01..\x02 so that the Bhojpuri fix below
    # touches only what this function generated.
    def fenced(fn):
        def run(m: re.Match) -> str:
            out = fn(m)
            return out if out == m.group(0) else f"\x01{out}\x02"
        return run

    (phone, money, money_after, time, date, day_month, month_day, rng, unit,
     year, plain, ordinal) = map(fenced, (
        phone, money, money_after, time, date, day_month, month_day, rng, unit,
        year, plain, ordinal))

    t = text
    t = _CODE.sub(code, t)
    t = _MONEY.sub(money, t)
    t = _PHONE.sub(phone, t)
    t = _MONEY_AFTER.sub(money_after, t)
    t = _PERCENT.sub(fenced(lambda m: L.percent(m.group(1))), t)
    t = _DATE.sub(date, t)
    t = _TIME.sub(time, t)
    if lang == "en":
        t = _DAY_MONTH_EN.sub(day_month, t)
        t = _MONTH_DAY_EN.sub(month_day, t)
        t = _ORDINAL_EN.sub(ordinal, t)
    t = _UNIT.sub(unit, t)
    t = _RANGE.sub(rng, t)
    t = _YEAR.sub(year, t)
    t = _PLAIN.sub(plain, t)
    t = _TITLE.sub(title, t)
    if L.hi:
        # A time already says बजे and सुबह/शाम; when the customer wrote them
        # too ("सुबह 10:30 बजे"), keep one, or every voice says "बजे बजे".
        t = _TIME_BAJE.sub("\x02", t)
        t = _TIME_PART.sub(lambda m: "\x01" + m.group(1), t)
        t = _AMP.sub(" और ", t)
        t = _ACRONYM.sub(acronym, t)
        if lang == "bho":
            # Bhojpuri says दू for two. Only inside generated numbers: the
            # Hindi verb दो ("give") in the customer's own text stays.
            t = _FENCED.sub(lambda m: _BHO_TWO.sub("दू", m.group(0)), t)
    else:
        t = _AMP.sub(f" {L.and_word} ", t)
        # "সাড়ে দশ" + " টায়" (time_context marked it) -> "সাড়ে দশটায়"
        t = re.sub("\x04\x02\\s*", "\x02", t)
    t = t.replace("\x01", "").replace("\x02", "")
    t = re.sub(r"(?<=[ap]\.m\.)\.", "", t)       # "at 7 p.m.." -> "at 7 p.m."
    return re.sub(r"[ \t]{2,}", " ", t)


_FENCED = re.compile(r"\x01[^\x02]*\x02")
_TIME_BAJE = re.compile(r"(?:(?<=बजे)|(?<=मिनट))\x02\s*बजे(?![ऀ-ॿ])")
_TIME_PART = re.compile(r"(सुबह|दोपहर|शाम|रात)\s+\x01\1(?=\s)")
_BHO_TWO = re.compile(r"(?<![ऀ-ॿ])दो(?![ऀ-ॿ])")
