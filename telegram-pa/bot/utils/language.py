from langdetect import detect, detect_langs, LangDetectException

_LANG_MAP = {
    "zh-cn": "zh-cn",
    "zh-tw": "zh-cn",
    "zh": "zh-cn",
    "ms": "ms",
    "en": "en",
}

# Minimum character length before attempting detection
_MIN_DETECT_LENGTH = 20

# Minimum confidence to trust a non-English detection
_MIN_CONFIDENCE = 0.85


def detect_language(text: str) -> str:
    if not text or len(text.strip()) < _MIN_DETECT_LENGTH:
        return "en"
    try:
        langs = detect_langs(text)
        # langs is a list of Language objects sorted by probability descending
        top = langs[0]
        lang_code = str(top.lang)
        prob = top.prob

        # Only trust Malay detection if very confident — it frequently
        # misdetects short English phrases as Malay
        if lang_code == "ms" and prob < _MIN_CONFIDENCE:
            return "en"

        return _LANG_MAP.get(lang_code, "en")
    except LangDetectException:
        return "en"
