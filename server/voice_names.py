"""Customer-facing voice names.

A voice should be presented as a person, not as the machinery behind it. Three
things were leaking into the picker:

  * the engine and quality tier — "(Kokoro, Ultra)", "(Parler, HD)",
    "(Neural, MMS)", "(Svara, Emotional)"
  * bare language names where a character name was never set — so "Hindi"
    appeared several times over and looked like a duplicate
  * raw dataset identifiers from the upstream voice corpora — "Darkman",
    "Vais1000", "Upc Ona", "Serbski Institut", "Dfki"

`pretty()` turns any of those into a single, stable character name. Stability
matters: the same voice must always get the same name, so it is chosen by a
hash of the voice id rather than by list position, and it never changes when
voices are added or removed.
"""
from __future__ import annotations

import hashlib
import re

# --- engine / tier labels that must never reach a customer ---------------- #
_ENGINE_SUFFIX = re.compile(
    r"\s*\((?:Kokoro|Parler|Chatterbox|Svara|IndicF5|Neural|Cloned|Chant)"
    r"[^)]*\)\s*$", re.I)

# a second pass, for names built as "X (Neural, Medium)" after a trait group
_TIER_WORDS = re.compile(
    r"\s*\((?:Ultra|HD|Expressive|Emotional|Medium|High|Low|MMS|X-Low)\)\s*$", re.I)

# names that are really just the language, or an upstream corpus id
_LANGUAGE_WORDS = {
    "hindi", "tamil", "telugu", "bengali", "marathi", "gujarati", "kannada",
    "malayalam", "punjabi", "urdu", "odia", "assamese", "sanskrit", "english",
    "nepali", "maithili", "bodo", "dogri", "manipuri", "bhojpuri",
    "chhattisgarhi", "konkani", "sindhi", "kashmiri", "santali",
}
# Anything with a digit in it, our own product names, and the corpus/vendor
# names that ship with the upstream voice datasets.
_BRANDS = {
    "mls", "rdh", "dfki", "ald", "bass", "bui", "ganji", "google", "iseke",
    "issai", "marylux", "siwis", "sharvard", "talesyntese", "upc ona", "davefx",
    "darkman", "rapunzelina", "serbski institut", "lanfrica", "claude",
    "vagdhenu", "vāgdhenu", "prapthi", "svara", "kokoro", "chitwan", "faber",
    "cadu", "huayan", "thorsten", "carlfm", "tugao", "aissa", "hokuspokus",
    "karlsson", "eva k", "ramona", "pavoque", "kerstin", "nathalie", "joy",
}
_TECHNICAL = re.compile(r"^(?:.*\d.*|.*[_]\w+)$")


def _is_brand(name: str) -> bool:
    n = re.sub(r"\s+", " ", name.strip().lower())
    return n in _BRANDS or _TECHNICAL.match(n) is not None

# --- name pools, chosen to suit the language of the voice ----------------- #
_POOLS: dict[str, dict[str, list[str]]] = {
    "hi": {"female": ["Ishita", "Naina", "Trisha", "Vaishali", "Sanya", "Kritika"],
           "male":   ["Aarav", "Devansh", "Yuvraj", "Nakul", "Shaurya", "Tanmay"]},
    "ta": {"female": ["Nila", "Thamarai", "Kayal", "Ilakkiya", "Selvi"],
           "male":   ["Arasu", "Muthu", "Senthil", "Ilango", "Vetri"]},
    "te": {"female": ["Bhavana", "Sirisha", "Padmaja", "Vennela"],
           "male":   ["Teja", "Srikar", "Charan", "Bhaskar"]},
    "kn": {"female": ["Chaitra", "Shruthi", "Bhoomika", "Nandini"],
           "male":   ["Vikram", "Girish", "Sudeep", "Raghu"]},
    "ml": {"female": ["Devika", "Parvathy", "Nithya", "Ambika"],
           "male":   ["Nikhil", "Unni", "Vineeth", "Madhavan"]},
    "bn": {"female": ["Moushumi", "Rupa", "Shreya", "Ananta"],
           "male":   ["Arnab", "Bikash", "Shubho", "Tathagata"]},
    "mr": {"female": ["Sonal", "Manasi", "Rutuja", "Shubhangi"],
           "male":   ["Omkar", "Sarang", "Mandar", "Kedar"]},
    "gu": {"female": ["Hetal", "Krupa", "Nandita", "Palak"],
           "male":   ["Kunal", "Jignesh", "Parth", "Hardik"]},
    "pa": {"female": ["Simran", "Harleen", "Jasmeet", "Rupinder"],
           "male":   ["Manjit", "Gurdeep", "Ranbir", "Balwant"]},
    "as": {"female": ["Bhaswati", "Rituparna", "Jonaki"],
           "male":   ["Pranjal", "Himangshu", "Dhrubajyoti"]},
    "or": {"female": ["Sasmita", "Ipsita", "Mamata"],
           "male":   ["Sibaram", "Jagannath", "Bhagaban"]},
    "sa": {"female": ["Gayatri", "Vagdevi", "Maitreyi"],
           "male":   ["Vidyut", "Yajnesh", "Shaunak"]},
    "ne": {"female": ["Sunita", "Muna", "Pramila"], "male": ["Bikash", "Suman", "Niraj"]},
    "mai": {"female": ["Rewa", "Maithili Devi", "Sarita"],
            "male":   ["Bhola", "Shyam", "Raghunath"]},
    "doi": {"female": ["Kanta", "Shakti"], "male": ["Karan", "Vikrant"]},
    "brx": {"female": ["Kalpana", "Maya"], "male": ["Bikram", "Sanjib"]},
    "mni": {"female": ["Thoibi", "Chaoba"], "male": ["Laishram", "Ranjit"]},
    "hne": {"female": ["Champa", "Bhanu"], "male": ["Sukhram", "Dau"]},
    "bho": {"female": ["Gita", "Sushma"], "male": ["Manish", "Vijay"]},
    "ur": {"female": ["Sana", "Nadia", "Hina"], "male": ["Imran", "Faisal", "Zeeshan"]},
    "en": {"female": ["Evelyn", "Clara", "Harper", "Nora", "Freya", "Iris"],
           "male":   ["Julian", "Nathan", "Elliot", "Miles", "Owen", "Felix"]},
}
# Indian English should sound Indian, not Western.
_POOLS["en-IN"] = {"female": ["Anaya", "Rhea", "Tanvi", "Aditi"],
                   "male":   ["Rohit", "Karan", "Vivek", "Nikhil"]}
_POOLS.update({
    "ar": {"female": ["Layla", "Amira", "Salma", "Yasmin"],
           "male":   ["Kareem", "Omar", "Tariq", "Hassan"]},
    "fa": {"female": ["Shirin", "Roya", "Nasrin"], "male": ["Amir", "Reza", "Kian"]},
    "he": {"female": ["Noa", "Tamar", "Shira"], "male": ["Eitan", "Yonatan", "Amit"]},
    "tr": {"female": ["Elif", "Zeynep", "Deniz"], "male": ["Emre", "Baris", "Kerem"]},
    "el": {"female": ["Eleni", "Maria", "Dafni"], "male": ["Nikos", "Yiannis", "Stelios"]},
    "ru": {"female": ["Anya", "Katya", "Irina"], "male": ["Denis", "Dmitri", "Sergei"]},
    "uk": {"female": ["Oksana", "Iryna", "Sofiya"], "male": ["Mykyta", "Oleksa", "Taras"]},
    "zh": {"female": ["Xiaoxiao", "Xiaoyi", "Mei", "Lan"],
           "male":   ["Yunxi", "Yunjian", "Hao", "Wei"]},
    "ja": {"female": ["Sakura", "Yuki", "Aoi"], "male": ["Haruto", "Ren", "Sora"]},
    "ko": {"female": ["Jiwoo", "Seoyeon", "Hana"], "male": ["Minjun", "Jihoon", "Daeun"]},
    "vi": {"female": ["Linh", "Mai", "Thuy"], "male": ["Minh", "Tuan", "Duc"]},
    "th": {"female": ["Ploy", "Fah", "Napat"], "male": ["Anan", "Chai", "Krit"]},
    "id": {"female": ["Dewi", "Sari", "Putri"], "male": ["Budi", "Agus", "Rizki"]},
    "ms": {"female": ["Nadia", "Aisyah", "Farah"], "male": ["Azman", "Hakim", "Faiz"]},
    "sw": {"female": ["Zuri", "Amani", "Neema"], "male": ["Juma", "Baraka", "Tumaini"]},
    "de": {"female": ["Lena", "Greta", "Annika"], "male": ["Thorsten", "Jonas", "Lukas"]},
    "fr": {"female": ["Camille", "Élodie", "Margot"], "male": ["Étienne", "Julien", "Hugo"]},
    "es": {"female": ["Sofia", "Lucía", "Valeria", "Carmen", "Paloma", "Elena"],
           "male":   ["Mateo", "Diego", "Álvaro", "Javier", "Nicolás", "Tomás"]},
    "it": {"female": ["Giulia", "Paola", "Serena"], "male": ["Marco", "Lorenzo", "Dario"]},
    "pt": {"female": ["Beatriz", "Mariana", "Inês"], "male": ["Tiago", "Rafael", "Bruno"]},
    "nl": {"female": ["Sanne", "Femke", "Lotte", "Anouk", "Saskia", "Marieke"],
           "male":   ["Bram", "Daan", "Sven", "Joris", "Tijn", "Ruben"]},
    "pl": {"female": ["Zofia", "Kasia", "Ola"], "male": ["Jakub", "Piotr", "Marek"]},
    "cs": {"female": ["Tereza", "Klara", "Petra"], "male": ["Jirka", "Tomas", "Pavel"]},
    "sk": {"female": ["Lili", "Zuzana", "Ivana"], "male": ["Marek", "Juraj", "Peter"]},
    "hu": {"female": ["Anna", "Berta", "Reka"], "male": ["Bence", "Levente", "Zoltan"]},
    "ro": {"female": ["Ioana", "Elena", "Andreea"], "male": ["Mihai", "Andrei", "Radu"]},
    "sv": {"female": ["Alma", "Elsa", "Lisa"], "male": ["Erik", "Oskar", "Nils"]},
    "da": {"female": ["Freja", "Ida", "Karen"], "male": ["Mads", "Jonas", "Soren"]},
    "nb": {"female": ["Ingrid", "Sigrid", "Astrid"], "male": ["Henrik", "Lars", "Ola"]},
    "fi": {"female": ["Aino", "Kaisa", "Sanni"], "male": ["Harri", "Mikko", "Eero"]},
    "is": {"female": ["Salka", "Hekla", "Embla"], "male": ["Bjorn", "Jon", "Ari"]},
    "lv": {"female": ["Laima", "Ilze", "Dace"], "male": ["Aivars", "Janis", "Karlis"]},
    "sr": {"female": ["Milica", "Jelena", "Ana"], "male": ["Nikola", "Marko", "Stefan"]},
    "hr": {"female": ["Ivana", "Petra", "Maja"], "male": ["Luka", "Ivan", "Marin"]},
    "ca": {"female": ["Nuria", "Laia", "Clara"], "male": ["Jordi", "Marc", "Pau"]},
    "ka": {"female": ["Natia", "Nino", "Tamar"], "male": ["Giorgi", "Levan", "Irakli"]},
    "kk": {"female": ["Aigul", "Dana", "Zhanar"], "male": ["Arman", "Nurlan", "Askar"]},
    "lb": {"female": ["Chantal", "Marie", "Anne"], "male": ["Luc", "Jean", "Pol"]},
    "sl": {"female": ["Maja", "Nina", "Eva"], "male": ["Artur", "Matej", "Jure"]},
})

# only reached for a language we have not listed
_DEFAULT = {"female": ["Mira", "Nora", "Alina"], "male": ["Adrian", "Ivan", "Nils"]}


def _needs_name(base: str) -> bool:
    b = base.strip()
    if not b:
        return True
    if b.lower() in _LANGUAGE_WORDS:
        return True
    # "Hindi (alt)" and the like are still just a language
    head = re.sub(r"\s*\(.*\)\s*$", "", b).strip().lower()
    if head in _LANGUAGE_WORDS:
        return True
    return _is_brand(b)


def _pool_for(lang: str) -> dict[str, list[str]]:
    """Prefer the exact locale (en-IN) over the bare language (en)."""
    code = (lang or "en")
    return (_POOLS.get(code) or _POOLS.get(code.lower())
            or _POOLS.get(code.split("-")[0].lower()) or _DEFAULT)


def _assign(voice_id: str, lang: str, gender: str) -> str:
    pool = _pool_for(lang)
    names = pool.get((gender or "female").lower()) or pool["female"]
    # stable: the same voice id always lands on the same name
    h = int(hashlib.sha1(voice_id.encode()).hexdigest()[:8], 16)
    return names[h % len(names)]


def pretty(voice_id: str, raw: str, lang: str = "en", gender: str = "female") -> str:
    """The name a customer should see: a person, never the machinery."""
    name = _TIER_WORDS.sub("", _ENGINE_SUFFIX.sub("", raw or "")).strip()
    # Drop the " · Language" decoration wherever it sits — the picker already
    # shows the language, and it may be followed by a trait like "(soft)".
    name = re.sub(r"\s*·\s*[A-Z][a-zA-Z]+(?=\s*\(|\s*$)", "", name).strip()
    if _needs_name(name):
        return _assign(voice_id, lang, gender)
    # keep genuine character traits like (deep), (soft), (young)
    return name


def pretty_all(rows: list[tuple[str, str, str, str]]) -> dict[str, str]:
    """Name a whole catalogue at once, guaranteeing no two voices in the same
    language share a name.

    Done as a batch because uniqueness cannot be decided one voice at a time.
    Sorted by voice id so the result is identical on every call — a voice must
    not be renamed just because the catalogue was rebuilt."""
    out: dict[str, str] = {}
    taken: dict[str, set[str]] = {}
    for vid, raw, lang, gender in sorted(rows, key=lambda r: r[0]):
        key = (lang or "en").split("-")[0].lower()
        used = taken.setdefault(key, set())
        name = pretty(vid, raw, lang, gender)
        if name in used:
            pool = _pool_for(lang)
            names = pool.get((gender or "female").lower()) or pool["female"]
            # walk the pool from this voice's own starting point, so the
            # alternative is still deterministic for this voice
            start = int(hashlib.sha1(vid.encode()).hexdigest()[:8], 16) % len(names)
            for i in range(len(names)):
                cand = names[(start + i) % len(names)]
                if cand not in used:
                    name = cand
                    break
            else:
                # pool exhausted for this language: keep it unique and readable
                n = 2
                while f"{name} {n}" in used:
                    n += 1
                name = f"{name} {n}"
        used.add(name)
        out[vid] = name
    return out
