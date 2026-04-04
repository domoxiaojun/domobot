import logging
import re

try:
    from babel.numbers import NumberFormatError, parse_decimal

    BABEL_AVAILABLE = True
except ImportError:
    BABEL_AVAILABLE = False

from utils.country_data import SUPPORTED_COUNTRIES

logger = logging.getLogger(__name__)

# Currency symbol to code mapping
CURRENCY_SYMBOL_TO_CODE = {
    "$": "USD",
    "USD": "USD",
    "€": "EUR",
    "£": "GBP",
    "₩": "KRW",
    "₺": "TRY",
    "₽": "RUB",
    "₹": "INR",
    "₫": "VND",
    "฿": "THB",
    "₱": "PHP",
    "₦": "NGN",
    "₴": "UAH",
    "₲": "PYG",
    "₪": "ILS",
    "₡": "CRC",
    "₸": "KZT",
    "₮": "MNT",
    "៛": "KHR",
    "CFA": "XOF",
    "FCFA": "XAF",
    "S/": "PEN",
    "Rs": "LKR",
    "NZ$": "NZD",
    "A$": "AUD",
    "C$": "CAD",
    "HK$": "HKD",
    "NT$": "TWD",
    "R$": "BRL",
    "RMB": "CNY",
    "RM": "MYR",
    "Rp": "IDR",
    "Bs.": "VES",
    "лв": "BGN",
    "S$": "SGD",
    "kr": "NOK",
    "TL": "TRY",
    "원": "KRW",
    "円": "JPY",
    "¥": "CNY",
    "₼": "AZN",
    "￥": "CNY",
    "EGP": "EGP",
    "Ft": "HUF",
    "zł": "PLN",
    "Kč": "CZK",
    "лев": "BGN",
    "lei": "RON",
}

# Currency multipliers for parsing
CURRENCY_MULTIPLIERS = {"ribu": 1000, "juta": 1000000, "k": 1000, "thousand": 1000}

# 3位小数货币例外列表 (中东货币)
THREE_DECIMAL_CURRENCIES = {"KWD", "BHD", "OMR", "TND", "LYD"}

# 反向映射：货币代码 → 货币符号 (用于格式化显示)
# 注意：多个符号可能映射到同一代码，这里保留最常用的符号
CURRENCY_CODE_TO_SYMBOL = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "KRW": "₩",
    "TRY": "₺",
    "RUB": "₽",
    "INR": "₹",
    "VND": "₫",
    "THB": "฿",
    "PHP": "₱",
    "NGN": "₦",
    "UAH": "₴",
    "PYG": "₲",
    "ILS": "₪",
    "CRC": "₡",
    "KZT": "₸",
    "MNT": "₮",
    "KHR": "៛",
    "XOF": "CFA",
    "XAF": "FCFA",
    "PEN": "S/",
    "LKR": "Rs",
    "NZD": "NZ$",
    "AUD": "A$",
    "CAD": "C$",
    "HKD": "HK$",
    "TWD": "NT$",
    "BRL": "R$",
    "MYR": "RM",
    "IDR": "Rp",
    "VES": "Bs.",
    "BGN": "лв",
    "SGD": "S$",
    "NOK": "kr",
    "SEK": "kr",
    "DKK": "kr",
    "ISK": "kr",
    "AZN": "₼",
    "CNY": "¥",
    "JPY": "¥",
    "EGP": "E£",
    "HUF": "Ft",
    "PLN": "zł",
    "CZK": "Kč",
    "RON": "lei",
    "CHF": "CHF",
    "AED": "د.إ",
    "SAR": "ر.س",
    "QAR": "ر.ق",
    "KWD": "د.ك",
    "BHD": ".د.ب",
    "OMR": "ر.ع.",
    "MXN": "$",
    "ARS": "$",
    "CLP": "$",
    "COP": "$",
    "ZAR": "R",
    "GHS": "₵",
    "MOP": "MOP$",
    "UYU": "$U",
    "TND": "د.ت",
    "LYD": "ل.د",
    "MAD": "د.م.",
    "JOD": "د.ا",
    "AMD": "֏",
    "GEL": "₾",
    "BYN": "Br",
    "PKR": "₨",
    "NPR": "₨",
    "BDT": "৳",
    "MMK": "Ks",
    "LAK": "₭",
}


def get_currency_symbol(currency_code: str) -> str:
    """
    获取货币代码对应的符号。

    Args:
        currency_code: 货币代码 (如 "USD", "CNY")

    Returns:
        货币符号 (如 "$", "¥")，未找到返回空字符串
    """
    if not currency_code:
        return ""
    # 先从 CURRENCY_CODE_TO_SYMBOL 查找
    symbol = CURRENCY_CODE_TO_SYMBOL.get(currency_code.upper())
    if symbol:
        return symbol
    # 再从 SUPPORTED_COUNTRIES 查找
    for country_info in SUPPORTED_COUNTRIES.values():
        if country_info.get("currency") == currency_code.upper():
            return country_info.get("symbol", "")
    return ""


# --- Pre-compiled Regex for performance ---
_currency_symbols = set(CURRENCY_SYMBOL_TO_CODE.keys())
_currency_symbols.add("¥")
for info in SUPPORTED_COUNTRIES.values():
    _currency_symbols.add(info["currency"])

_currency_patterns_escaped = [
    re.escape(cp) for cp in sorted(_currency_symbols, key=len, reverse=True)
]
_currency_pattern_str = "|".join(_currency_patterns_escaped)

_PATTERN_CURRENCY_FIRST = re.compile(
    rf"^(?P<currency>{_currency_pattern_str})\s*(?P<amount>.*?)$"
)
_PATTERN_AMOUNT_FIRST = re.compile(
    rf"^(?P<amount>.*?)\s*(?P<currency>{_currency_pattern_str})$"
)
# --- End of Pre-compiled Regex ---


def detect_currency_from_context(
    currency_symbol: str, price_str: str, country_code: str | None = None
) -> str:
    """Smartly detects currency, especially for the ambiguous ¥ and $ symbols."""
    if currency_symbol == "¥":
        if country_code:
            if country_code in ["CN", "HK", "TW", "MO"]:
                return "CNY"
            if country_code == "JP":
                return "JPY"

        price_lower = price_str.lower()
        if any(keyword in price_lower for keyword in ["人民币", "元", "rmb"]):
            return "CNY"
        if any(keyword in price_lower for keyword in ["円", "yen", "jpy"]):
            return "JPY"

        numbers = re.findall(r"\d+", price_str)
        if numbers:
            max_num = max(int(num) for num in numbers)
            if max_num >= 500:
                return "JPY"
            if max_num <= 100:
                return "CNY"
        return "CNY"

    # Handle $ symbol based on country_code
    # Many countries use $ symbol for their local currency, not USD.
    if currency_symbol == "$":
        if country_code:
            dollar_currency_map = {
                # 亚太
                "TW": "TWD",
                "HK": "HKD",
                "AU": "AUD",
                "CA": "CAD",
                "NZ": "NZD",
                "SG": "SGD",
                "BN": "BND",
                "FJ": "FJD",
                "SB": "SBD",
                "KY": "KYD",
                # 拉美
                "AR": "ARS",
                "CL": "CLP",
                "CO": "COP",
                "MX": "MXN",
                "UY": "UYU",
                "BS": "BSD",
                "BB": "BBD",
                "BM": "BMD",
                "GY": "GYD",
                "SR": "SRD",
                "JM": "JMD",
                "TT": "TTD",
                # 东加勒比元区
                "AI": "XCD",
                "DM": "XCD",
                "GD": "XCD",
                "LC": "XCD",
                "MS": "XCD",
                "KN": "XCD",
                "VC": "XCD",
                "AG": "XCD",
                # 非洲
                "NA": "NAD",
                "ZW": "ZWL",
                "LR": "LRD",
                "CV": "CVE",
            }
            if country_code in dollar_currency_map:
                return dollar_currency_map[country_code]
        # Default to USD (US, EC, PA, SV, FM 等真正使用 USD 的国家)
        return "USD"

    # Handle £ symbol based on country_code
    # Several countries use the £ symbol for their local currency
    if currency_symbol == "£":
        if country_code:
            pound_currency_map = {
                "EG": "EGP",
                "LB": "LBP",
                "SD": "SDG",
                "SS": "SSP",
                "SY": "SYP",
                "FK": "FKP",
                "GI": "GIP",
                "SH": "SHP",
            }
            if country_code in pound_currency_map:
                return pound_currency_map[country_code]
        return "GBP"

    return CURRENCY_SYMBOL_TO_CODE.get(currency_symbol, "USD")


def extract_currency_and_price(
    price_str: str, country_code: str | None = None, service: str | None = None
) -> tuple[str, float | None]:
    """
    Extracts currency code and numerical price from a price string.
    Uses babel for robust parsing with a fallback to regex for safety.

    Args:
        price_str: The price string to parse (e.g. "USD 5.99", "5,99 €")
        country_code: country code (e.g. "US", "AR", "CN")
        service: Service identifier (e.g. "app_store", "steam", "netflix")
                 "app_store" and "apple_services" will use smart parsing first to handle mixed formats.
                 Others will default to babel parsing (strict locale) first.
    """
    if not price_str or price_str.lower() in ["未知", "free", "免费"]:
        return "USD", 0.0

    price_str = price_str.replace("\xa0", " ").strip()

    currency_part = None
    amount_part = price_str

    match = _PATTERN_CURRENCY_FIRST.match(price_str)
    if match and re.search(r"\d", match.group("amount")):
        currency_part = match.group("currency")
        amount_part = match.group("amount").strip()
    else:
        match = _PATTERN_AMOUNT_FIRST.match(price_str)
        if match and re.search(r"\d", match.group("amount")):
            currency_part = match.group("currency")
            amount_part = match.group("amount").strip()

    detected_currency_code = None
    if currency_part:
        detected_currency_code = detect_currency_from_context(
            currency_part, price_str, country_code
        )

    if not detected_currency_code and country_code:
        detected_currency_code = SUPPORTED_COUNTRIES.get(country_code, {}).get(
            "currency", "USD"
        )
    elif not detected_currency_code:
        detected_currency_code = "USD"

    price_value = None

    # Determine parsing strategy based on service
    # Apple services often have mixed formats (USD in AR store), so we trust visual structure (smart parsing) more
    use_smart_parsing_first = service in ["app_store", "apple_services"]

    def try_smart_parsing():
        multiplier = 1
        cleaned_amount_part = amount_part
        for key, value in sorted(
            CURRENCY_MULTIPLIERS.items(), key=lambda x: len(x[0]), reverse=True
        ):
            if cleaned_amount_part.lower().endswith(key):
                multiplier = value
                cleaned_amount_part = cleaned_amount_part[: -len(key)].strip()
                break

        if cleaned_amount_part:
            amount_only = re.sub(r"[^\d.,]", "", cleaned_amount_part)
            val = _smart_parse_number(amount_only, detected_currency_code)
            if val is not None:
                return val * multiplier
        return None

    def try_babel_parsing():
        if not BABEL_AVAILABLE:
            return None
        try:
            locale_str = SUPPORTED_COUNTRIES.get(country_code, {}).get(
                "locale", "en_US"
            )
            # If standard service but USD currency, maybe still force en_US logic?
            # User said "Standard internationalized is standard", usually implies strictly following locale.
            # But let's stick to the prompt: Standard = Use Babel (strict locale).

            return float(parse_decimal(amount_part.strip(), locale=locale_str))
        except (NumberFormatError, ValueError, TypeError) as e:
            logger.debug(
                f"Babel parsing failed for '{amount_part}' with locale '{locale_str}': {e}"
            )
            return None

    if use_smart_parsing_first:
        # Strategy A: Smart Parsing -> Babel Parsing
        price_value = try_smart_parsing()
        if price_value is None:
            price_value = try_babel_parsing()
    else:
        # Strategy B: Babel Parsing -> Smart Parsing (Default)
        price_value = try_babel_parsing()
        if price_value is None:
            price_value = try_smart_parsing()

    return detected_currency_code, price_value


def _smart_parse_number(
    amount_cleaned: str, currency_code: str | None = None
) -> float | None:
    """
    智能解析数字字符串，基于位置优先规则判断小数点。

    规则：
    1. 从右往左第3位有标点 + 后2位数字 → 小数点
    2. 从右往左第4位有标点 + 后3位数字 → 千位分隔符 (除非是3位小数货币)
    3. 多标点间隔=3 → 都是千位分隔符
    """
    if not amount_cleaned:
        return None

    # 找出所有标点位置
    punctuation_positions = []
    for i, char in enumerate(amount_cleaned):
        if char in ".,":
            punctuation_positions.append((i, char))

    if not punctuation_positions:
        # 没有标点，直接转换
        try:
            return float(amount_cleaned)
        except ValueError:
            return None

    # 取最后一个标点
    last_pos, last_char = punctuation_positions[-1]
    digits_after = len(amount_cleaned) - last_pos - 1

    # 检查是否是3位小数货币
    is_three_decimal_currency = (
        currency_code and currency_code.upper() in THREE_DECIMAL_CURRENCIES
    )

    # 规则1: 从右数第3位有标点 + 后2位数字 → 小数点
    if digits_after == 2:
        decimal_part = amount_cleaned[last_pos + 1 :]
        integer_part = amount_cleaned[:last_pos].replace(",", "").replace(".", "")
        try:
            return float(f"{integer_part}.{decimal_part}")
        except ValueError:
            return None

    # 规则2: 从右数第4位有标点 + 后3位数字
    elif digits_after == 3:
        if is_three_decimal_currency:
            # 3位小数货币，这是小数点
            decimal_part = amount_cleaned[last_pos + 1 :]
            integer_part = amount_cleaned[:last_pos].replace(",", "").replace(".", "")
            try:
                return float(f"{integer_part}.{decimal_part}")
            except ValueError:
                return None
        else:
            # 规则3: 检查是否有多个标点且间隔一致（千位分隔符）
            if len(punctuation_positions) > 1:
                # 多标点，检查间隔
                intervals = []
                for i in range(1, len(punctuation_positions)):
                    interval = (
                        punctuation_positions[i][0] - punctuation_positions[i - 1][0]
                    )
                    intervals.append(interval)

                # 如果间隔都是4（包含标点本身），说明是千位分隔符
                if all(interval == 4 for interval in intervals):
                    # 都是千位分隔符
                    try:
                        return float(amount_cleaned.replace(",", "").replace(".", ""))
                    except ValueError:
                        return None

            # 默认：后3位数字且不是3位小数货币 → 千位分隔符
            try:
                return float(amount_cleaned.replace(",", "").replace(".", ""))
            except ValueError:
                return None

    # 规则4: 后1位数字 → 可能是小数点（某些地区只显示1位小数）
    elif digits_after == 1:
        decimal_part = amount_cleaned[last_pos + 1 :]
        integer_part = amount_cleaned[:last_pos].replace(",", "").replace(".", "")
        try:
            return float(f"{integer_part}.{decimal_part}")
        except ValueError:
            return None

    # 其他情况：移除所有标点
    try:
        return float(amount_cleaned.replace(",", "").replace(".", ""))
    except ValueError:
        return None


def extract_price_value_from_country_info(
    price_str: str, country_info: dict | None = None
) -> float:
    """
    Extracts numerical price from a price string based on country's number format.
    Delegates to extract_currency_and_price with service="apple_services" to use smart parsing.
    """
    country_code = None
    if country_info:
        # Try to find country code from country_info (this is a bit hacky but works for reverse lookup)
        # Ideally we should pass country_code directly
        for code, info in SUPPORTED_COUNTRIES.items():
            if info == country_info:
                country_code = code
                break

    # Use extract_currency_and_price with apple_services flag for smart parsing
    _, price_value = extract_currency_and_price(
        price_str, country_code=country_code, service="apple_services"
    )

    return price_value if price_value is not None else 0.0
