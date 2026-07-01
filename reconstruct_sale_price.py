"""
reconstruct_sale_price.py  —  v3 (Deterministic Price Reconstruction Engine)
=============================================================================
Deterministic reconstruction and sanity validation for real estate sale prices.
Parses unstructured listing descriptions, extracts price rates, and handles
systematic anomalies (such as 10x/100x decimal shifts) to reconstruct accurate prices.
"""
import re
import math

_NUM = r'(\d[\d.,]*)'

MILIAR_SET = {'miliard', 'milyard', 'milliard', 'millyard',
              'milliar', 'millyar', 'miliar', 'milyar', 'billion'}
JUTA_SET = {'juta', 'jt', 'million', 'mio'}
RIBU_SET = {'ribu', 'rb'}


def _alt(words):
    return '|'.join(sorted(words, key=len, reverse=True))


UNIT_RX = r'(' + _alt(MILIAR_SET | JUTA_SET | RIBU_SET) + r'|m)?'
MILIAR_RX = r'(' + _alt(MILIAR_SET) + r')'


def parse_id_num(tok: str) -> float:
    """
    Parses Indonesian numeric formats. Dot (.) is treated as a thousands separator
    only if there are 2 or more groups (e.g., 1.100.000.000).
    A single group with a dot (e.g., 1.475) is treated as a decimal (1.475).
    """
    tok = tok.strip()
    if re.match(r'^\d{1,3}(\.\d{3}){2,}$', tok):
        return float(tok.replace('.', ''))
    tok = tok.replace(',', '.')
    try:
        return float(tok)
    except ValueError:
        return math.nan


def _unit_to_idr(val, unit):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return math.nan
    u = (unit or '').strip().lower()
    if u in MILIAR_SET or u == 'm':
        return val * 1e9
    if u in JUTA_SET:
        return val * 1e6
    if u in RIBU_SET:
        return val * 1e3
    return val


# Original tails for standard layout parsing
_PER_ARE_TAIL = r'\s*(?:/|per)\s*\d*\s*are\b'
_PER_ARE_TAIL_NOSEP = r'\s+are\b'

# Normalisation to collapse junk segments between the price and unit keywords
_PER_ARE_NORMALIZE = re.compile(
    r'(?:\s*(?:/|per)\s*\d{1,4}\s*m\s*[²2]?'
    r'|\s+nego|\s+net{1,2}|\s+buc)+'
    r'(?=\s*(?:/|per)?\s*are\b)', re.I)


def _per_are(s):
    s = _PER_ARE_NORMALIZE.sub(' ', s)   # collapse junk before original patterns run
    # 1) separator form
    m = re.search(_NUM + r'\s*' + UNIT_RX + _PER_ARE_TAIL, s)
    if m:
        v = parse_id_num(m.group(1)); u = m.group(2)
        if not u and v and 30 <= v <= 5000:
            u = 'juta'                       # plain number /are defaults to million (juta)
        return _unit_to_idr(v, u)
    m = re.search(r'rp\.?\s*' + _NUM + r'\s*' + UNIT_RX + _PER_ARE_TAIL, s)
    if m:
        return _unit_to_idr(parse_id_num(m.group(1)), m.group(2))
    # 2) separator-less form: REQUIRES an explicit price unit glued to "are"
    #    ("1.550 miliar are"), so a bare land size ("luas 2 are") never matches.
    m = re.search(_NUM + r'\s*(' + _alt(MILIAR_SET | JUTA_SET) + r'|m)' +
                  _PER_ARE_TAIL_NOSEP, s)
    if m:
        return _unit_to_idr(parse_id_num(m.group(1)), m.group(2))
    return math.nan


def _per_m2(s):
    # "/100 m2" or "per 100m2" is equivalent to per are
    m = re.search(_NUM + r'\s*' + UNIT_RX + r'\s*(?:/|per)\s*100\s*m\s*2?\b', s)
    if m:
        v = parse_id_num(m.group(1)); u = m.group(2)
        if not u and v and 30 <= v <= 5000:
            u = 'juta'
        return ('are', _unit_to_idr(v, u))
    # "/m2" or "per m2"
    m = re.search(_NUM + r'\s*' + UNIT_RX + r'\s*(?:/|per)\s*m\s*2\b', s)
    if m:
        v = parse_id_num(m.group(1)); u = m.group(2)
        if not u and v and v < 100:
            u = 'juta'
        return ('m2', _unit_to_idr(v, u))
    return ('', math.nan)


def _global(s):
    """
    Conservative global price screening. Extracts explicit milliard/million words,
    or plain 'm' only if accompanied by direct pricing context (e.g. rp., price, hrg).
    Prevents false matches of bare numbers and distance measurements.
    """
    best = math.nan

    def consider(v):
        nonlocal best
        if not math.isnan(v) and 100e6 <= v <= 200e9:
            if math.isnan(best) or v > best:
                best = v

    for m in re.finditer(_NUM + r'\s*' + MILIAR_RX + r'\b', s):
        consider(_unit_to_idr(parse_id_num(m.group(1)), 'm'))

    # plain "m" with specific currency/pricing context
    for m in re.finditer(r'(?:harga|hrg|rp\.?|:)\s*' + _NUM + r'\s*m\b(?!\s*[2²])', s):
        consider(parse_id_num(m.group(1)) * 1e9)
    for m in re.finditer(_NUM + r'\s*m\b(?!\s*[2²])\s*(?:nego|net|nett|cash|buc)', s):
        consider(parse_id_num(m.group(1)) * 1e9)

    return best


def reconstruct_price(raw_text: str, land_size_m2=None, building_size_m2=None):
    """
    Attempts to reconstruct total price from description and land/building sizes.
    Priority: per_are > per_100m2 > per_m2 > global.
    Returns: (reconstructed_price_idr, method_used)
    """
    s = (raw_text or '').lower()
    land_are = (land_size_m2 / 100.0) if land_size_m2 else None

    pa = _per_are(s)
    pm_kind, pm = _per_m2(s)
    g = _global(s)

    if not math.isnan(pa) and land_are:
        return round(pa * land_are), 'per_are'
    if pm_kind == 'are' and not math.isnan(pm) and land_are:
        return round(pm * land_are), 'per_100m2'
    if pm_kind == 'm2' and not math.isnan(pm) and land_size_m2:
        return round(pm * land_size_m2), 'per_m2'
    if not math.isnan(g):
        return round(g), 'global'
    return None, ''


RELIABLE = {'per_are', 'per_100m2', 'per_m2'}


def _price_is_sane(price, land_m2, building_m2, listing_kind):
    """
    Validation check to verify if a extracted price falls into a reasonable
    geographic range based on dimensions and properties.
    """
    if not price or price <= 0:
        return False
    is_built = bool(building_m2) or (listing_kind == 'sale')
    if is_built:
        if not (150e6 <= price <= 150e9):
            return False
        if land_m2 and land_m2 > 0:
            per = price / land_m2
            return 1e6 <= per <= 120e6   # IDR/m2 limits for built properties
        return True
    # land plot only
    if land_m2 and land_m2 > 0:
        per = price / land_m2
        return 100e3 <= per <= 100e6     # IDR/m2 limits for raw land
    return 50e6 <= price <= 200e9


def tier_for(stored_price, recon, method,
             land_m2=None, building_m2=None, listing_kind=None):
    """
    Categorises the pricing consistency tier of the record.
    Compares the stored/GPT-extracted price against the reconstructed price
    to detect systematic scaling shifts (e.g., 10x or 100x errors).
    """
    # 1) Reliable unit rate parsing is treated as the primary authority
    if method in RELIABLE and recon and recon > 0:
        if stored_price is None:
            return 'fill_from_text'
        rt = stored_price / recon
        if 0.9 <= rt <= 1.111:   return 'ok'          # within ±10% margin
        if 0.667 <= rt <= 1.5:
            # Prefer the reconstruction only if land size is validated
            explicit = method in ('per_are', 'per_100m2') and bool(land_m2)
            if explicit and _price_is_sane(recon, land_m2, building_m2, listing_kind):
                return 'use_recon'
            return 'ok'
        if 0.008 <= rt <= 0.012: return 'fix_100x_low'
        if 0.08 <= rt <= 0.12:   return 'fix_10x_low'
        if 8 <= rt <= 12:        return 'fix_10x_high'
        if 80 <= rt <= 120:      return 'fix_100x_high'
        
        # Fallback if reconstruction is consistent but differs significantly from GPT
        if _price_is_sane(recon, land_m2, building_m2, listing_kind):
            return 'use_recon'
        return 'review_mismatch'

    # 2) General fallback checks for systematic scale anomalies
    g = recon if method == 'global' and recon and recon > 0 else None
    if stored_price and g:
        rt = stored_price / g
        if 0.008 <= rt <= 0.012: return 'fix_100x_low'
        if 0.08 <= rt <= 0.12:   return 'fix_10x_low'
        if 8 <= rt <= 12:        return 'fix_10x_high'
        if 80 <= rt <= 120:      return 'fix_100x_high'

    # 3) Accept the standard price if it satisfies sanity bounds
    if stored_price and _price_is_sane(stored_price, land_m2, building_m2, listing_kind):
        return 'ok_gpt'

    if stored_price:
        return 'review_mismatch'
    if g and _price_is_sane(g, land_m2, building_m2, listing_kind):
        return 'fill_from_text'
    return 'no_reliable_recon'


# ==========================================================
# ROUTING GUARDS — rejects rentals misclassified as sales
# ==========================================================
_SALE_INTENT = re.compile(r'\b(di ?jual|for ?sale|harga jual|jual cepat|freehold)\b', re.I)
_RENT_INTENT = re.compile(
    r'\b(disewakan|dikontrakk?an|'
    r'(?:tanah|rumah|villa|kamar|kos|kost|ruko)\s+sewa|'
    r'sewa\s+(?:harian|bulanan|tahunan|mingguan)|'
    r'sub\s?lease|for\s+lease|for\s+rent|'
    r'/\s*thn|/\s*bln|/\s*tahun|/\s*bulan|/\s*th\b|/\s*bl\b|'
    r'/\s*year|/\s*month|/\s*yr|/\s*mo\b|'
    r'per\s+tahun|per\s+bulan|per\s+year|per\s+month|'
    r'/\s*are\s*/\s*year|/\s*are\s*/\s*yr|are\s*/\s*year|'
    r'juta\s*/\s*tahun|jt\s*/\s*are\s*/\s*thn)\b', re.I)


def is_lease_rate_listing(title, raw_text):
    """
    Checks if a listing belongs in rental tables instead of sales database.
    Ensures that active rental keywords are evaluated while preventing false positives
    on mixed-intent posts.
    """
    t = f"{title or ''} {raw_text or ''}".lower()
    return bool(_RENT_INTENT.search(t)) and not bool(_SALE_INTENT.search(t))


NON_BALI = [
    "yogyakarta", "jogja", "jogjakarta", "wirobrajan", "sleman", "bantul", "kulon progo", "gunungkidul",
    "jakarta", "bekasi", "depok", "tangerang", "bogor", "serpong", "bsd",
    "surabaya", "sidoarjo", "gresik", "mojokerto", "malang", "semarang", "solo", "surakarta",
    "bandung", "cimahi", "cirebon", "garut", "sukabumi",
    "lombok", "mataram", "makassar", "medan", "palembang", "balikpapan", "samarinda", "manado", "batam",
]
BALI_MARKERS = [
    "bali", "denpasar", "badung", "gianyar", "tabanan", "buleleng", "bangli", "karangasem", "klungkung",
    "jembrana", "singaraja", "negara", "semarapura", "amlapura",
    "canggu", "ubud", "sanur", "seminyak", "kuta", "jimbaran", "nusa dua", "uluwatu", "pererenan", "seseh",
    "cemagi", "kerobokan", "umalas", "pecatu", "ungasan", "sukawati", "mengwi", "kediri tabanan", "nyitdah",
    "renon", "sesetan", "sidakarya", "pemogan", "cekomaria", "peguyangan", "ubung", "balangan",
]


def is_non_bali(title, location, raw_text):
    """
    Geographic routing guard. Matches listing text against known regional datasets 
    and validates if the property is located in the target province.
    """
    t = f"{title or ''} {location or ''} {raw_text or ''}".lower()
    if any(b in t for b in BALI_MARKERS):
        return False
    return any(nb in t for nb in NON_BALI)


# ==========================================================
# FINAL NORMALIZED VALUE CALCULATION
# ==========================================================
FIX_TIERS = {'fix_10x_low', 'fix_10x_high', 'fix_100x_low', 'fix_100x_high',
             'fill_from_text', 'use_recon'}
TRUST_GPT_TIERS = {'ok', 'ok_gpt'}


def final_sale_price(gpt_price, recon, tier, is_lease=False):
    """
    Calculates the final clean price to be stored.
    Returns: Clean price integer or None (releasing to review queue)
    """
    if is_lease:
        return None
    if tier in TRUST_GPT_TIERS:
        return gpt_price
    if tier in FIX_TIERS and recon:
        return int(recon)
    return None


# ── GPT currency-misparse guard ──────────────────────────────────────────
_FOREIGN_CCY_RX = re.compile(r'\b(usd|us\$|\$|aud|eur|€|sgd|dollar)\b', re.I)

def correct_gpt_currency_misparse(gpt_price, raw_text):
    """
    Reverts erroneous ×16000 multiplications done by GPT models during
    raw currency parsing when the source text was already specified in IDR.
    """
    if not gpt_price or gpt_price <= 0:
        return gpt_price
    if _FOREIGN_CCY_RX.search(raw_text or ''):   # Valid foreign exchange listing
        return gpt_price
    if gpt_price >= 150_000_000:                 # Suspect only if implausibly small
        return gpt_price
    if gpt_price % 16000 != 0:
        return gpt_price
    juta = gpt_price // 16000
    if 30 <= juta <= 5000:                       # Corresponds to a standard IDR million range
        return int(juta * 1_000_000)
    return gpt_price
