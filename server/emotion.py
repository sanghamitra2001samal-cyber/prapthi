"""One emotion vocabulary for every engine, plus scenario detection.

Before this module each layer had its own list: the dashboard offered 19
emotions, app.py whitelisted 7 (everything else silently became "neutral"),
svara understood 3 tags and Chatterbox 7.  Now every engine reads its
settings from FEELS, so an emotion either works everywhere or not at all.

`detect()` powers emotion="auto": the text is split into sentences and each
gets the feeling its words call for (a condolence line is sympathetic, the
reassurance after it is warm), so delivery follows the scenario.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Feel:
    svara: str                      # svara sentence-end tag ("" = none)
    parler: str                     # Parler speaker-description fragment
    cbx: tuple[float, float]        # Chatterbox (exaggeration, cfg_weight)
    prosody: tuple[float, float, float]  # (speed, pitch, volume) multipliers


# svara-tts-v1 documents exactly: <happy> <sad> <anger> <fear> <clear>.
# Measured (hi_female, condolence line, 3 takes each, vs no tag 186 Hz):
#   <happy> +102 Hz, 7% faster   <anger> +77 Hz, 15% faster, loudest
#   <sad>    +44 Hz, 5% slower, quietest   <fear> +41 Hz, slow + quiet
#   <clear>  +54 Hz, 13% faster
# So sympathy/apology ride <sad>; urgency rides <clear> (NOT <fear>, which
# is slow and quiet).
FEELS: dict[str, Feel] = {
    "neutral": Feel("", "in a warm, expressive and natural tone", (0.5, 0.5), (1.0, 1.0, 1.0)),
    # --- feelings ---
    "happy": Feel("<happy>", "in a cheerful, upbeat and happy tone with bright, lively energy",
                  (0.85, 0.35), (1.03, 1.09, 1.02)),
    "excited": Feel("<happy>", "in a very excited, enthusiastic and energetic tone, speaking with high expressiveness",
                    (1.1, 0.3), (1.05, 1.13, 1.07)),
    "sad": Feel("<sad>", "in a soft, sad and melancholic tone, gently and slowly",
                (0.35, 0.8), (0.95, 0.91, 0.93)),
    "sympathetic": Feel("<sad>", "in a gentle, warm and deeply sympathetic tone, speaking softly and slowly with compassion",
                        (0.45, 0.7), (0.93, 0.96, 0.88)),
    "empathetic": Feel("<sad>", "in a warm, understanding and caring tone, speaking gently",
                       (0.45, 0.65), (0.95, 0.97, 0.9)),
    "reassuring": Feel("", "in a calm, warm, steady and reassuring tone, speaking kindly",
                       (0.4, 0.6), (0.95, 0.98, 0.95)),
    "apologetic": Feel("<sad>", "in a sincere, soft and apologetic tone, speaking humbly",
                       (0.4, 0.7), (0.95, 0.95, 0.9)),
    "grateful": Feel("<happy>", "in a warm, heartfelt and grateful tone",
                     (0.6, 0.5), (0.98, 1.04, 0.98)),
    "hopeful": Feel("<happy>", "in a gentle, bright and hopeful tone",
                    (0.6, 0.5), (0.99, 1.05, 1.0)),
    "calm": Feel("", "in a calm, soft, soothing and relaxed tone",
                 (0.35, 0.65), (0.97, 0.96, 0.94)),
    "romantic": Feel("", "in a soft, tender, intimate and romantic tone",
                     (0.55, 0.6), (0.95, 0.98, 0.9)),
    "angry": Feel("<anger>", "in an intense, forceful and angry tone",
                  (1.15, 0.35), (1.02, 0.97, 1.12)),
    "fear": Feel("<fear>", "in a trembling, anxious and fearful tone",
                 (0.9, 0.4), (1.04, 1.05, 0.92)),
    "surprise": Feel("<happy>", "in a surprised, astonished tone with rising energy",
                     (0.95, 0.35), (1.03, 1.12, 1.05)),
    "disgust": Feel("<anger>", "in a disgusted, disapproving tone",
                    (0.8, 0.5), (0.97, 0.94, 1.0)),
    # --- delivery styles ---
    "serious": Feel("", "in a serious, firm and confident, authoritative tone",
                    (0.5, 0.65), (0.99, 0.95, 1.02)),
    "narration": Feel("", "in a clear, engaging storytelling narration tone",
                      (0.55, 0.55), (0.97, 1.0, 1.0)),
    "conversation": Feel("", "in a relaxed, friendly conversational tone",
                         (0.6, 0.45), (1.02, 1.02, 1.0)),
    "news": Feel("<clear>", "in a crisp, clear and professional news-anchor tone",
                 (0.45, 0.6), (1.02, 1.0, 1.04)),
    "command": Feel("<clear>", "in a firm, loud and commanding tone",
                    (0.75, 0.5), (0.98, 0.95, 1.1)),
    "confident": Feel("", "in a confident, assured and positive tone",
                      (0.6, 0.5), (1.0, 0.98, 1.05)),
    "urgent": Feel("<clear>", "in an urgent, fast and tense tone",
                   (0.9, 0.3), (1.08, 1.04, 1.08)),
    "whisper": Feel("", "in a very soft, breathy, whispering voice",
                    (0.3, 0.6), (0.95, 1.0, 0.6)),
    "sarcastic": Feel("", "in a dry, ironic and sarcastic tone",
                      (0.7, 0.5), (0.98, 1.03, 1.0)),
}

EMOTIONS = set(FEELS) | {"auto"}
# Aliases the UI or API callers may send.
ALIASES = {"sympathy": "sympathetic", "empathy": "empathetic", "anger": "angry",
           "fearful": "fear", "surprised": "surprise", "conversational": "conversation",
           "commanding": "command", "sorry": "apologetic", "thankful": "grateful"}


def normalize(name: str) -> str:
    n = (name or "neutral").strip().lower()
    n = ALIASES.get(n, n)
    return n if n in EMOTIONS else "neutral"


def feel(name: str) -> Feel:
    return FEELS.get(name, FEELS["neutral"])


# --------------------------------------------------------------------------- #
# Scenario detection
# --------------------------------------------------------------------------- #
# Cues per feeling, in English, Hinglish (romanised) and native scripts.
# Order matters: earlier feelings win ties (grief beats plain sadness).
_CUES: list[tuple[str, list[str]]] = [
    ("sympathetic", [
        "passed away", "pass away", "lost your", "loss of", "condolence", "rest in peace",
        "rip", "my sympathies", "deepest sympathy", "so sorry for your", "sorry to hear",
        "heartbroken", "funeral", "demise", "no more with us",
        "नहीं रहे", "नहीं रही", "गुज़र गए", "गुजर गए", "निधन", "देहांत", "श्रद्धांजलि",
        "संवेदना", "दुख हुआ", "दुःख हुआ", "शोक", "आत्मा को शांति",
        "nahi rahe", "guzar gaye", "shraddhanjali", "dukh hua",
        "અવસાન", "નિધન", "શ્રદ્ધાંજલિ", "દુઃખ થયું", "દુખ થયું", "શોક",
    ]),
    ("apologetic", [
        "i apologize", "i apologise", "we apologize", "we apologise", "my apologies",
        "sorry for the", "sorry for any", "we regret", "please forgive", "my mistake",
        "क्षमा", "माफ़ी", "माफी", "माफ़ कीजिए", "माफ कीजिए", "खेद है",
        "maafi", "maaf kijiye", "kshama",
        "માફ કરશો", "માફી", "દિલગીર",
    ]),
    ("reassuring", [
        "don't worry", "dont worry", "do not worry", "you are not alone", "you're not alone",
        "i am with you", "i'm with you", "we are here for you", "it will be okay",
        "it's going to be okay", "everything will be fine", "take care", "stay strong",
        "we will help", "we'll help", "rest assured",
        "चिंता मत", "चिंता न", "घबराइए मत", "घबराओ मत", "अकेले नहीं", "आपके साथ हूँ",
        "आपके साथ हैं", "सब ठीक हो जाएगा", "ध्यान रखें", "हिम्मत रखें",
        "chinta mat", "ghabraiye mat", "sab theek ho jayega", "akele nahi",
        "ચિંતા ન", "ચિંતા કરશો નહીં", "એકલા નથી", "તમારી સાથે", "બધું સારું થઈ જશે",
    ]),
    ("grateful", [
        "thank you", "thanks a lot", "thanks so much", "grateful", "appreciate", "thankful",
        "धन्यवाद", "शुक्रिया", "आभार", "आभारी", "dhanyavaad", "dhanyavad", "shukriya",
        "આભાર", "ધન્યવાદ",
    ]),
    ("angry", [
        "angry", "furious", "unacceptable", "how dare", "outrageous", "fed up", "enough is enough",
        "गुस्सा", "क्रोध", "बर्दाश्त नहीं", "हद हो गई", "gussa", "bardasht nahi",
        "ગુસ્સો", "સહન નહીં",
    ]),
    ("fear", [
        "scared", "afraid", "terrified", "frightened", "panic", "help me", "danger",
        "डर", "भय", "बचाओ", "खतरा", "ख़तरा", "dar lag", "bachao",
        "ડર", "બચાવો", "ખતરો",
    ]),
    ("urgent", [
        "urgent", "immediately", "right now", "emergency", "hurry", "asap", "act now",
        "तुरंत", "जल्दी", "आपातकाल", "turant", "jaldi",
        "તરત", "તાત્કાલિક", "જલ્દી",
    ]),
    ("sad", [
        "sad", "unhappy", "cry", "crying", "tears", "lonely", "miss you", "heartache", "grief",
        "उदास", "दुखी", "आँसू", "आंसू", "रोना", "अकेला", "याद आती",
        "udaas", "dukhi", "yaad aati",
        "ઉદાસ", "દુઃખી", "આંસુ", "એકલું",
    ]),
    ("excited", [
        "congratulations", "congrats", "amazing", "awesome", "fantastic", "incredible", "wow",
        "hurray", "hooray", "can't wait", "cant wait",
        "बधाई", "मुबारक", "वाह", "शानदार", "कमाल", "badhai", "mubarak", "shandaar", "kamaal",
        "અભિનંદન", "વાહ", "શાનદાર",
    ]),
    ("happy", [
        "happy", "glad", "delighted", "joy", "wonderful", "great news", "good news", "love it",
        "खुश", "ख़ुश", "खुशी", "ख़ुशी", "आनंद", "अच्छी खबर", "अच्छी ख़बर",
        "khush", "khushi", "achhi khabar",
        "ખુશ", "ખુશી", "આનંદ", "સારા સમાચાર",
    ]),
    ("hopeful", [
        "hope", "hopefully", "better days", "bright future", "we will overcome",
        "उम्मीद", "आशा", "बेहतर दिन", "ummeed", "umeed",
        "આશા", "ઉમ્મીદ",
    ]),
    ("surprise", [
        "surprise", "unbelievable", "can't believe", "cant believe", "oh my god", "really?",
        "सच में?", "अरे", "यकीन नहीं", "sach mein?", "yakeen nahi",
        "ખરેખર?", "અરે",
    ]),
    ("romantic", [
        "i love you", "my love", "sweetheart", "darling",
        "प्यार करता", "प्यार करती", "मेरी जान", "pyaar karta", "pyar karta", "meri jaan",
        "પ્રેમ કરું",
    ]),
]

_LATIN = re.compile(r"[A-Za-z]")
_COMPILED: list[tuple[str, list[re.Pattern]]] = []
for _emo, _words in _CUES:
    pats = []
    for w in _words:
        esc = re.escape(w.lower())
        # Word boundaries only make sense for Latin cues; Indic scripts use
        # combining marks that \b does not treat as word characters.
        pats.append(re.compile(rf"(?<![a-z]){esc}(?![a-z])" if _LATIN.search(w) else esc))
    _COMPILED.append((_emo, pats))

_SPLIT = re.compile(r"(?<=[.!?।॥])\s+|\n+")


def classify(sentence: str) -> str | None:
    """Best feeling for one sentence, or None when nothing signals one."""
    s = sentence.lower()
    best, best_hits = None, 0
    for emo, pats in _COMPILED:
        hits = sum(1 for p in pats if p.search(s))
        if hits > best_hits:          # strict: earlier feeling wins ties
            best, best_hits = emo, hits
    if best:
        return best
    if s.rstrip().endswith("!"):
        return "excited" if s.count("!") > 1 else "happy"
    return None


def detect(text: str) -> list[tuple[str, str]]:
    """Split text into runs of (chunk, emotion).

    Sentences without a cue inherit the most recent feeling (a condolence is
    still being spoken sympathetically two sentences later), falling back to
    the text's dominant feeling, then neutral.  Adjacent runs that share a
    feeling are merged so engines get natural, full-length phrases.
    """
    sents = [x.strip() for x in _SPLIT.split(text.strip()) if x and x.strip()]
    if not sents:
        return [(text, "neutral")]
    labels = [classify(x) for x in sents]
    found = [x for x in labels if x]
    dominant = max(set(found), key=found.count) if found else "neutral"

    runs: list[tuple[str, str]] = []
    current = None
    for sent, lab in zip(sents, labels):
        emo = lab or current or dominant
        current = emo
        if runs and runs[-1][1] == emo:
            runs[-1] = (runs[-1][0] + " " + sent, emo)
        else:
            runs.append((sent, emo))
    return runs


if __name__ == "__main__":
    for t in [
        "I just heard your father passed away. I am so sorry. You are not alone, we are here for you.",
        "मुझे पता चला कि आपके पिताजी अब नहीं रहे। मैं आपके साथ हूँ, आप अकेले नहीं हैं।",
        "Congratulations on your new job! We are so happy for you.",
        "We apologize for the delay in your order. Thank you for your patience.",
        "Your appointment is on Monday at 10 am.",
        "તમારા પિતાજીના અવસાનના સમાચારથી દુઃખ થયું. ચિંતા કરશો નહીં, અમે તમારી સાથે છીએ.",
        "Aapka order late ho gaya, maaf kijiye. Chinta mat kijiye, kal tak pahunch jayega.",
    ]:
        print(detect(t))
