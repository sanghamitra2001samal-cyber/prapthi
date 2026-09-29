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
    r"^(hf_|hm_|parler-hi|chatterbox-hi|hi_IN-|mms-hin|svara-hi|if5-)")
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
    ("kh", "ख"), ("ee", "ी"), ("ea", "ी"), ("oo", "ू"), ("ou", "ाउ"), ("ai", "ै"),
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

    # English rarely ends on the inherent vowel; drop a trailing "ा"/"े".
    if len(text) > 2 and text[-1] in "ाे" and text[-2] in _CONSONANTS:
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
