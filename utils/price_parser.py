import re
import logging

from utils.country_data import SUPPORTED_COUNTRIES

logger = logging.getLogger(__name__)

# Currency symbol to code mapping (extended from original scripts)
# Note: ¥ can be both JPY and CNY, handled separately in detect_currency_from_context
CURRENCY_SYMBOL_TO_CODE = {
    "$": "USD", "USD": "USD", "€": "EUR", "£": "GBP", "₩": "KRW",
    "₺": "TRY", "₽": "RUB", "₹": "INR", "₫": "VND", "฿": "THB", "₱": "PHP",
    "₦": "NGN", "₴": "UAH", "₲": "PYG", "₪": "ILS", "₡": "CRC", "₸": "KZT",
    "₮": "MNT", "៛": "KHR", "CFA": "XOF", "FCFA": "XAF", "S/": "PEN",
    "Rs": "LKR", "NZ$": "NZD", "A$": "AUD", "C$": "CAD", "HK$": "HKD",
    "NT$": "TWD", "R$": "BRL", "RM": "MYR", "Rp": "IDR", "Bs.": "VES",
    "лв": "BGN", "S$": "SGD", "kr": "NOK", "₼": "AZN", "￥": "CNY",
    "Ft": "HUF", "zł": "PLN", "Kč": "CZK", "лев": "BGN", "lei": "RON"
}

# Currency multipliers for parsing (e.g., 'ribu' for thousands)
CURRENCY_MULTIPLIERS = {'ribu': 1000, 'juta': 1000000, 'k': 1000, 'thousand': 1000}

def detect_currency_from_context(currency_symbol: str, price_str: str, country_code: str = None) -> str:
    """智能检测货币代码，特别处理¥符号的JPY/CNY冲突"""
    if currency_symbol == "¥":
        # 优先级1: 根据国家代码判断
        if country_code:
            if country_code in ["CN", "HK", "TW", "MO"]:  # 中国相关地区
                return "CNY"
            elif country_code == "JP":  # 日本
                return "JPY"
        
        # 优先级2: 根据价格文本内容判断
        price_lower = price_str.lower()
        
        # 中文相关关键词倾向CNY
        if any(keyword in price_lower for keyword in ["人民币", "元", "rmb", "cny", "中国", "cn"]):
            return "CNY"
        
        # 日文相关关键词倾向JPY  
        if any(keyword in price_lower for keyword in ["円", "yen", "jpy", "日本", "jp"]):
            return "JPY"
        
        # 优先级3: 根据价格数值范围启发式判断
        # 提取数值进行分析
        numbers = re.findall(r'\d+', price_str)
        if numbers:
            max_num = max(int(num) for num in numbers)
            # 日元通常数值较大（比如：¥1980），人民币相对较小（比如：¥29.8）
            if max_num >= 500:
                return "JPY"  # 大数值倾向日元
            elif max_num <= 100:
                return "CNY"  # 小数值倾向人民币
        
        # 默认情况：基于地区倾向，默认CNY
        return "CNY"
    
    # 其他货币符号直接查表
    return CURRENCY_SYMBOL_TO_CODE.get(currency_symbol, "USD")

def extract_currency_and_price(price_str: str, country_code: str | None = None) -> tuple[str, float | None]:
    """Extracts currency code and numerical price from a price string.
    Optionally uses country_code for fallback currency if symbol is ambiguous.
    """
    if not price_str or price_str.lower() in ['未知', 'free', '免费']:
        return "USD", 0.0

    price_str = price_str.replace('\xa0', ' ').strip()

    currency_symbols_and_codes = set(CURRENCY_SYMBOL_TO_CODE.keys())
    # 添加¥符号用于检测
    currency_symbols_and_codes.add("¥")
    for info in SUPPORTED_COUNTRIES.values():
        currency_symbols_and_codes.add(info['currency'])

    currency_patterns = sorted(currency_symbols_and_codes, key=len, reverse=True)
    currency_patterns_escaped = [re.escape(cp) for cp in currency_patterns]
    currency_pattern_str = '|'.join(currency_patterns_escaped)

    patterns = [
        rf'^(?P<currency>{currency_pattern_str})\s*(?P<amount>.*?)$',
        rf'^(?P<amount>.*?)\s*(?P<currency>{currency_pattern_str})$',
    ]

    currency_part = None
    amount_part = price_str

    for p_str in patterns:
        match = re.match(p_str, price_str)
        if match:
            potential_amount = match.group('amount').strip()
            if re.search(r'\d', potential_amount):
                currency_part = match.group('currency')
                amount_part = potential_amount
                break

    detected_currency_code = None
    if currency_part:
        # 使用智能检测处理¥符号冲突
        detected_currency_code = detect_currency_from_context(currency_part, price_str, country_code)
    
    # Fallback to country's default currency if symbol not directly mapped or found
    if not detected_currency_code and country_code:
        detected_currency_code = SUPPORTED_COUNTRIES.get(country_code, {}).get('currency', 'USD')
    elif not detected_currency_code: # Default to USD if no country code or no specific currency detected
        detected_currency_code = "USD"

    multiplier = 1
    for key, value in sorted(CURRENCY_MULTIPLIERS.items(), key=lambda x: len(x[0]), reverse=True):
        if amount_part.lower().endswith(key):
            multiplier = value
            amount_part = amount_part[:-len(key)].strip()
            break

    price_value = None
    if amount_part:
        amount_cleaned = re.sub(r'[^\d.,]', '', amount_part)
        decimal_match = re.search(r'[.,](\d{1,2})$', amount_cleaned)
        if decimal_match:
            decimal_part = decimal_match.group(1)
            integer_part = amount_cleaned[:decimal_match.start()].replace(',', '').replace('.', '')
            final_num_str = f"{integer_part}.{decimal_part}"
        else:
            final_num_str = amount_cleaned.replace(',', '').replace('.', '')

        try:
            price_value = float(final_num_str) * multiplier
        except ValueError:
            logger.warning(f"Price parsing failed: '{price_str}' -> '{final_num_str}'")
            price_value = None

    return detected_currency_code, price_value

def extract_price_value_from_country_info(price_str: str, country_info: dict) -> float:
    """Extracts numerical price from a price string based on country's number format.
    This version is specifically for cases where country_info (with symbol) is available.
    """
    try:
        # Remove invisible spaces and currency symbols
        price_str = price_str.replace('\xa0', ' ').replace(country_info.get('symbol', ''), '').strip()
        
        # Remove spaces
        price_str = price_str.replace(' ', '')
        
        # If string is empty or has no digits, return 0
        if not price_str or not re.search(r'\d', price_str):
            return 0.0
        
        # Clean common separators, keep last dot or comma as decimal point
        price_cleaned = re.sub(r'[^\d.,]', '', price_str)
        
        # Simple decimal point check: if last part is .XX or ,XX (1-3 digits), treat as decimal
        decimal_match = re.search(r'[.,](\d{1,3})$', price_cleaned)
        if decimal_match:
            decimal_part = decimal_match.group(1)
            # If 3 digits after decimal, it might be a thousands separator, not decimal
            if len(decimal_part) == 3:
                # Check if there are other separators before, if so, it's likely thousands
                before_decimal = price_cleaned[:decimal_match.start()]
                if re.search(r'[.,]', before_decimal):
                    # Other separators exist, so current one is likely thousands, remove all
                    final_num_str = price_cleaned.replace(',', '').replace('.', '')
                else:
                    # No other separators, but 3 digits is unusual, treat conservatively: remove all
                    final_num_str = price_cleaned.replace(',', '').replace('.', '')
            else:
                # 1-2 digits after decimal, treat as actual decimal point
                integer_part = price_cleaned[:decimal_match.start()].replace(',', '').replace('.', '')
                final_num_str = f"{integer_part}.{decimal_part}"
        else:
            # No obvious decimal part, remove all separators
            final_num_str = price_cleaned.replace(',', '').replace('.', '')
        
        return float(final_num_str)
    except Exception as e:
        logger.error(f"Price conversion failed: {e}, original price: {price_str}")
        return 0.0
