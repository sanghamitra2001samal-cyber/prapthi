"""Checks for the text an engine is given: numbers read aloud, English words in
the voice's script. Run from server/:  python test_text_prep.py  (or pytest).

Every expectation here was checked by ear or by a recogniser on the live voices
(6 Nov 2026); change one only with a measurement that says the new text reads
better.
"""
import re

import hinglish
import speech_text

EXPAND = [
    # Hindi / Bhojpuri / English, as before this change
    ("hi", "कीमत ₹2,450 है", "कीमत दो हज़ार चार सौ पचास रुपये है"),
    ("hi", "सुबह 10:30 बजे मिलेंगे", "सुबह साढ़े दस बजे मिलेंगे"),
    ("en", "Call 1800 123 4567", "Call one eight zero zero, one two three, four five six seven"),
    ("bho", "दो लोग 2 घंटे", "दो लोग दू घंटे"),
    # a number does not swallow the pause after it
    ("hi", "कीमत ₹2,450, फिर", "कीमत दो हज़ार चार सौ पचास रुपये, फिर"),
    ("en", "It costs ₹500, then", "It costs five hundred rupees, then"),
    # the currency already written is not said twice
    ("hi", "₹500 रुपये दो", "पाँच सौ रुपये दो"),
    # Tamil
    ("ta", "இந்த பொருளின் விலை ₹1,500, நீங்கள் 3 பொருட்கள் வாங்கலாம்.",
     "இந்த பொருளின் விலை ஆயிரத்து ஐநூறு ரூபாய், நீங்கள் மூன்று பொருட்கள் வாங்கலாம்."),
    ("ta", "கூட்டம் 15/08/2026 அன்று காலை 10:30 மணிக்கு நடக்கும்.",
     "கூட்டம் ஆகஸ்ட் பதினைந்து, இரண்டாயிரத்து இருபத்து ஆறு அன்று காலை பத்து முப்பது மணிக்கு நடக்கும்."),
    ("ta", "₹1 மட்டும்", "ஒரு ரூபாய் மட்டும்"),
    ("ta", "1998 இல்", "ஆயிரத்து தொள்ளாயிரத்து தொண்ணூற்றெட்டு இல்"),
    # Telugu
    ("te", "ఈ రోజు అన్ని వస్తువులపై 25% తగ్గింపు ఉంది.", "ఈ రోజు అన్ని వస్తువులపై ఇరవై ఐదు శాతం తగ్గింపు ఉంది."),
    ("te", "₹1,500 రూపాయలు", "ఒక వెయ్యి ఐదు వందల రూపాయలు"),
    ("te", "1998 లో", "పందొమ్మిది వందల తొంభై ఎనిమిది లో"),
    # Bengali
    ("bn", "মিটিং 15/08/2026 তারিখে সকাল 10:30 টায় হবে।",
     "মিটিং পনেরোই আগস্ট, দুই হাজার ছাব্বিশ তারিখে সকাল সাড়ে দশটায় হবে।"),
    ("bn", "3টি বই", "তিনটি বই"),
    ("bn", "₹5 lakh টাকার ঋণ", "পাঁচ লাখ টাকার ঋণ"),
    # Marathi
    ("mr", "मीटिंग 15/08/2026 रोजी सकाळी 10:30 वाजता होईल.",
     "मीटिंग पंधरा ऑगस्ट दोन हजार सव्वीस रोजी सकाळी साडेदहा वाजता होईल."),
    ("mr", "दुपारी 1:30 वाजता", "दुपारी दीड वाजता"),
    ("mr", "१५/०८/२०२६ रोजी", "पंधरा ऑगस्ट दोन हजार सव्वीस रोजी"),
]

SCRIPT = [
    ("te", "దయచేసి మీ email చూడండి, తర్వాత office కి call చేయండి.",
     "దయచేసి మీ ఈమేల్ చూడండి, తర్వాత ఆఫిస్ కి కాల్ చేయండి."),
    ("ta", "Thank you, எங்கள் team Monday முதல் online meeting நடத்தும்.",
     "தேங்க் யூ, எங்கள் டீம் மண்டே முதல் ஆன்லைன் மீட்டிங் நடத்தும்."),
    ("mr", "तुमची order उद्या delivery होईल", "तुमची ऑर्डर उद्या डिलिवरी होईल"),
    ("te", "పూర్తిగా తెలుగు వాక్యం.", "పూర్తిగా తెలుగు వాక్యం."),        # native text untouched
]
OTHER_SCRIPTS = {"te": "[ऀ-৿஀-௿]", "ta": "[ऀ-৿ఀ-౿]",
                 "mr": "[ঀ-৿஀-౿]", "bn": "[ऀ-ॿ஀-౿]"}
WORDS = ("email office call meeting please check mobile phone bank account password online order "
         "delivery thank you Monday WhatsApp OTP SBI app link update Google team manager free video "
         "photo computer internet class data India").split()


def test_expand():
    for lang, text, want in EXPAND:
        got = speech_text.expand(text, lang)
        assert got == want, f"{lang} {text!r}\n  got  {got}\n  want {want}"


def test_script():
    for lang, text, want in SCRIPT:
        got = hinglish.to_script(text, lang)
        assert got == want, f"{lang} {text!r}\n  got  {got}\n  want {want}"


def test_no_stray_script():
    """No converted word may keep a letter of another script or a marker."""
    for lang, other in OTHER_SCRIPTS.items():
        for w in WORDS:
            out = hinglish.to_script(w, lang)
            assert not re.search(other + "|[-]", out), f"{lang} {w} -> {out}"


if __name__ == "__main__":
    test_expand(); test_script(); test_no_stray_script()
    print(f"ok: {len(EXPAND)} number cases, {len(SCRIPT)} script cases, "
          f"{len(WORDS) * len(OTHER_SCRIPTS)} words checked for stray script")
