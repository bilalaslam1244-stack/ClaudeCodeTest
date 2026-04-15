from langdetect import detect, LangDetectException

_LANG_MAP = {
    "zh-cn": "zh-cn",
    "zh-tw": "zh-cn",
    "zh": "zh-cn",
    "ms": "ms",
    "en": "en",
}


def detect_language(text: str) -> str:
    if not text or len(text.strip()) < 3:
        return "en"
    try:
        lang = detect(text)
        return _LANG_MAP.get(lang, "en")
    except LangDetectException:
        return "en"
