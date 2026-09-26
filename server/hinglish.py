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

_HINDI_VOICE = re.compile(r"^(hf_|hm_|parler-hi|chatterbox-hi)")
_HAS_LATIN = re.compile(r"[A-Za-z]")
_TOKEN = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


def is_hindi_voice(voice_id: str) -> bool:
    vid = (voice_id or "").replace("server:", "")
    return bool(_HINDI_VOICE.match(vid))


def to_devanagari(text: str) -> str:
    """Replace known romanized Hindi words with Devanagari; leave the rest."""
    if not _HAS_LATIN.search(text):
        return text

    def repl(tok: str) -> str:
        if not tok[0].isalpha():
            return tok
        hit = _DICT.get(tok.lower())
        return hit if hit else tok

    return "".join(repl(t) for t in _TOKEN.findall(text))
