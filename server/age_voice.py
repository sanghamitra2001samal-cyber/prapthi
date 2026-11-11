"""Child and grandparent voices, made from an adult voice in the catalogue.

No model we run was trained on children or on old speakers, so these voices
are an adult voice reshaped with Praat (PSOLA "Change gender" + a pitch-tier
rewrite), after the adult engine has spoken:

  little girl / boy - a shorter vocal tract (every formant raised 26-30%) and
                      a child's pitch (300-330 Hz median), slightly slower,
                      with a livelier melody.
  grandma / grandpa - formants lowered 8%, slower (x1.20-1.25), an unsteady
                      voice: 5-7% cycle-to-cycle pitch wobble plus a 5.5 Hz
                      tremor in pitch and loudness, duller highs. Older
                      women's pitch drops (x0.86); older men's barely moves.

A voice id is the adult voice plus a suffix: "if5-aanya~girl". Everything that
looks a voice up by prefix (engine routing, plans, script handling) therefore
treats it exactly like its adult voice; only the sound is changed at the end.

Measured 9 Nov 2026 (scratchpad age/), with an age/gender model first
checked against real speech: real 9-10 year olds read as age 10, child
p=0.94; real 70+ women as 57 against 30 for women in their 20s-30s.
  girl:    age 9-11,  child p 0.97-0.98   (Hindi CER 4.2% -> 5.0%)
  boy:     age 14,    child p 0.85         (CER 5.8%)
  grandma: Hindi 46 -> 58, English 73      (CER unchanged)
  grandpa: +17 years, 66-70                (CER 4.2% -> 3.3%)
  grandma from a male voice: female p 0.97, age 69; grandpa from a female
  voice: male p 0.97, age 65. A male voice cannot be made into a convincing
  child (still read as an adult woman at +55% formants), so child voices exist
  only where the language has a female adult voice.
Bump VERSION whenever a profile changes: it is part of the audio cache key.

a2 (11 Nov 2026), after customers heard glitches and background noise. Measured
on 16 demo lines (scratchpad glitch/):
  * the senior wobble ran a SECOND overlap-add pass over the already reshaped
    take: pause noise rose 5-8 dB (French grandpa -53 -> -46 dB under speech);
  * one pitch search range (75-600 Hz) for every voice misread periods and
    left clicks (Hindi grandma 15 -> 51, Tamil girl 5 -> 25);
  * the wobble was white noise on a 10 ms pitch grid, i.e. a 5-7% pitch jump
    every 10 ms: stepped, not hoarse;
  * the 5.5 Hz loudness tremor also pulsed the hiss in every pause.
Now: ONE overlap-add pass (formant shift by sample-rate override, pitch,
duration and wobble together), a pitch search around the speaker's own pitch,
per-cycle jitter + a slow smooth wander + tremor for seniors, the loudness
tremor only while speaking, and pauses gated down by up to 12 dB. Pause noise
is now 8-20 dB lower than a1 and clicks are back near the adult take's count.
Ages on the model: children younger (girl 9-15, boy 10), seniors 44-69 (a1:
45-75; real 70+ women read as 57 on the same model).
"""
from __future__ import annotations

import os
import subprocess
import tempfile

VERSION = "a2"
KINDS = ("girl", "boy", "grandma", "grandpa")
LABEL = {"girl": "little girl", "boy": "little boy", "grandma": "grandma", "grandpa": "grandpa"}
GENDER = {"girl": "female", "boy": "male", "grandma": "female", "grandpa": "male"}
AGE = {"girl": "child", "boy": "child", "grandma": "senior", "grandpa": "senior"}

# (kind, base gender) -> Praat settings
PROFILES: dict[tuple[str, str], dict] = {
    ("girl", "female"): dict(formant=1.30, median=330, range=1.15, dur=1.06),
    ("boy", "female"): dict(formant=1.26, median=300, range=1.10, dur=1.06),
    # trem = 5.5 Hz pitch tremor, wander = slow smooth pitch drift, jit = per-cycle
    # jitter, atrem = loudness tremor (all fractions)
    ("grandma", "female"): dict(formant=0.92, ratio=0.86, range=0.90, dur=1.20,
                                trem=0.05, wander=0.03, jit=0.05, atrem=0.18, shelf=-4.0),
    ("grandpa", "male"): dict(formant=0.92, ratio=1.04, range=0.90, dur=1.25,
                              trem=0.05, wander=0.03, jit=0.05, atrem=0.18, shelf=-7.0),
    # cross-gender seniors, for languages with only one adult voice
    ("grandma", "male"): dict(formant=1.12, ratio=1.55, range=0.90, dur=1.20,
                              trem=0.05, wander=0.03, jit=0.05, atrem=0.18, shelf=-4.0),
    ("grandpa", "female"): dict(formant=0.77, ratio=0.52, range=0.90, dur=1.25,
                                trem=0.05, wander=0.03, jit=0.05, atrem=0.18, shelf=-7.0),
}
# a child from a male voice measured as an adult woman; never listed, but an
# id typed by hand still gets the strongest version rather than an error
PROFILES[("girl", "male")] = dict(formant=1.50, median=330, range=1.15, dur=1.06)
PROFILES[("boy", "male")] = dict(formant=1.45, median=300, range=1.10, dur=1.06)

# Tones carry meaning: keep the melody's range untouched there.
TONAL = {"vi", "zh", "yue", "cmn", "th", "lo", "my", "km", "yo", "ig", "ha"}

# locale -> (female adult voices, male adult voices), best first. The first one
# actually present in the catalogue is used. Chosen: fast engines first, never a
# non-commercial (MMS, NC Piper) voice, never an HD voice of unrecorded origin.
BASES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "hi-IN": (("if5-aanya", "hf_alpha"), ("if5-aarav", "hm_omega")),
    "bn-IN": (("if5-bn-f", "parler-bn-aditi"), ("if5-bn-m", "parler-bn-arjun")),
    "ta-IN": (("if5-ta-f", "parler-ta-kavitha"), ("if5-ta-m", "svara-ta-m")),
    "te-IN": (("if5-te-f", "parler-te-lalitha"), ("if5-te-m", "parler-te-prakash")),
    "kn-IN": (("if5-kn-f", "parler-kn-anu"), ("if5-kn-m", "parler-kn-suresh")),
    "ml-IN": (("if5-ml-f", "parler-ml-anjali"), ("if5-ml-m", "parler-ml-harish")),
    "mr-IN": (("if5-mr-f", "parler-mr-sunita"), ("if5-mr-m", "parler-mr-sanjay")),
    "gu-IN": (("if5-gu-f", "parler-gu-neha"), ("if5-gu-m", "parler-gu-yash")),
    "pa-IN": (("if5-pa-f", "svara-pa-f"), ("if5-pa-m", "parler-pa-divjot")),
    "or-IN": (("if5-or-f", "parler-or-debjani"), ("if5-or-m", "parler-or-manas")),
    "bho-IN": (("if5-bho-f", "parler-bho-sushma"), ("if5-bho-m", "parler-bho-manish")),
    "as-IN": (("parler-as-sita", "svara-as-f"), ("parler-as-amit", "svara-as-m")),
    "brx-IN": (("parler-brx-maya", "svara-brx-f"), ("parler-brx-bikram", "svara-brx-m")),
    "hne-IN": (("parler-hne-champa", "svara-hne-f"), ("parler-hne-bhanu", "svara-hne-m")),
    "doi-IN": (("svara-doi-f",), ("parler-doi-karan", "svara-doi-m")),
    "mag-IN": (("svara-mag-f",), ("svara-mag-m",)),
    "mai-IN": (("svara-mai-f",), ("svara-mai-m",)),
    "mni-IN": ((), ("parler-mni-laishram",)),
    "ne-NP": (("ne_NP-google-medium", "parler-ne-amrita"), ("ne_NP-chitwan-medium", "svara-ne-m")),
    "sa-IN": (("svara-sa-f",), ("parler-sa-aryan", "svara-sa-m")),
    "en-IN": (("parler-en-mary", "svara-en-f"), ("parler-en-thoma", "svara-en-m")),
    "en-US": (("af_heart",), ("am_michael",)),
    "en-GB": (("bf_emma",), ("bm_george",)),
    "ur-PK": (("ur_PK-aegis_female-medium",), ("ur_PK-fasih-medium",)),
    "zh-CN": (("zf_xiaoxiao",), ("zm_yunyang",)),
    "es-ES": (("ef_dora",), ("em_alex",)),
    "es-MX": (("es_MX-claude-high",), ("es_MX-ald-medium",)),
    "it-IT": (("if_sara",), ("im_nicola",)),
    "pt-BR": (("pf_dora",), ("pm_alex",)),
    "pt-PT": (("chatterbox-pt-beatriz",), ()),
    "fr-FR": (("ff_siwis", "fr_FR-siwis-medium"), ("fr_FR-mls-medium",)),
    "de-DE": (("chatterbox-de-lena",), ("de_DE-thorsten-high",)),
    "nl-NL": (("chatterbox-nl-sanne",), ("nl_NL-alex-medium",)),
    "nl-BE": (("nl_BE-nathalie-medium",), ("nl_BE-rdh-medium",)),
    "ru-RU": (("ru_RU-dmitri-medium",), ("ru_RU-denis-medium",)),
    "pl-PL": (("chatterbox-pl-zofia",), ("pl_PL-darkman-medium",)),
    "cs-CZ": (("cs_CZ-kasandra-medium",), ("cs_CZ-jirka-medium",)),
    "da-DK": (("chatterbox-da-freja",), ("da_DK-talesyntese-medium",)),
    "fi-FI": (("chatterbox-fi-aino",), ("fi_FI-harri-medium",)),
    "eu-ES": (("eu_ES-maider-medium",), ("eu_ES-antton-medium",)),
    "is-IS": (("is_IS-salka-medium",), ("is_IS-bui-medium",)),
    "ar": (("chatterbox-ar-layla",), ()),
    "ar-JO": ((), ("ar_JO-kareem-medium",)),
    "ca-ES": (("ca_ES-upc_ona-medium",), ()),
    "cy-GB": (("cy_GB-bu_tts-medium",), ()),
    "el-GR": (("el_GR-rapunzelina-medium",), ()),
    "he-IL": (("chatterbox-he-noa",), ()),
    "hu-HU": (("hu_HU-anna-medium",), ()),
    "ja-JP": (("chatterbox-ja-sakura",), ()),
    "ka-GE": (("ka_GE-natia-medium",), ()),
    "ko-KR": (("chatterbox-ko-jiwoo",), ()),
    "ms-MY": (("chatterbox-ms-nadia",), ()),
    "nb-NO": (("chatterbox-no-ingrid",), ()),
    "sk-SK": (("sk_SK-lili-medium",), ()),
    "sv-SE": (("sv_SE-alma-medium",), ()),
    "sw-KE": (("chatterbox-sw-zuri",), ()),
    "tr-TR": (("chatterbox-tr-elif",), ()),
    "vi-VN": (("vi_VN-vais1000-medium",), ()),
    "bg-BG": ((), ("bg_BG-dimitar-medium",)),
    "et-EE": ((), ("et_EE-news-medium",)),
    "fa-IR": ((), ("fa_IR-amir-medium",)),
    "kk-KZ": ((), ("kk_KZ-issai-high",)),
    "lv-LV": ((), ("lv_LV-aivars-medium",)),
    "no-NO": ((), ("no_NO-talesyntese-medium",)),
    "ro-RO": ((), ("ro_RO-mihai-medium",)),
    "sl-SI": ((), ("sl_SI-artur-medium",)),
    "sq-AL": ((), ("sq_AL-edon-medium",)),
    "sw-CD": ((), ("sw_CD-lanfrica-medium",)),
    "uk-UA": ((), ("uk_UA-mykyta-high",)),
}

# locale -> names for (girl, boy, grandma, grandpa); the picker adds the label.
NAMES: dict[str, tuple[str, str, str, str]] = {
    "hi-IN": ("Pari", "Chintu", "Dadi", "Dadaji"),
    "bn-IN": ("Mishti", "Bablu", "Thakuma", "Dadu"),
    "ta-IN": ("Meenu", "Kannan", "Paati", "Thatha"),
    "te-IN": ("Chinni", "Bujji", "Ammamma", "Thatayya"),
    "kn-IN": ("Putti", "Raju", "Ajji", "Ajja"),
    "ml-IN": ("Ammu", "Kunjunni", "Ammamma", "Appooppan"),
    "mr-IN": ("Chiu", "Sonu", "Aaji", "Aajoba"),
    "gu-IN": ("Chinki", "Bittu", "Baa", "Dada"),
    "pa-IN": ("Pinky", "Gopi", "Bebe", "Bapuji"),
    "or-IN": ("Lipi", "Bapi", "Jejema", "Jejebapa"),
    "bho-IN": ("Gudiya", "Chhotu", "Aaji", "Baba"),
    "as-IN": ("Moina", "Bubu", "Aita", "Koka"),
    "brx-IN": ("Rimi", "Raju", "Phulmoti", "Harendra"),
    "hne-IN": ("Munni", "Chhotu", "Dai", "Bade Baba"),
    "doi-IN": ("Guddi", "Bittu", "Dadi", "Dadu"),
    "mag-IN": ("Bebi", "Bauwa", "Dadi", "Baba"),
    "mai-IN": ("Bauwi", "Bauwa", "Dadi", "Baba"),
    "mni-IN": ("Thoibi", "Tomba", "Ibok", "Ipu"),
    "ne-NP": ("Maiya", "Kanchha", "Hajurama", "Hajurba"),
    "sa-IN": ("Gauri", "Balaka", "Pitamahi", "Pitamaha"),
    "en-IN": ("Pihu", "Kunal", "Nani", "Nana"),
    "en-US": ("Lily", "Max", "Grandma Rose", "Grandpa Joe"),
    "en-GB": ("Poppy", "Alfie", "Nana Margaret", "Grandad Arthur"),
    "ur-PK": ("Hiba", "Ahmed", "Dadi Jaan", "Dada Jaan"),
    "zh-CN": ("Xiaomei", "Xiaobao", "Nainai", "Yeye"),
    "es-ES": ("Martina", "Pablo", "Abuela Carmen", "Abuelo Paco"),
    "es-MX": ("Valeria", "Santi", "Abuelita Lupe", "Abuelito Chucho"),
    "it-IT": ("Chiara", "Matteo", "Nonna Rosa", "Nonno Pino"),
    "pt-BR": ("Bia", "Davi", "Vovó Lúcia", "Vovô Zé"),
    "pt-PT": ("Inês", "Tomás", "Avó Lurdes", "Avô Manel"),
    "fr-FR": ("Chloé", "Léo", "Mamie Odette", "Papi Marcel"),
    "de-DE": ("Mia", "Lukas", "Oma Helga", "Opa Heinz"),
    "nl-NL": ("Emma", "Daan", "Oma Truus", "Opa Kees"),
    "nl-BE": ("Lotte", "Mats", "Oma Rita", "Opa Jef"),
    "ru-RU": ("Masha", "Vanya", "Babushka Galina", "Dedushka Ivan"),
    "pl-PL": ("Zuzia", "Kuba", "Babcia Halina", "Dziadek Janusz"),
    "cs-CZ": ("Eliška", "Kubík", "Babička Jarmila", "Dědeček Josef"),
    "da-DK": ("Ida", "Oscar", "Mormor Inge", "Morfar Poul"),
    "fi-FI": ("Venla", "Eetu", "Mummo Aili", "Vaari Eino"),
    "eu-ES": ("Ane", "Iker", "Amona Miren", "Aitona Josu"),
    "is-IS": ("Embla", "Aron", "Amma Sigga", "Afi Gunnar"),
    "ar": ("Mariam", "Omar", "Jaddah Fatima", "Jaddi Mahmoud"),
    "ar-JO": ("Lina", "Zaid", "Teta Samira", "Jiddo Khalil"),
    "ca-ES": ("Martina", "Pau", "Àvia Montse", "Avi Jordi"),
    "cy-GB": ("Megan", "Osian", "Nain Gwen", "Taid Emrys"),
    "el-GR": ("Katerina", "Giorgos", "Giagia Sofia", "Pappous Nikos"),
    "he-IL": ("Maya", "Itai", "Savta Rina", "Saba Moshe"),
    "hu-HU": ("Lili", "Bence", "Nagymama Erzsi", "Nagypapa Feri"),
    "ja-JP": ("Hana", "Haruto", "Obaachan", "Ojiichan"),
    "ka-GE": ("Nini", "Luka", "Bebia Nana", "Babua Giorgi"),
    "ko-KR": ("Seoyeon", "Minjun", "Halmeoni", "Harabeoji"),
    "ms-MY": ("Aisyah", "Adam", "Nenek Siti", "Atuk Ismail"),
    "nb-NO": ("Nora", "Jakob", "Bestemor Kari", "Bestefar Ola"),
    "no-NO": ("Ingrid", "Emil", "Bestemor Solveig", "Bestefar Arne"),
    "sk-SK": ("Natálka", "Samko", "Babka Mária", "Dedko Jozef"),
    "sv-SE": ("Ella", "Hugo", "Mormor Britt", "Morfar Sven"),
    "sw-KE": ("Neema", "Baraka", "Bibi Mwanaisha", "Babu Hamisi"),
    "sw-CD": ("Zawadi", "Jabari", "Bibi Amani", "Babu Juma"),
    "tr-TR": ("Zeynep", "Emir", "Babaanne Ayşe", "Dede Mehmet"),
    "vi-VN": ("Ngọc", "Bin", "Bà Lan", "Ông Hùng"),
    "bg-BG": ("Mila", "Niki", "Baba Penka", "Dyado Ivan"),
    "et-EE": ("Mia", "Rasmus", "Vanaema Maie", "Vanaisa Jaan"),
    "fa-IR": ("Yasmin", "Arian", "Maman-bozorg Parvin", "Baba-bozorg Hassan"),
    "kk-KZ": ("Aiym", "Alikhan", "Äje Gulnar", "Ata Serik"),
    "lv-LV": ("Sofija", "Roberts", "Vecmāmiņa Inta", "Vectētiņš Jānis"),
    "ro-RO": ("Ioana", "Andrei", "Bunica Maria", "Bunicul Ion"),
    "sl-SI": ("Zala", "Luka", "Babica Marija", "Dedek Janez"),
    "sq-AL": ("Era", "Arbër", "Gjyshja Drita", "Gjyshi Agim"),
    "uk-UA": ("Solomiia", "Taras", "Babusia Halyna", "Didus Petro"),
}

_BASE_GENDER: dict[str, str] = {}
for _l, (_f, _m) in BASES.items():
    for _v in _f:
        _BASE_GENDER[_v] = "female"
    for _v in _m:
        _BASE_GENDER[_v] = "male"


def split(voice_id: str) -> tuple[str, str]:
    """("if5-aanya", "girl") for "if5-aanya~girl"; (voice_id, "") otherwise."""
    base, sep, kind = (voice_id or "").rpartition("~")
    if sep and base and kind in KINDS and ":" not in base:
        return base, kind
    return voice_id, ""


def catalogue(present: dict[str, str]) -> list[dict]:
    """Picker entries for every locale whose adult voice is in the catalogue.
    `present` maps voice id -> locale for the voices being listed."""
    out = []
    for lang, (fem, mal) in BASES.items():
        f = next((v for v in fem if present.get(v) == lang), None)
        m = next((v for v in mal if present.get(v) == lang), None)
        names = NAMES.get(lang)
        if not names or not (f or m):
            continue
        for kind, name in zip(KINDS, names):
            base = (f if kind in ("girl", "boy") else
                    (f or m) if kind == "grandma" else (m or f))
            if not base:
                continue
            out.append({"id": f"{base}~{kind}", "name": f"{name} ({LABEL[kind]})",
                        "lang": lang, "gender": GENDER[kind], "age": AGE[kind]})
    return out


def _median_f0(snd) -> float:
    from parselmouth.praat import call
    f0 = call(call(snd, "To Pitch", 0.0, 75, 600), "Get quantile", 0, 0, 0.5, "Hertz")
    return float(f0) if f0 == f0 else 0.0  # NaN -> 0


def _reshape(snd, p: dict, f0: float, tonal: bool):
    """Formants, pitch, duration and the senior wobble in ONE overlap-add pass.
    None when the take has too little voicing to reshape this way."""
    import numpy as np
    from parselmouth.praat import call

    sr = snd.sampling_frequency
    k = p["formant"]
    # search for periods around this speaker's own pitch: a 75-600 Hz search
    # on every voice misread periods and left clicks
    lo, hi = max(50.0, 0.55 * f0), min(700.0, 2.0 * f0)
    s = snd.copy()
    call(s, "Override sampling frequency", sr * k)      # every frequency x k, duration / k
    manip = call(s, "To Manipulation", 0.01, lo * k, hi * k)
    tier = call(manip, "Extract pitch tier")
    n = int(call(tier, "Get number of points"))
    if n < 3:
        return None
    t = np.array([call(tier, "Get time from index", i) for i in range(1, n + 1)])
    f = np.array([call(tier, "Get value at index", i) for i in range(1, n + 1)]) / k
    mold = float(np.median(f))
    mnew = p.get("median") or f0 * p.get("ratio", 1.0)
    rng = 1.0 if tonal else p.get("range", 1.0)
    new = np.exp(np.log(mnew) + rng * (np.log(f) - np.log(mold)))
    dur = p["dur"]
    trem, wander, jit = p.get("trem", 0.0), p.get("wander", 0.0), p.get("jit", 0.0)
    if trem or wander or jit:
        rs = np.random.default_rng(0)
        tout = t * dur * k                                # seconds in the finished take
        mod = 1 + trem * np.sin(2 * np.pi * 5.5 * tout)
        if wander:                                        # slow drift, a new target every 120 ms
            grid = np.arange(0.0, tout.max() + 0.12, 0.12)
            mod *= 1 + np.interp(tout, grid, rs.normal(0, wander, len(grid)))
        new = new * mod
        if jit:                                           # one point per glottal cycle
            tt, cur = [], float(t[0])
            while cur <= t[-1]:
                tt.append(cur)
                cur += 1.0 / (float(np.interp(cur, t, new)) * k)
            tt = np.array(tt)
            new = np.interp(tt, t, new) * (1 + rs.normal(0, jit, len(tt)))
            t = tt
    start, end = call(tier, "Get start time"), call(tier, "Get end time")
    nt = call("Create PitchTier", "age", start, end)
    for ti, v in zip(t, new * k):                        # the tier lives in the x k domain
        call(nt, "Add point", float(ti), float(v))
    call([nt, manip], "Replace pitch tier")
    dt = call("Create DurationTier", "age", start, end)
    call(dt, "Add point", 0.0, dur * k)
    call([dt, manip], "Replace duration tier")
    out = call(manip, "Get resynthesis (overlap-add)")
    return call(out, "Resample", sr, 50)


def _speech_env(y, sr):
    """Per sample, 1 while speaking and 0 in pauses (frames more than 30 dB under
    the speech level), with a 6 dB soft knee and ~30 ms smoothing."""
    import numpy as np

    n = max(1, int(0.01 * sr))
    m = len(y) // n
    if m < 3:
        return np.ones(len(y))
    fr = np.sqrt(np.mean(y[:m * n].reshape(m, n) ** 2, axis=1)) + 1e-9
    db = 20 * np.log10(fr)
    sp = np.percentile(db, 95)
    g = np.clip((db - (sp - 36.0)) / 6.0, 0, 1)
    w = np.hanning(7)
    g = np.convolve(g, w / w.sum(), mode="same")
    return np.interp(np.arange(len(y)), np.arange(m) * n + n / 2, g)


def make_age(path: str, kind: str, lang: str = "", base: str = "") -> bool:
    """Turn the adult WAV at `path` into `kind` in place. False = left untouched."""
    import numpy as np
    import parselmouth
    from parselmouth.praat import call

    if kind not in KINDS:
        return False
    tmp = path + ".age.wav"
    try:
        snd = parselmouth.Sound(path)
        if snd.n_channels > 1:
            snd = snd.convert_to_mono()
        sr = int(snd.sampling_frequency)
        f0 = _median_f0(snd)
        if f0 <= 0:
            return False
        gender = _BASE_GENDER.get(base) or ("male" if f0 < 165.0 else "female")
        p = PROFILES[(kind, gender)]
        tonal = lang.split("-")[0].lower() in TONAL
        out = _reshape(snd, p, f0, tonal)
        if out is None:                                   # almost no voicing: plain reshape
            median = p.get("median") or f0 * p.get("ratio", 1.0)
            out = call(snd, "Change gender", 75, 600, p["formant"], median,
                       1.0 if tonal else p.get("range", 1.0), p["dur"])

        y = out.values[0].astype(np.float64)
        env = _speech_env(y, out.sampling_frequency)
        atrem = p.get("atrem", 0.0)
        if atrem:                                         # tremble while speaking, not in pauses
            t = np.arange(len(y)) / out.sampling_frequency
            y = y * (1 + env * atrem * np.sin(2 * np.pi * 5.5 * t + 0.7))
        y = y * 10 ** (-(1 - env) * 12.0 / 20)            # pauses down by up to 12 dB
        peak = float(np.max(np.abs(y))) or 1.0
        parselmouth.Sound(y / peak * 0.89, sampling_frequency=out.sampling_frequency).save(tmp, "WAV")
        af = f"highshelf=f=3500:g={p['shelf']}," if p.get("shelf") else ""
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af",
                            af + "alimiter=limit=0.89", "-ar", str(sr), path + ".age2.wav"],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            return False
        os.replace(path + ".age2.wav", path)
        return True
    except Exception as e:  # never break synthesis over the age layer
        print(f"[voxforge] age shaping failed: {e!r}")
        return False
    finally:
        for f in (tmp, path + ".age2.wav"):
            try:
                os.remove(f)
            except OSError:
                pass


def apply(audio: bytes, mime: str, kind: str, lang: str = "", base: str = "") -> tuple[bytes, str]:
    """Age-shape a rendered take. Always returns WAV; on failure the take is
    returned unchanged rather than losing the customer's audio."""
    if not kind:
        return audio, mime
    fd, src = tempfile.mkstemp(suffix=".in")
    os.close(fd)
    wav = src + ".wav"
    try:
        with open(src, "wb") as f:
            f.write(audio)
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, wav],
                           capture_output=True, timeout=120)
        if r.returncode != 0 or not make_age(wav, kind, lang, base):
            return audio, mime
        with open(wav, "rb") as f:
            return f.read(), "audio/wav"
    finally:
        for f in (src, wav):
            try:
                os.remove(f)
            except OSError:
                pass
