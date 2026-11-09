"""Best-effort Hinglish helper (no external deps).

Free-form romanized Hindi -> Devanagari is genuinely hard; a full neural model
(IndicXlit) won't install cleanly here (fairseq). So this uses a curated
dictionary of the most common romanized Hindi words — the function words,
pronouns and verbs that make Hinglish sound "foreign" when a Hindi voice reads
them in Latin script. Known words are converted to Devanagari so the Hindi model
pronounces them natively; unknown words (often English) are left as-is, which a
Hindi voice renders with a natural Indian accent.

Only applied for Hindi voices, and only when the text actually contains
romanized (Latin) content.
"""

from __future__ import annotations

import re
import unicodedata

# Common romanized Hindi -> Devanagari. Lowercased keys.
_DICT: dict[str, str] = {
    # pronouns
    "main": "मैं", "mai": "मैं", "mein": "में", "hum": "हम", "tum": "तुम",
    "tu": "तू", "aap": "आप", "ye": "ये", "yeh": "यह", "wo": "वो", "woh": "वह",
    "vo": "वो", "iska": "इसका", "uska": "उसका", "mera": "मेरा", "meri": "मेरी",
    "mere": "मेरे", "tera": "तेरा", "teri": "तेरी", "tere": "तेरे",
    "tumhara": "तुम्हारा", "tumhari": "तुम्हारी", "hamara": "हमारा",
    "hamari": "हमारी", "apna": "अपना", "apni": "अपनी", "iske": "इसके",
    "unka": "उनका", "inka": "इनका",
    # to-be / common verbs
    "hai": "है", "hain": "हैं", "ho": "हो", "hoon": "हूँ", "hu": "हूँ",
    "hun": "हूँ", "tha": "था", "thi": "थी", "the": "थे", "hoga": "होगा",
    "hogi": "होगी", "honge": "होंगे", "raha": "रहा", "rahi": "रही",
    "rahe": "रहे", "kar": "कर", "karo": "करो", "karna": "करना",
    "karta": "करता", "karti": "करती", "karte": "करते", "kiya": "किया",
    "karenge": "करेंगे", "karunga": "करूँगा", "ja": "जा", "jao": "जाओ",
    "jana": "जाना", "jaa": "जा", "gaya": "गया", "gayi": "गई", "gaye": "गए",
    "aa": "आ", "aao": "आओ", "aana": "आना", "aaya": "आया", "aayi": "आई",
    "le": "ले", "lo": "लो", "lena": "लेना", "liya": "लिया", "de": "दे",
    "do": "दो", "dena": "देना", "diya": "दिया", "dekh": "देख",
    "dekho": "देखो", "dekha": "देखा", "bol": "बोल", "bolo": "बोलो",
    "bola": "बोला", "sun": "सुन", "suno": "सुनो", "kha": "खा",
    "khao": "खाओ", "pi": "पी", "chal": "चल", "chalo": "चलो", "mil": "मिल",
    "mila": "मिला", "milega": "मिलेगा", "samajh": "समझ",
    "samjho": "समझो", "pata": "पता", "chahiye": "चाहिए", "sakta": "सकता",
    "sakti": "सकती", "sakte": "सकते", "raha_hoon": "रहा हूँ",
    # particles / connectors
    "aur": "और", "ya": "या", "lekin": "लेकिन", "par": "पर", "magar": "मगर",
    "kyunki": "क्योंकि", "kyun": "क्यों", "kyu": "क्यों", "kya": "क्या",
    "kaise": "कैसे", "kaisa": "कैसा", "kaisi": "कैसी", "kab": "कब",
    "kahan": "कहाँ", "kaun": "कौन", "kitna": "कितना", "kitni": "कितनी",
    "jab": "जब", "tab": "तब", "abhi": "अभी", "ab": "अब", "phir": "फिर",
    "to": "तो", "toh": "तो", "bhi": "भी", "hi": "ही", "na": "ना",
    "nahi": "नहीं", "nahin": "नहीं", "mat": "मत", "haan": "हाँ", "han": "हाँ",
    "ki": "कि", "ke": "के", "ka": "का", "se": "से", "me": "में",
    "ko": "को", "pe": "पे", "tak": "तक", "liye": "लिए", "saath": "साथ",
    "wala": "वाला", "wali": "वाली", "wale": "वाले",
    # common words
    "aaj": "आज", "kal": "कल", "abhi_abhi": "अभी अभी", "bahut": "बहुत",
    "thoda": "थोड़ा", "zyada": "ज़्यादा", "accha": "अच्छा", "acha": "अच्छा",
    "theek": "ठीक", "thik": "ठीक", "sahi": "सही", "galat": "ग़लत",
    "naam": "नाम", "kaam": "काम", "ghar": "घर", "din": "दिन", "raat": "रात",
    "samay": "समय", "waqt": "वक़्त", "baat": "बात", "baatein": "बातें",
    "log": "लोग", "logon": "लोगों", "dost": "दोस्त", "pyaar": "प्यार",
    "pyar": "प्यार", "dil": "दिल", "zindagi": "ज़िंदगी", "duniya": "दुनिया",
    "khush": "ख़ुश", "khushi": "ख़ुशी", "dukh": "दुख", "umeed": "उम्मीद",
    "shukriya": "शुक्रिया", "dhanyavaad": "धन्यवाद", "namaste": "नमस्ते",
    "bhai": "भाई", "behen": "बहन", "maa": "माँ", "papa": "पापा",
    "beta": "बेटा", "beti": "बेटी", "paani": "पानी", "khana": "खाना",
    "school": "स्कूल", "sab": "सब", "sabhi": "सभी", "kuch": "कुछ",
    "kuchh": "कुछ", "sirf": "सिर्फ़", "bas": "बस", "ek": "एक", "do_": "दो",
    "teen": "तीन", "char": "चार", "paanch": "पाँच", "bahar": "बाहर",
    "andar": "अंदर", "upar": "ऊपर", "neeche": "नीचे", "aage": "आगे",
    "peeche": "पीछे", "yahan": "यहाँ", "wahan": "वहाँ", "idhar": "इधर",
    "udhar": "उधर", "matlab": "मतलब", "waise": "वैसे", "jaise": "जैसे",
    # song / romance vocabulary (common in lyrics)
    "tujhe": "तुझे", "mujhe": "मुझे", "tujhko": "तुझको", "mujhko": "मुझको",
    "tujhse": "तुझसे", "mujhse": "मुझसे", "chahta": "चाहता",
    "chahti": "चाहती", "chahte": "चाहते", "chahat": "चाहत", "chahoon": "चाहूँ",
    "ishq": "इश्क़", "mohabbat": "मोहब्बत", "muhabbat": "मोहब्बत",
    "sapna": "सपना", "sapne": "सपने", "sapno": "सपनों", "khwab": "ख़्वाब",
    "khwaab": "ख़्वाब", "aankh": "आँख", "aankhen": "आँखें", "aankhon": "आँखों",
    "neend": "नींद", "saans": "साँस", "saansein": "साँसें", "judaa": "जुदा",
    "judai": "जुदाई", "intezaar": "इंतज़ार", "intzaar": "इंतज़ार",
    "yaad": "याद", "yaadein": "यादें", "yaadon": "यादों", "tanha": "तन्हा",
    "tanhai": "तन्हाई", "aansoo": "आँसू", "aansu": "आँसू", "manzil": "मंज़िल",
    "raah": "राह", "raahein": "राहें", "safar": "सफ़र", "chand": "चाँद",
    "chaand": "चाँद", "sitaare": "सितारे", "sitare": "सितारे",
    "aasmaan": "आसमान", "asmaan": "आसमान", "baarish": "बारिश",
    "mausam": "मौसम", "hawa": "हवा", "hawaa": "हवा", "subah": "सुबह",
    "sham": "शाम", "shaam": "शाम", "roshni": "रोशनी", "andhera": "अँधेरा",
    "khamoshi": "ख़ामोशी", "awaaz": "आवाज़", "aawaz": "आवाज़",
    "geet": "गीत", "dhun": "धुन", "jaan": "जान", "jaanu": "जानू",
    "jaana": "जाना", "sanam": "सनम", "mahiya": "माहिया", "dhadkan": "धड़कन",
    "armaan": "अरमान", "arman": "अरमान", "junoon": "जुनून",
    "deewana": "दीवाना", "deewani": "दीवानी", "diwana": "दीवाना",
    "bekarar": "बेक़रार", "beqarar": "बेक़रार", "karib": "क़रीब",
    "kareeb": "क़रीब", "door": "दूर", "paas": "पास", "hamesha": "हमेशा",
    "kabhi": "कभी", "lamha": "लम्हा", "lamhe": "लम्हे", "pal": "पल",
    "khud": "ख़ुद", "rooh": "रूह", "ehsaas": "एहसास", "ehsas": "एहसास",
    "sukoon": "सुकून", "bechain": "बेचैन", "dard": "दर्द", "gham": "ग़म",
    "khushboo": "ख़ुशबू", "khushbu": "ख़ुशबू", "rang": "रंग", "rangeen": "रंगीन",
    "noor": "नूर", "qismat": "क़िस्मत", "kismat": "क़िस्मत", "naseeb": "नसीब",
    "waada": "वादा", "vaada": "वादा", "kasam": "क़सम", "jahan": "जहान",
    "jahaan": "जहान", "fasaana": "फ़साना", "kahani": "कहानी",
    "kahaani": "कहानी", "milan": "मिलन", "vishwaas": "विश्वास",
    "bina": "बिना", "bin": "बिन", "sang": "संग", "milke": "मिलके",
    "kahin": "कहीं", "kaheen": "कहीं", "sada": "सदा", "har": "हर",
    "dil_se": "दिल से", "saath_saath": "साथ साथ",
}

# Every Hindi voice we serve, across all engines. Missing one here means
# that voice silently receives un-converted Latin text.
_HINDI_VOICE = re.compile(
    r"^(hf_|hm_|parler-hi|parler-bho|chatterbox-hi|hi_IN-|mms-hin|svara-hi|svara-bho|if5-)")
_HAS_LATIN = re.compile(r"[A-Za-z]")
_TOKEN = re.compile(r"[A-Za-z]+|[^A-Za-z]+")



# --- English words that appear constantly in Hinglish speech ------------- #
# Spelled the way a Hindi speaker says them, not letter-by-letter: a
# Devanagari-only model reads these, whereas Latin text it cannot read at all.
_ENGLISH_LOANS: dict[str, str] = {
    "weather": "वेदर", "office": "ऑफ़िस", "meeting": "मीटिंग", "product": "प्रोडक्ट",
    "useful": "यूज़फ़ुल", "computer": "कंप्यूटर", "mobile": "मोबाइल", "phone": "फ़ोन",
    "internet": "इंटरनेट", "online": "ऑनलाइन", "email": "ईमेल", "message": "मैसेज",
    "video": "वीडियो", "audio": "ऑडियो", "photo": "फ़ोटो", "camera": "कैमरा",
    "school": "स्कूल", "college": "कॉलेज", "student": "स्टूडेंट", "teacher": "टीचर",
    "doctor": "डॉक्टर", "hospital": "हॉस्पिटल", "market": "मार्केट", "shop": "शॉप",
    "bank": "बैंक", "money": "मनी", "price": "प्राइस", "order": "ऑर्डर",
    "customer": "कस्टमर", "service": "सर्विस", "company": "कंपनी", "business": "बिज़नेस",
    "team": "टीम", "project": "प्रोजेक्ट", "report": "रिपोर्ट", "update": "अपडेट",
    "time": "टाइम", "date": "डेट", "today": "टुडे", "tomorrow": "टुमॉरो",
    "morning": "मॉर्निंग", "evening": "ईवनिंग", "night": "नाइट", "week": "वीक",
    "month": "मंथ", "year": "ईयर", "train": "ट्रेन", "bus": "बस", "car": "कार",
    "ticket": "टिकट", "station": "स्टेशन", "airport": "एयरपोर्ट", "hotel": "होटल",
    "food": "फ़ूड", "water": "वॉटर", "tea": "चाय", "coffee": "कॉफ़ी",
    "friend": "फ़्रेंड", "family": "फ़ैमिली", "home": "होम", "house": "हाउस",
    "work": "वर्क", "job": "जॉब", "salary": "सैलरी", "boss": "बॉस",
    "please": "प्लीज़", "sorry": "सॉरी", "thanks": "थैंक्स", "welcome": "वेलकम",
    "good": "गुड", "best": "बेस्ट", "nice": "नाइस", "great": "ग्रेट",
    "problem": "प्रॉब्लम", "solution": "सलूशन", "help": "हेल्प", "support": "सपोर्ट",
    "call": "कॉल", "book": "बुक", "class": "क्लास", "exam": "एग्ज़ाम",
    "result": "रिज़ल्ट", "office's": "ऑफ़िस का", "app": "ऐप", "website": "वेबसाइट",
    "link": "लिंक", "file": "फ़ाइल", "download": "डाउनलोड", "upload": "अपलोड",
    "account": "अकाउंट", "password": "पासवर्ड", "login": "लॉगिन", "screen": "स्क्रीन",
    "voice": "वॉइस", "sound": "साउंड", "music": "म्यूज़िक", "song": "सॉन्ग",
    "news": "न्यूज़", "story": "स्टोरी", "party": "पार्टी", "holiday": "हॉलिडे",
    "easy": "ईज़ी", "simple": "सिंपल", "ready": "रेडी", "start": "स्टार्ट",
    "stop": "स्टॉप", "open": "ओपन", "close": "क्लोज़", "share": "शेयर",
    "send": "सेंड", "receive": "रिसीव", "check": "चेक", "select": "सेलेक्ट",
}

# Romanized Hindi that the main dictionary was missing, so it fell through to
# the rough phonetic fallback and came out mangled.
_EXTRA_HINDI = {
    "aapse": "आपसे", "aapko": "आपको", "aapka": "आपका", "aapki": "आपकी",
    "karke": "करके", "karte": "करते", "karta": "करता", "karti": "करती",
    "kiya": "किया", "kiye": "किए", "raha": "रहा", "rahi": "रही", "rahe": "रहे",
    "hoon": "हूँ", "hain": "हैं", "tha": "था", "thi": "थी", "the": "थे",
    "bahut": "बहुत", "accha": "अच्छा", "acchi": "अच्छी", "khush": "ख़ुश",
    "dhanyavaad": "धन्यवाद", "shukriya": "शुक्रिया", "namaste": "नमस्ते",
}

# Longest first, so "tion" wins over "ti" and "sh" over "s".
_TRANSLIT = [
    ("tion", "शन"), ("sion", "ेशन"), ("ough", "ओ"), ("ing", "िंग"), ("ck", "क"),
    ("sh", "श"), ("ch", "च"), ("th", "थ"), ("ph", "फ़"), ("gh", "ग"), ("wh", "व"),
    ("kh", "ख"), ("aa", "ा"), ("ii", "ी"), ("uu", "ू"), ("ee", "ी"), ("ea", "ी"), ("oo", "ू"), ("ou", "ाउ"), ("ai", "ै"),
    ("ay", "े"), ("ey", "े"), ("au", "ॉ"), ("aw", "ॉ"), ("oa", "ो"), ("oi", "ॉय"),
    # \x00 marks "this consonant already has its vowel — do not join it to
    # the one before". Stripped again at the end.
    ("ar", "ा\x00र"), ("er", "\x00र"), ("ir", "ि\x00र"),
    ("or", "ॉ\x00र"), ("ur", "ु\x00र"),
    ("a", "ा"), ("b", "ब"), ("c", "क"), ("d", "ड"), ("e", "े"), ("f", "फ़"),
    ("g", "ग"), ("h", "ह"), ("i", "ि"), ("j", "ज"), ("k", "क"), ("l", "ल"),
    ("m", "म"), ("n", "न"), ("o", "ो"), ("p", "प"), ("q", "क"), ("r", "र"),
    ("s", "स"), ("t", "ट"), ("u", "ु"), ("v", "व"), ("w", "व"), ("x", "क्स"),
    ("y", "य"), ("z", "ज़"),
]


# Devanagari consonants carry an inherent "a" sound. Two in a row must be
# joined with a halant or every cluster gains a vowel that is not there.
# Note: the nukta (U+093C) is NOT listed — it modifies the consonant
# before it, and treating it as a consonant inserts a halant inside
# letters like फ़, which breaks them.
_CONSONANTS = set("कखगघचछजझटठडढणतथदधनपफबभमयरलवशषसह")
_NUKTA = "\u093c"
_MATRAS = set("ािीुूृेैोौंँ्")
_NO_JOIN = "\x00"   # marker: leave the next character unjoined


# vowel sign -> the independent letter used at the start of a word
_LEADING_VOWEL = {
    "ा": "आ", "ि": "इ", "ी": "ई", "ु": "उ", "ू": "ऊ",
    "े": "ए", "ै": "ऐ", "ो": "ओ", "ौ": "औ",
}


def _translit_latin(word: str) -> str:
    """Approximate Devanagari for an unknown Latin word.

    Deliberately rough: the aim is that the voice says something close, rather
    than skipping the word or reading it as noise, which is what a
    Devanagari-only model does with Latin script today.
    """
    w = word.lower()
    out, i = [], 0
    while i < len(w):
        for src, dst in _TRANSLIT:
            if w.startswith(src, i):
                out.append(dst)
                i += len(src)
                break
        else:
            i += 1
    text = "".join(out)

    # Join consonant clusters: "प" + "र" reads pa-ra, "प्र" reads pra.
    joined = []
    for i, ch in enumerate(text):
        if ch == _NO_JOIN:
            continue
        joined.append(ch)
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if ch in _CONSONANTS and nxt in _CONSONANTS and nxt != _NUKTA:
            joined.append("्")
    text = "".join(joined).replace(_NO_JOIN, "")

    # A word-final "i" is long in Hindi and Bhojpuri (bani, taxi, ji), and
    # a short one there sounds clipped.
    if len(text) > 1 and text[-1] == "ि":
        text = text[:-1] + "ी"

    # A final "e" is usually silent (time, phone); drop it. A final "a" is
    # said, in English and in romanized Hindi alike (data, camera, pooja).
    if len(text) > 2 and text[-1] == "े" and text[-2] in _CONSONANTS:
        text = text[:-1]

    # A word cannot START with a vowel sign; promote it to the independent
    # vowel letter, or the first sound is lost entirely.
    if text and text[0] in _LEADING_VOWEL:
        text = _LEADING_VOWEL[text[0]] + text[1:]
    return text or word


def is_hindi_voice(voice_id: str) -> bool:
    vid = (voice_id or "").replace("server:", "")
    return bool(_HINDI_VOICE.match(vid))


def to_devanagari(text: str, speak_english: bool = False) -> str:
    """Replace romanized Hindi with Devanagari.

    With `speak_english`, Latin words that are NOT romanized Hindi are also
    converted — from the loanword list where we have one, phonetically
    otherwise. Use it for engines that can only read Devanagari, where leaving
    Latin behind means the word is garbled or dropped entirely.
    """
    if not _HAS_LATIN.search(text):
        return text

    def repl(tok: str) -> str:
        if not tok[0].isalpha():
            return tok
        low = tok.lower()
        hit = _DICT.get(low) or _EXTRA_HINDI.get(low)
        if hit:
            return hit
        if speak_english:
            return _ENGLISH_LOANS.get(low) or _translit_latin(tok)
        return tok

    return "".join(repl(t) for t in _TOKEN.findall(text))


# --------------------------------------------------------------------------- #
# Bengali
# --------------------------------------------------------------------------- #
# A Latin word left inside Bengali text does real damage: MMS drops it silently
# (its tokenizer discards anything outside its own script, so "office" simply
# vanishes), and svara sometimes derails into another language entirely — one
# measured run of a Bengali sentence containing "office" and "Thank you" came
# back as Sinhala gibberish. Converting the word to Bengali script first avoids
# all of that, exactly as it does for Hindi.
#
# Devanagari and Bengali are the same Brahmic structure and Unicode lays the two
# blocks out in the same order, so the transliteration above is reused wholesale
# and its output mapped across. Of the 57 characters it can emit, 54 differ only
# by the 0x80 between the blocks. These are the three that do not:
_DEV_TO_BENGALI = {
    "\u0911": "\u0985",   # candra O -> অ, Bengali has none (ऑफ़िस -> অফিস)
    "\u0935": "\u09ad",   # va -> ভ: Bengali has no va, and ব would read as b
    "\u0949": "",          # candra O sign has no equivalent (कॉल -> কল)
    "\u093c": "",          # nukta: Bengali writes these loanwords without it
}


# Only letters and vowel signs shift between the blocks. Punctuation does not:
# the danda U+0964 is shared by both scripts, and +0x80 would silently turn it
# into a Bengali currency numerator.
_DEV_LETTERS = frozenset(
    "\u0901\u0902\u0905\u0906\u0907\u0908\u0909\u090a\u090f\u0910\u0913\u0914"
    "\u0915\u0916\u0917\u0918\u0919\u091a\u091b\u091c\u091d\u091e"
    "\u091f\u0920\u0921\u0922\u0923\u0924\u0925\u0926\u0927\u0928"
    "\u092a\u092b\u092c\u092d\u092e\u092f\u0930\u0932\u0936\u0937\u0938\u0939"
    "\u093e\u093f\u0940\u0941\u0942\u0943\u0947\u0948\u094b\u094c\u094d"
)


def _dev_to_bengali(s: str) -> str:
    out = []
    for ch in s:
        if ch in _DEV_TO_BENGALI:
            out.append(_DEV_TO_BENGALI[ch])
        elif ch in _DEV_LETTERS:
            out.append(chr(ord(ch) + 0x80))
        else:
            out.append(ch)   # Bengali, punctuation and spacing pass through
    return "".join(out)


# Every Bengali voice we serve. Missing one means that voice still receives
# raw Latin text.
_BENGALI_VOICE = re.compile(r"^(mms-ben|svara-bn|parler-bn|if5-bn|bn_)")


def is_bengali_voice(voice_id: str) -> bool:
    v = (voice_id or "").lower().replace("server:", "")
    return bool(_BENGALI_VOICE.match(v))


def to_bengali(text: str, speak_english: bool = False) -> str:
    """Bengali text with any Latin words rewritten in Bengali script.

    Bengali already in the text is left exactly as it is: the converter only
    rewrites runs of Latin letters.
    """
    return _dev_to_bengali(to_devanagari(text, speak_english))


# --------------------------------------------------------------------------- #
# Telugu, Tamil, Marathi
# --------------------------------------------------------------------------- #
# The same fault as Bengali. Measured 6 Nov 2026 with a Telugu recogniser:
# svara read "దయచేసి మీ email చూడండి, తర్వాత office కి call చేయండి" 19-27%
# wrong against 2-10% with the English words in Telugu script, and MMS drops
# any Latin word outright (its tokenizer discards it).
#
# Words come from the English list above, never from the romanized-Hindi one:
# a Tamil or Telugu writer's "main road" is English, not मैं. Acronyms are
# spelt out (OTP -> ओ टी पी) instead of read as a word.
#
# Telugu and Tamil keep the inherent vowel at the end of a word where Hindi
# drops it, so "ऑफ़िस" mapped letter by letter would read "aaphisa"; a
# converted word that ends in a bare consonant gets the virama it needs.

def _acronym_devanagari(tok: str) -> str | None:
    from speech_text import _ACRONYM_WORDS_HI, _LETTERS_HI   # no cycle: it imports nothing of ours
    if tok.isupper() and 2 <= len(tok) <= 6:
        return _ACRONYM_WORDS_HI.get(tok) or " ".join(_LETTERS_HI[c] for c in tok)
    return None


# Telugu sits 0x300 above Devanagari, letter for letter, for everything the
# converter emits except these.
_DEV_TO_TELUGU = {
    "\u0911": "\u0c06",   # candra O (ऑ) -> ఆ: ఆఫీస్, as Telugu writes office
    "\u0949": "\u0c3e",   # its vowel sign (ॉ) -> ా: కాల్
    "\u0945": "\u0c46",   # candra E sign -> ె
    "\u0935": "\u0c35",   # va (Bengali has none, so it is not in _DEV_LETTERS)
    "\u093c": "",          # nukta: ఫ already serves for f, జ for z
}
_TE_CONSONANTS = frozenset(chr(c) for c in range(0x0C15, 0x0C3A))

# Tamil has one letter for each of क/ख/ग/घ, च/छ, ट/ठ/ड/ढ, त/थ/द/ध and प/फ/ब/भ;
# the reader voices them from context, as it does for native words.
_DEV_TO_TAMIL = {
    "अ": "அ", "आ": "ஆ", "इ": "இ", "ई": "ஈ", "उ": "உ", "ऊ": "ஊ", "ऋ": "ரு",
    "ए": "ஏ", "ओ": "ஓ", "औ": "ஔ", "ऑ": "ஆ",
    "क": "க", "ख": "க", "ग": "க", "घ": "க", "ङ": "ங",
    "च": "ச", "छ": "ச", "ज": "ஜ", "झ": "ஜ", "ञ": "ஞ",
    "ट": "ட", "ठ": "ட", "ड": "ட", "ढ": "ட", "ण": "ண",
    "त": "த", "थ": "த", "द": "த", "ध": "த", "न": "ன",
    "प": "ப", "फ": "ஃப", "ब": "ப", "भ": "ப", "म": "ம",
    "य": "ய", "र": "ர", "ल": "ல", "ळ": "ள", "व": "வ",
    "श": "ஷ", "ष": "ஷ", "स": "ஸ", "ह": "ஹ",
    "ा": "ா", "ि": "ி", "ी": "ீ", "ु": "ு", "ू": "ூ", "ृ": "ு",
    "े": "ே", "ो": "ோ", "ौ": "ௌ", "ॉ": "ா", "ॅ": "ெ",
    "्": "்", "़": "", "ः": "",
}
_TA_CONSONANTS = frozenset("கஙசஜஞடணதநனபமயரலளழவஷஸஹ")
# Anusvara takes the nasal of the consonant after it (பேங்க், டீம்), and a word
# opens with ந, not ன.
_TA_NASAL = {"க": "ங்", "ச": "ஞ்", "ஜ": "ஞ்", "ட": "ண்", "த": "ந்", "ப": "ம்", "ம": "ம்"}

# In the Hindi spellings of English words, ै is the vowel of "bank", and ाइ /
# ाउ are the diphthongs of "online" / "account". Telugu, Tamil and Bengali
# each write those differently (బ్యాంక్, பேங்க், ব্যাংক), so they travel as the
# markers english_lexicon uses and each script fills them in.
_DIPHTHONGS = (("आई", "\ue003\ue000"), ("आइ", "\ue003\ue000"), ("आउ", "\ue005\ue000"),
               ("ऐ", "\ue001\ue000"), ("ाइ", "\ue003"), ("ाउ", "\ue005"), ("ै", "\ue001"))
_VOICELESS_STOPS = frozenset("कचटतप")
_MARKERS = frozenset("\ue001\ue003\ue005\ue007")
_DEV_VOWEL_SIGNS = frozenset("ािीुूृेैोौॉॅ")
_DEV_VOWELS = frozenset("अआइईउऊऋएऐओऔऑ")


def _hindi_schwa_deletion(word: str) -> str:
    """Write in the vowels Hindi leaves unsaid (ऑनलाइन -> ऑन्लाइन, पासवर्ड ->
    पास्वर्ड), for scripts that say every written vowel. The usual rule: going
    right to left, a consonant's inherent vowel is silent when a vowel comes
    before it and a consonant with a vowel after it, never in the first
    syllable; the final one is silent too (the caller adds that virama)."""
    # aksharas: [text, has_inherent_vowel, has_a_vowel]
    ak: list[list] = []
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        if ch in _CONSONANTS:
            j = i + 1
            while j + 1 < n and word[j] == "्" and word[j + 1] in _CONSONANTS:
                j += 2
            if j < n and word[j] == "़":
                j += 1
            if j < n and word[j] in _DEV_VOWEL_SIGNS:
                ak.append([word[i:j + 1], False, True]); j += 1
            elif j < n and word[j] == "्":
                ak.append([word[i:j + 1], False, False]); j += 1
            else:
                ak.append([word[i:j], True, True])
            while j < n and word[j] in "ंँ":
                ak[-1][0] += word[j]; j += 1
            i = j
        else:
            ak.append([ch, False, ch in _DEV_VOWELS]); i += 1
    if ak and ak[-1][1]:
        ak[-1][2] = False                   # the final inherent vowel is silent
    for k in range(len(ak) - 2, 0, -1):
        if ak[k][1] and ak[k - 1][2] and ak[k + 1][2] and ak[k + 1][0][0] in _CONSONANTS \
                and not ak[k][0].endswith(("ं", "ँ")):
            ak[k][0] += "्"; ak[k][1] = ak[k][2] = False
    return "".join(a[0] for a in ak)


def _dev_to_tamil(word: str) -> str:
    # English "-ng" is a nasal alone: मीटिंग -> மீட்டிங், not மீட்டிங்க்.
    word = re.sub("ंग(्?)(?=\\s|$)", "ङ\\1", word)
    out = []
    n = len(word)
    for i, ch in enumerate(word):
        nxt_ch = word[i + 1] if i + 1 < n else ""
        if ch in ("ं", "ँ"):
            nxt = _DEV_TO_TAMIL.get(nxt_ch, "")
            out.append(_TA_NASAL.get(nxt[-1:], "ம்" if not nxt else "ன்"))
        elif ch == "ज" and nxt_ch == "़":
            out.append("ஸ")                        # z: ப்ளீஸ், not ப்லீஜ்
        elif (ch in _VOICELESS_STOPS and i > 0
              and (word[i - 1] in _DEV_VOWEL_SIGNS or word[i - 1] in _DEV_VOWELS
                   or word[i - 1] in _CONSONANTS or word[i - 1] in _MARKERS)
              and nxt_ch and (nxt_ch in _DEV_VOWEL_SIGNS or nxt_ch in _CONSONANTS
                              or nxt_ch in _MARKERS)):
            # A lone Tamil stop between vowels is voiced (ட = d), so English
            # t/k/p there is doubled the way Tamil writes it: மீட்டிங், போட்டோ.
            t = _DEV_TO_TAMIL[ch]
            out.append(t + "்" + t)
        else:
            out.append(_DEV_TO_TAMIL.get(ch, ch))
    s = "".join(out)
    return "ந" + s[1:] if s.startswith("ன") else s


def _dev_to_telugu(word: str) -> str:
    return "".join(_DEV_TO_TELUGU[ch] if ch in _DEV_TO_TELUGU
                   else chr(ord(ch) + 0x300) if ch in _DEV_LETTERS else ch for ch in word)


# Gujarati, Kannada, Malayalam, Gurmukhi and Odia also sit at a fixed distance
# from Devanagari; these are the letters that do not, or that the language
# writes differently in English words.
_OFFSET = {"gujr": 0x180, "knda": 0x380, "mlym": 0x400, "guru": 0x100, "orya": 0x200}
_OFFSET_OVERRIDES = {
    "gujr": {"\u093c": ""},                                  # ફ, ઝ: no nukta
    "knda": {"ऑ": "ಆ", "ॉ": "ಾ", "ॅ": "ೆ", "ँ": "ಂ", "\u093c": ""},   # ಆಫೀಸ್, ಕಾಲ್
    "mlym": {"ऑ": "ഓ", "ॉ": "ോ", "ॅ": "െ", "ौ": "ൗ", "ँ": "ം", "\u093c": ""},  # ഓഫീസ്, കോൾ
    "guru": {"ऑ": "ਆ", "ॉ": "ਾ", "ॅ": "ੈ", "ृ": "੍ਰਿ", "ऋ": "ਰਿ", "ष": "ਸ਼", "ँ": "ਂ"},
    "orya": {"ऑ": "ଅ", "ॉ": "", "ॅ": "େ", "व": "ଭ", "\u093c": ""},   # ଅଫିସ, କଲ: ଅ is already "o"
}
# Malayalam writes a nasal before a stop as that stop's nasal (അക്കൗണ്ട്, not
# the anusvara), and doubles a lone voiceless stop between vowels, which it
# would otherwise voice: ഫോട്ടോ, കമ്പ്യൂട്ടർ, as the language spells them.
_ML_NASAL = {**dict.fromkeys("कखगघ", "ङ"), **dict.fromkeys("चछजझ", "ञ"),
             **dict.fromkeys("टठडढ", "ण"), **dict.fromkeys("तथदध", "न"),
             **dict.fromkeys("पफबभ", "म")}
_ML_CHILLU = {"ന": "ൻ", "ല": "ൽ", "ര": "ർ", "ണ": "ൺ", "ള": "ൾ"}
# English l and n after a back vowel take the retroflex chillu, as Malayalam
# spells them: കോൾ, ഫുട്ബോൾ, ഫോൺ, ടൗൺ; elsewhere മൊബൈൽ, സ്റ്റേഷൻ.
_ML_BACK_VOWEL = frozenset("ോൊൂുാൗഓഒഊഉആഔ")
# Before these the consonant joins the next one instead (ന്റ, ല്ല, ണ്ട).
_ML_NO_CHILLU_BEFORE = {"ന": "നതദറ", "ല": "ല", "ണ": "ണടഡ", "ള": "ള", "ര": ""}


def _offset_script(dev: str, script: str) -> str:
    over, shift = _OFFSET_OVERRIDES[script], _OFFSET[script]
    out = []
    for i, ch in enumerate(dev):
        if ch == "\u093c" and script == "orya" and i and dev[i - 1] in "डढ":
            out.append("\u0b3c")                          # ଡ଼ ଢ଼ are Odia letters
        elif ch in over:
            out.append(over[ch])
        elif "\u0901" <= ch <= "\u094d":
            out.append(chr(ord(ch) + shift))
        else:
            out.append(ch)          # markers, punctuation, the danda
    return "".join(out)


def _ml_prepare(dev: str) -> str:
    dev = re.sub("ंग्?(?=\\s|$)", "ङ्", dev)        # മീട്ടിങ്, not മീട്ടിംഗ്
    # z is സ and th is ത in Malayalam spellings of English: പ്ലീസ്, താങ്ക് യൂ.
    dev = dev.replace("ज\u093c", "स").replace("थ", "त")
    dev = re.sub("[ंँ](?=[" + "".join(_ML_NASAL) + "])",
                 lambda m: _ML_NASAL[dev[m.end()]] + "्", dev)
    out, n = [], len(dev)
    for i, ch in enumerate(dev):
        nxt = dev[i + 1] if i + 1 < n else ""
        prev = dev[i - 1] if i else ""
        if (ch in _VOICELESS_STOPS and prev and nxt
                and (prev in _DEV_VOWEL_SIGNS or prev in _DEV_VOWELS or prev in _CONSONANTS
                     or prev in _MARKERS)
                and (nxt in _DEV_VOWEL_SIGNS or nxt in _CONSONANTS or nxt in _MARKERS)):
            out.append(ch + "्" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _ml_finish(word: str) -> str:
    """Final and pre-consonant n/l/r/ṇ/ḷ as chillu letters (ഓൺലൈൻ, കോൾ,
    സർവീസ്), final m as anusvara (ടീം)."""
    out = []
    n = len(word)
    i = 0
    while i < n:
        ch = word[i]
        if ch in _ML_CHILLU and i + 1 < n and word[i + 1] == "്":
            after = word[i + 2] if i + 2 < n else ""
            if not after or (after.isalpha() and "\u0d15" <= after <= "\u0d39"
                             and after not in _ML_NO_CHILLU_BEFORE[ch]):
                back = i and word[i - 1] in _ML_BACK_VOWEL
                if ch == "ല" and back:
                    ch = "ള"
                elif ch == "ന" and back and after in ("", "ല"):
                    ch = "ണ"                                 # ഫോൺ, ഓൺലൈൻ
                out.append(_ML_CHILLU[ch]); i += 2; continue
        if ch == "മ" and word[i + 1:i + 2] == "്" and i + 2 == n:
            out.append("ം"); i += 2; continue
        out.append(ch); i += 1
    return "".join(out)


def _guru_finish(word: str) -> str:
    """Gurmukhi writes no virama in a cluster except the subjoined ਰ ਹ ਵ; a
    doubled consonant takes the addak (ਬੱਸ), and a nasal after a short vowel
    is the tippi (ਮੀਟਿੰਗ), after a long one the bindi (ਬੈਂਕ)."""
    word = re.sub("([\u0a15-\u0a39])\u0a4d\\1", "\u0a71\\1", word)
    word = re.sub("\u0a4d(?![ਰਹ])", "", word)
    # A y glide between vowels is a vowel letter in Gurmukhi: ਇੰਡੀਆ, ਵੀਡੀਓ, ਕੰਪਿਊਟਰ.
    word = re.sub("ਿਯ([ਾੋ])", lambda m: "ੀ" + {"ਾ": "ਆ", "ੋ": "ਓ"}[m.group(1)], word)
    word = re.sub("(?<=[\u0a15-\u0a39])ਯੂ", "ਿਊ", word)
    return re.sub("(?<=[\u0a15-\u0a39\u0a3c\u0a3f\u0a41\u0a42ਅਇਉ])\u0a02", "\u0a70", word)


def _orya_finish(word: str) -> str:
    # Odia ଯ is "ja": y, and the ya-phala (ବ୍ୟାଙ୍କ), are ୟ.
    return word.replace("\u0b2f", "\u0b5f")


_FINISH = {"mlym": _ml_finish, "guru": _guru_finish, "orya": _orya_finish}


def dev_to_script(dev: str, script: str) -> str:
    """Devanagari (with english_lexicon's vowel markers) in another script.
    Markers are left in place for the caller to fill."""
    dev = unicodedata.normalize("NFD", dev)        # फ़ U+095E -> फ + nukta
    if script != "deva":
        for a, b in _DIPHTHONGS:
            dev = dev.replace(a, b)
    if script == "beng":
        dev = re.sub("ंग(?=\\s|$)", "ं", dev)        # মিটিং, not মিটিংগ
        dev = re.sub("(?:^|(?<=\\s))यू", "इउ", dev)     # "you" ইউ: initial য reads j
        dev = re.sub("(?:^|(?<=\\s))य", "इय", dev)
        dev = dev.replace("्\ue009", "\ue009")
        # Bengali writes a nasal before t/d/p as the letter itself (মন্ডে,
        # অকাউন্ট); ং there would read "ng".
        dev = re.sub("[ंँ](?=[टठडढतथदधनचछजझ])", "न्", dev)
        dev = re.sub("[ंँ](?=[पफबभम])", "म्", dev)
        out = _dev_to_bengali(dev)
        # য after a vowel or at a syllable start is য় in Bengali spelling of
        # English (ভিডিয়ো); after a virama it is the য-phala and stays.
        return re.sub("(?<!\u09cd)য(?!\u09bc)", "য\u09bc", out)
    if script == "telu":
        return _dev_to_telugu(dev)
    if script == "taml":
        return _dev_to_tamil(dev)
    if script in _OFFSET:
        if script == "gujr":
            dev = dev.replace("ज\u093c", "झ")              # Gujarati writes z as ઝ
        elif script == "mlym":
            dev = _ml_prepare(dev)
        elif script == "orya":
            dev = re.sub("ंग(्?)(?=\\s|$)", "ं", dev)          # ମିଟିଂ
        return _offset_script(dev, script)
    return dev


def _close_word(word: str, consonants: frozenset, virama: str) -> str:
    return word + virama if word and word[-1] in consonants else word


# lang -> (script, whether a final consonant needs a virama, consonants, virama)
_SCRIPTS = {
    "te": ("telu", _TE_CONSONANTS, "\u0c4d"),
    "ta": ("taml", _TA_CONSONANTS, "\u0bcd"),
    "mr": ("deva", frozenset(), ""),
    "bn": ("beng", frozenset(), ""),
    "gu": ("gujr", frozenset(), ""),
    "kn": ("knda", frozenset(chr(c) for c in range(0x0C95, 0x0CBA)), "\u0ccd"),
    "ml": ("mlym", frozenset(chr(c) for c in range(0x0D15, 0x0D3A)), "\u0d4d"),
    "pa": ("guru", frozenset(), ""),
    "or": ("orya", frozenset(chr(c) for c in range(0x0B15, 0x0B3A)) | {"\u0b5f"}, "\u0b4d"),
}
# Every voice of these languages, IndicF5 included: measured 6 Nov 2026, it
# read English words better in its own script than in Devanagari (Bengali
# "Thank you ... Monday ... meeting" 25% -> 6% wrong, Marathi 24% -> 9%).
_SCRIPT_VOICE = {
    "te": re.compile(r"^(mms-tel|svara-te|parler-te|te_IN-|if5-te)"),
    "ta": re.compile(r"^(mms-tam|svara-ta|parler-ta|if5-ta)"),
    "mr": re.compile(r"^(svara-mr|parler-mr|mms-mar|if5-mr)"),
    "bn": _BENGALI_VOICE,
    "gu": re.compile(r"^(mms-guj|svara-gu|parler-gu|if5-gu)"),
    "kn": re.compile(r"^(mms-kan|svara-kn|parler-kn|if5-kn)"),
    "ml": re.compile(r"^(mms-mal|svara-ml|parler-ml|ml_IN-|if5-ml)"),
    "pa": re.compile(r"^(mms-pan|svara-pa|parler-pa|if5-pa)"),
    "or": re.compile(r"^(mms-ory|svara-or|parler-or|if5-or)"),
}


def _english_word(tok: str, lang: str) -> str:
    """One Latin word in the script of `lang`."""
    import english_lexicon
    script, consonants, virama = _SCRIPTS[lang]

    post = _FINISH.get(script)

    def done(out: str) -> str:
        return " ".join(post(w) for w in out.split(" ")) if post else out

    def finish(dev: str) -> str:
        out = english_lexicon.fill_marks(dev_to_script(dev, script), script)
        return done(" ".join(_close_word(w, consonants, virama) for w in out.split(" ")))

    acr = _acronym_devanagari(tok)
    if acr:
        return finish(acr)
    low = tok.lower()
    # The hand-made list holds the Indian way of saying a word (मोबाइल, not
    # the dictionary's American "mobul"), so it comes first. Scripts whose
    # readers say every written vowel get Hindi's silent ones marked
    # (ऑनलाइन would read "aa-na-laa-in").
    if low in _ENGLISH_LOANS:
        loan = unicodedata.normalize("NFD", _ENGLISH_LOANS[low])
        if script in english_lexicon.SAYS_EVERY_VOWEL:
            loan = _hindi_schwa_deletion(loan)
        return finish(loan)
    said = english_lexicon.pronounce(low, script)
    return done(said) if said else finish(_translit_latin(tok))


def script_language(voice_id: str) -> str:
    """The language code (a key of _SCRIPTS) of a voice whose English words
    need its own script, or ""."""
    v = (voice_id or "").replace("server:", "")
    return next((lang for lang, rx in _SCRIPT_VOICE.items() if rx.match(v)), "")


def to_script(text: str, lang: str) -> str:
    """Latin words in `text` rewritten in the script of `lang` (a key of
    _SCRIPTS). Text already in that script is left exactly as it is."""
    if lang not in _SCRIPTS or not _HAS_LATIN.search(text):
        return text
    # Only the Latin runs: _TOKEN's other runs are the customer's own text, and
    # str.isalpha() is true for Tamil or Bengali letters too. Until 6 Nov 2026
    # the text before the first English word went through the converter
    # (இந்த -> இந்த், যদি -> য়দি).
    out = "".join(_english_word(t, lang) if t[0].isascii() and t[0].isalpha() else t
                  for t in _TOKEN.findall(text))
    return unicodedata.normalize("NFC", out)
