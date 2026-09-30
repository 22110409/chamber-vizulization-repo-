"""Country lookup (English / Arabic / codes), flags, icons and images."""
from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import ASSETS, FLAGS_DIR, ICONS_DIR

# ======================================================================
# Countries
# ======================================================================
_COUNTRIES: dict = json.loads((ASSETS / "countries.json").read_text(encoding="utf-8"))

# Extra spellings used in Jordanian / Arab statistics and everyday English.
EXTRA_ALIASES = {
    # Arabic
    "السعودية": "SA", "المملكة العربية السعودية": "SA", "السعوديه": "SA",
    "الصين": "CN", "الصين الشعبية": "CN", "جمهورية الصين الشعبية": "CN",
    "الامارات": "AE", "الإمارات": "AE", "الأمارات العربية": "AE", "الامارات العربية": "AE",
    "الولايات المتحدة": "US", "الولايات المتحدة الامريكية": "US", "الولايات المتحدة الأمريكية": "US",
    "امريكا": "US", "أمريكا": "US", "أميركا": "US",
    "المانيا": "DE", "ألمانيا": "DE", "بريطانيا": "GB", "المملكة المتحدة": "GB",
    "كوريا": "KR", "كوريا الجنوبية": "KR", "كوريا الشمالية": "KP",
    "روسيا": "RU", "روسيا الاتحادية": "RU", "تركيا": "TR", "العراق": "IQ",
    "سوريا": "SY", "سورية": "SY", "فلسطين": "PS", "السلطة الفلسطينية": "PS",
    "عمان": "OM", "سلطنة عمان": "OM", "مصر": "EG", "جمهورية مصر العربية": "EG",
    "الهند": "IN", "ايطاليا": "IT", "إيطاليا": "IT", "اسبانيا": "ES", "إسبانيا": "ES",
    "هولندا": "NL", "سويسرا": "CH", "فرنسا": "FR", "اليابان": "JP", "تايوان": "TW",
    "فيتنام": "VN", "هونغ كونغ": "HK", "هونج كونج": "HK", "ايران": "IR", "إيران": "IR",
    "الأردن": "JO", "الاردن": "JO", "لبنان": "LB", "الكويت": "KW", "قطر": "QA",
    "البحرين": "BH", "اليمن": "YE", "ليبيا": "LY", "تونس": "TN", "الجزائر": "DZ",
    "المغرب": "MA", "السودان": "SD", "اندونيسيا": "ID", "ماليزيا": "MY",
    "البرازيل": "BR", "الارجنتين": "AR", "أوكرانيا": "UA", "اوكرانيا": "UA",
    "رومانيا": "RO", "بلجيكا": "BE", "النمسا": "AT", "السويد": "SE", "كندا": "CA",
    "استراليا": "AU", "أستراليا": "AU", "باكستان": "PK", "بنغلادش": "BD",
    "بنجلاديش": "BD", "سنغافورة": "SG", "تايلند": "TH", "تايلاند": "TH",
    # English
    "usa": "US", "us": "US", "u.s.": "US", "u.s.a.": "US", "america": "US",
    "united states of america": "US", "uk": "GB", "u.k.": "GB", "britain": "GB",
    "great britain": "GB", "england": "GB", "uae": "AE", "u.a.e.": "AE", "emirates": "AE",
    "ksa": "SA", "saudi": "SA", "korea": "KR", "south korea": "KR", "republic of korea": "KR",
    "north korea": "KP", "russia": "RU", "iran": "IR", "syria": "SY", "turkey": "TR",
    "türkiye": "TR", "turkiye": "TR", "czech republic": "CZ", "czechia": "CZ",
    "vietnam": "VN", "taiwan province of china": "TW", "chinese taipei": "TW", "viet nam": "VN", "taiwan": "TW", "palestine": "PS",
    "hong kong": "HK", "china pr": "CN", "p.r. china": "CN", "holland": "NL",
    "the netherlands": "NL", "egypt": "EG", "ivory coast": "CI", "laos": "LA",
    "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ", "moldova": "MD",
    "macedonia": "MK", "north macedonia": "MK", "eswatini": "SZ", "swaziland": "SZ",
    "vatican": "VA", "kosovo": "XK", "burma": "MM",
}

NOT_COUNTRIES = {"other", "others", "rest of world", "total", "grand total", "world",
                 "أخرى", "اخرى", "دول أخرى", "دول اخرى", "باقي الدول", "المجموع",
                 "الإجمالي", "الاجمالي", "المجموع الكلي", "العالم"}

_AR_DIAC = re.compile(r"[ً-ْٰـ]")


def _norm(s: str) -> str:
    s = str(s).strip().lower()
    s = _AR_DIAC.sub("", s)
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
          .replace("ة", "ه").replace("ى", "ي"))
    s = re.sub(r"[\s\-_.,()'\"]+", " ", s).strip()
    s = s.replace("the ", "") if s.startswith("the ") else s
    return s


def _tokens(s: str) -> set:
    out = set()
    for t in _norm(s).split():
        if t.startswith("ال") and len(t) > 4:
            t = t[2:]
        if t not in {"of", "and", "&", "republic", "جمهوريه", "دوله"}:
            out.add(t)
    return out


@lru_cache(maxsize=1)
def _index():
    exact, names = {}, []
    for code, c in _COUNTRIES.items():
        for n in [code, c.get("iso3"), c["en"], c["ar"], *c.get("aliases", [])]:
            if n:
                exact.setdefault(_norm(n), code)
                names.append((n, code))
    for n, code in EXTRA_ALIASES.items():
        exact[_norm(n)] = code
        names.append((n, code))
    return exact, names


@lru_cache(maxsize=4096)
def country_code(name) -> str | None:
    """'Jordan', 'الأردن', 'JO', 'JOR', 'الصين الشعبية' -> ISO-2 code (or None)."""
    if name is None:
        return None
    raw = str(name).strip()
    if not raw or _norm(raw) in {_norm(x) for x in NOT_COUNTRIES}:
        return None
    exact, names = _index()
    n = _norm(raw)
    if n in exact:
        return exact[n]
    # token containment ("الصين الشعبية" -> "الصين")
    q = _tokens(raw)
    best, best_score = None, 0.0
    if q:
        for cand, code in names:
            t = _tokens(cand)
            if not t:
                continue
            inter = len(q & t)
            if inter and (q <= t or t <= q):
                score = inter / len(q | t)
                if score > best_score:
                    best, best_score = code, score
    if best and best_score >= 0.5:
        return best
    close = difflib.get_close_matches(n, list(exact), n=1, cutoff=0.86)
    return exact[close[0]] if close else None


def country_info(name) -> dict | None:
    code = country_code(name)
    return dict(_COUNTRIES[code]) if code and code in _COUNTRIES else None


def country_name(name, language: str = "en") -> str | None:
    info = country_info(name)
    return info[language] if info else None


def all_countries() -> list[dict]:
    return [dict(v) for v in _COUNTRIES.values()]


def looks_like_countries(labels, threshold: float = 0.8) -> bool:
    labels = [l for l in labels if l is not None and str(l).strip()]
    if not labels:
        return False
    real = [l for l in labels if _norm(l) not in {_norm(x) for x in NOT_COUNTRIES}]
    if not real:
        return False
    hits = sum(country_code(l) is not None for l in real)
    return hits / len(real) >= threshold


# ======================================================================
# Flags
# ======================================================================
@lru_cache(maxsize=1024)
def _load_png(path: str) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA")).astype(float) / 255.0


def flag(country, style: str = "round") -> np.ndarray | None:
    """RGBA image array of a country's flag (style 'round' or 'rect')."""
    code = country_code(country)
    if not code:
        return None
    p = FLAGS_DIR / style / f"{code.lower()}.png"
    return _load_png(str(p)) if p.exists() else None


def flag_path(country, style: str = "round") -> Path | None:
    code = country_code(country)
    if not code:
        return None
    p = FLAGS_DIR / style / f"{code.lower()}.png"
    return p if p.exists() else None


def load_image(path) -> np.ndarray:
    return _load_png(str(Path(path)))


# ======================================================================
# Icons (Tabler Icons, 5,000+ outline and 1,000+ filled)
# ======================================================================
_ICONS = json.loads((ICONS_DIR / "icons.json").read_text())

# keyword (English or Arabic) -> icon name. Used by icons="auto".
ICON_KEYWORDS = [
    (("mineral fuel", "fuel", "petrol", "oil", "gas", "وقود", "نفط", "زيوت معدنية", "محروقات", "بترول"), "flame"),
    (("electric", "electrical", "كهربائية", "كهربائي", "كهرباء"), "bolt"),
    (("vehicle", "car", "automobile", "tramway", "سيارات", "مركبات", "عربات"), "car"),
    (("pearl", "precious", "jewel", "gold", "diamond", "لؤلؤ", "أحجار كريمة", "احجار كريمة", "ذهب", "مجوهرات", "حلي"), "diamond"),
    (("nuclear", "reactor", "boiler", "machinery", "mechanical", "مفاعلات", "آلات", "الات", "أجهزة آلية", "مراجل"), "atom"),
    (("cereal", "wheat", "grain", "barley", "rice", "حبوب", "قمح", "شعير", "أرز", "ارز"), "wheat"),
    (("plastic", "لدائن", "بلاستيك"), "bottle"),
    (("pharma", "medic", "drug", "medicine", "صيدل", "أدوية", "ادوية", "دواء"), "pill"),
    (("fertili", "أسمدة", "اسمدة", "potash", "بوتاس", "phosphate", "فوسفات"), "plant"),
    (("cloth", "apparel", "garment", "textile", "knit", "ملابس", "ألبسة", "البسة", "نسيج", "منسوجات", "محبوكة"), "shirt"),
    (("iron", "steel", "حديد", "صلب", "فولاذ"), "building-factory-2"),
    (("aluminium", "aluminum", "copper", "metal", "ألمنيوم", "المنيوم", "نحاس", "معادن"), "hammer"),
    (("chemical", "organic", "inorganic", "كيماوية", "كيميائية", "عضوية"), "flask"),
    (("meat", "لحوم", "لحم"), "meat"), (("fish", "seafood", "أسماك", "اسماك"), "fish"),
    (("dairy", "milk", "egg", "ألبان", "البان", "حليب", "بيض"), "milk"),
    (("fruit", "nut", "فواكه", "ثمار", "مكسرات"), "apple"),
    (("vegetable", "خضار", "خضروات", "بقول"), "carrot"),
    (("sugar", "sweet", "confection", "سكر", "حلويات"), "candy"),
    (("coffee", "tea", "spice", "بن", "شاي", "توابل", "قهوة"), "coffee"),
    (("tobacco", "cigar", "تبغ", "دخان", "سجائر"), "smoking"),
    (("paper", "book", "print", "ورق", "كتب", "مطبوعات"), "book"),
    (("furniture", "أثاث", "اثاث"), "armchair"),
    (("rubber", "tyre", "tire", "مطاط"), "steering-wheel"),
    (("wood", "timber", "خشب", "أخشاب"), "tree"),
    (("glass", "زجاج"), "glass"), (("toy", "game", "ألعاب", "العاب"), "horse-toy"),
    (("footwear", "shoe", "أحذية", "احذية"), "shoe"),
    (("aircraft", "air", "طائرات", "جوي"), "plane"), (("ship", "boat", "vessel", "سفن", "بحري"), "ship"),
    (("perfume", "cosmetic", "essential oil", "عطور", "مستحضرات تجميل", "زيوت عطرية"), "perfume"),
    (("salt", "sulphur", "stone", "cement", "ملح", "كبريت", "أتربة", "اتربة", "أسمنت", "اسمنت", "حجر"), "mountain"),
    (("optical", "photo", "instrument", "بصرية", "تصوير"), "microscope"),
    (("animal", "live", "حيوانات", "مواشي"), "paw"),
    (("beverage", "drink", "مشروبات"), "glass-full"),
    (("service", "خدمات"), "briefcase"), (("tourism", "travel", "سياحة", "سفر"), "luggage"),
    (("export", "صادرات"), "package-export"), (("import", "مستوردات", "واردات"), "package-import"),
]


def icon_char(name: str, variant: str = "outline") -> str:
    """Unicode character for an icon name (see search_icons)."""
    table = _ICONS[variant]
    if name not in table:
        other = _ICONS["outline" if variant == "filled" else "filled"]
        if name in other:
            raise KeyError(f"Icon '{name}' only exists as variant="
                           f"'{'outline' if variant == 'filled' else 'filled'}'")
        hint = difflib.get_close_matches(name, list(table), n=5)
        raise KeyError(f"Unknown icon '{name}'. Did you mean: {', '.join(hint) or '-'}? "
                       f"Use cv.search_icons('{name}') to browse.")
    return chr(table[name])


def search_icons(query: str = "", variant: str = "outline", limit: int = 200) -> list[str]:
    """Find icon names containing the query, e.g. search_icons('truck')."""
    q = query.lower().strip()
    names = sorted(_ICONS[variant])
    hits = [n for n in names if q in n] if q else names
    return hits[:limit]


def _kw_match(word: str, text: str) -> bool:
    if re.search(r"[\u0600-\u06FF]", word):
        return word in text
    return re.search(r"\b" + re.escape(word), text) is not None


def auto_icon(label) -> str | None:
    """Guess an icon from a label (English or Arabic), e.g. 'Cereals' -> 'wheat'."""
    s = str(label).lower()
    for words, icon in ICON_KEYWORDS:
        if any(_kw_match(w, s) for w in words):
            return icon if icon in _ICONS["outline"] else None
    return None
