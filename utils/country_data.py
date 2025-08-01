# Description: Consolidated country data for the Telegram bot.
# This file serves as the single source of truth for country codes, names,
# currencies, locales, and standard Unicode emoji flags.

SUPPORTED_COUNTRIES = {
    "AE": {"name": "阿联酋", "currency": "AED", "symbol": "د.إ", "locale": "ar_AE"},
    "AG": {"name": "安提瓜和巴布达", "currency": "XCD", "symbol": "$", "locale": "en_AG"},
    "AI": {"name": "安圭拉", "currency": "XCD", "symbol": "$", "locale": "en_AI"},
    "AL": {"name": "阿尔巴尼亚", "currency": "ALL", "symbol": "L", "locale": "sq_AL"},
    "AM": {"name": "亚美尼亚", "currency": "AMD", "symbol": "֏", "locale": "hy_AM"},
    "AO": {"name": "安哥拉", "currency": "AOA", "symbol": "Kz", "locale": "pt_AO"},
    "AR": {"name": "阿根廷", "currency": "ARS", "symbol": "$", "locale": "es_AR"},
    "AT": {"name": "奥地利", "currency": "EUR", "symbol": "€", "locale": "de_AT"},
    "AU": {"name": "澳大利亚", "currency": "AUD", "symbol": "A$", "locale": "en_AU"},
    "AZ": {"name": "阿塞拜疆", "currency": "AZN", "symbol": "₼", "locale": "az_AZ"},
    "BB": {"name": "巴巴多斯", "currency": "BBD", "symbol": "$", "locale": "en_BB"},
    "BE": {"name": "比利时", "currency": "EUR", "symbol": "€", "locale": "nl_BE"},
    "BF": {"name": "布基纳法索", "currency": "XOF", "symbol": "CFA", "locale": "fr_BF"},
    "BG": {"name": "保加利亚", "currency": "BGN", "symbol": "лв", "locale": "bg_BG"},
    "BH": {"name": "巴林", "currency": "BHD", "symbol": ".د.ب", "locale": "ar_BH"},
    "BJ": {"name": "贝宁", "currency": "XOF", "symbol": "CFA", "locale": "fr_BJ"},
    "BM": {"name": "百慕大", "currency": "BMD", "symbol": "$", "locale": "en_BM"},
    "BN": {"name": "文莱", "currency": "BND", "symbol": "$", "locale": "ms_BN"},
    "BO": {"name": "玻利维亚", "currency": "BOB", "symbol": "Bs.", "locale": "es_BO"},
    "BR": {"name": "巴西", "currency": "BRL", "symbol": "R$", "locale": "pt_BR"},
    "BS": {"name": "巴哈马", "currency": "BSD", "symbol": "$", "locale": "en_BS"},
    "BW": {"name": "博茨瓦纳", "currency": "BWP", "symbol": "P", "locale": "en_BW"},
    "BY": {"name": "白俄罗斯", "currency": "BYN", "symbol": "Br", "locale": "be_BY"},
    "BZ": {"name": "伯利兹", "currency": "BZD", "symbol": "BZ$", "locale": "en_BZ"},
    "CA": {"name": "加拿大", "currency": "CAD", "symbol": "C$", "locale": "en_CA"},
    "CH": {"name": "瑞士", "currency": "CHF", "symbol": "CHF", "locale": "de_CH"},
    "CL": {"name": "智利", "currency": "CLP", "symbol": "$", "locale": "es_CL"},
    "CN": {"name": "中国", "currency": "CNY", "symbol": "¥", "locale": "zh_CN"},
    "CO": {"name": "哥伦比亚", "currency": "COP", "symbol": "$", "locale": "es_CO"},
    "CR": {"name": "哥斯达黎加", "currency": "CRC", "symbol": "₡", "locale": "es_CR"},
    "CV": {"name": "佛得角", "currency": "CVE", "symbol": "$", "locale": "pt_CV"},
    "CY": {"name": "塞浦路斯", "currency": "EUR", "symbol": "€", "locale": "el_CY"},
    "CZ": {"name": "捷克", "currency": "CZK", "symbol": "Kč", "locale": "cs_CZ"},
    "DE": {"name": "德国", "currency": "EUR", "symbol": "€", "locale": "de_DE"},
    "DK": {"name": "丹麦", "currency": "DKK", "symbol": "kr", "locale": "da_DK"},
    "DM": {"name": "多米尼克", "currency": "XCD", "symbol": "$", "locale": "en_DM"},
    "DO": {"name": "多米尼加共和国", "currency": "DOP", "symbol": "RD$", "locale": "es_DO"},
    "DZ": {"name": "阿尔及利亚", "currency": "DZD", "symbol": "دج", "locale": "ar_DZ"},
    "EC": {"name": "厄瓜多尔", "currency": "USD", "symbol": "$", "locale": "es_EC"},
    "EE": {"name": "爱沙尼亚", "currency": "EUR", "symbol": "€", "locale": "et_EE"},
    "EG": {"name": "埃及", "currency": "EGP", "symbol": "£", "locale": "ar_EG"},
    "ES": {"name": "西班牙", "currency": "EUR", "symbol": "€", "locale": "es_ES"},
    "FI": {"name": "芬兰", "currency": "EUR", "symbol": "€", "locale": "fi_FI"},
    "FJ": {"name": "斐济", "currency": "FJD", "symbol": "$", "locale": "en_FJ"},
    "FM": {"name": "密克罗尼西亚", "currency": "USD", "symbol": "$", "locale": "en_FM"},
    "FR": {"name": "法国", "currency": "EUR", "symbol": "€", "locale": "fr_FR"},
    "GB": {"name": "英国", "currency": "GBP", "symbol": "£", "locale": "en_GB"},
    "GD": {"name": "格林纳达", "currency": "XCD", "symbol": "$", "locale": "en_GD"},
    "GH": {"name": "加纳", "currency": "GHS", "symbol": "₵", "locale": "en_GH"},
    "GM": {"name": "冈比亚", "currency": "GMD", "symbol": "D", "locale": "en_GM"},
    "GR": {"name": "希腊", "currency": "EUR", "symbol": "€", "locale": "el_GR"},
    "GT": {"name": "危地马拉", "currency": "GTQ", "symbol": "Q", "locale": "es_GT"},
    "GW": {"name": "几内亚比绍", "currency": "XOF", "symbol": "CFA", "locale": "pt_GW"},
    "GY": {"name": "圭亚那", "currency": "GYD", "symbol": "$", "locale": "en_GY"},
    "HK": {"name": "香港", "currency": "HKD", "symbol": "HK$", "locale": "zh_HK"},
    "HN": {"name": "洪都拉斯", "currency": "HNL", "symbol": "L", "locale": "es_HN"},
    "HR": {"name": "克罗地亚", "currency": "HRK", "symbol": "kn", "locale": "hr_HR"},
    "HU": {"name": "匈牙利", "currency": "HUF", "symbol": "Ft", "locale": "hu_HU"},
    "ID": {"name": "印度尼西亚", "currency": "IDR", "symbol": "Rp", "locale": "id_ID"},
    "IE": {"name": "爱尔兰", "currency": "EUR", "symbol": "€", "locale": "en_IE"},
    "IL": {"name": "以色列", "currency": "ILS", "symbol": "₪", "locale": "he_IL"},
    "IN": {"name": "印度", "currency": "INR", "symbol": "₹", "locale": "en_IN"},
    "IS": {"name": "冰岛", "currency": "ISK", "symbol": "kr", "locale": "is_IS"},
    "IT": {"name": "意大利", "currency": "EUR", "symbol": "€", "locale": "it_IT"},
    "JM": {"name": "牙买加", "currency": "JMD", "symbol": "J$", "locale": "en_JM"},
    "JO": {"name": "约旦", "currency": "JOD", "symbol": "د.ا", "locale": "ar_JO"},
    "JP": {"name": "日本", "currency": "JPY", "symbol": "¥", "locale": "ja_JP"},
    "KE": {"name": "肯尼亚", "currency": "KES", "symbol": "KSh", "locale": "en_KE"},
    "KG": {"name": "吉尔吉斯斯坦", "currency": "KGS", "symbol": "сом", "locale": "ky_KG"},
    "KH": {"name": "柬埔寨", "currency": "KHR", "symbol": "៛", "locale": "km_KH"},
    "KN": {"name": "圣基茨和尼维斯", "currency": "XCD", "symbol": "$", "locale": "en_KN"},
    "KR": {"name": "韩国", "currency": "KRW", "symbol": "₩", "locale": "ko_KR"},
    "KW": {"name": "科威特", "currency": "KWD", "symbol": "د.ك", "locale": "ar_KW"},
    "KY": {"name": "开曼群岛", "currency": "KYD", "symbol": "$", "locale": "en_KY"},
    "KZ": {"name": "哈萨克斯坦", "currency": "KZT", "symbol": "₸", "locale": "kk_KZ"},
    "LA": {"name": "老挝", "currency": "LAK", "symbol": "₭", "locale": "lo_LA"},
    "LB": {"name": "黎巴嫩", "currency": "LBP", "symbol": "ل.ل", "locale": "ar_LB"},
    "LC": {"name": "圣卢西亚", "currency": "XCD", "symbol": "$", "locale": "en_LC"},
    "LI": {"name": "列支敦士登", "currency": "CHF", "symbol": "CHF", "locale": "de_LI"},
    "LK": {"name": "斯里兰卡", "currency": "LKR", "symbol": "Rs", "locale": "si_LK"},
    "LT": {"name": "立陶宛", "currency": "EUR", "symbol": "€", "locale": "lt_LT"},
    "LU": {"name": "卢森堡", "currency": "EUR", "symbol": "€", "locale": "fr_LU"},
    "LV": {"name": "拉脱维亚", "currency": "EUR", "symbol": "€", "locale": "lv_LV"},
    "MA": {"name": "摩洛哥", "currency": "MAD", "symbol": "د.م.", "locale": "ar_MA"},
    "MD": {"name": "摩尔多瓦", "currency": "MDL", "symbol": "L", "locale": "ro_MD"},
    "MG": {"name": "马达加斯加", "currency": "MGA", "symbol": "Ar", "locale": "mg_MG"},
    "MK": {"name": "北马其顿", "currency": "MKD", "symbol": "ден", "locale": "mk_MK"},
    "ML": {"name": "马里", "currency": "XOF", "symbol": "CFA", "locale": "fr_ML"},
    "MM": {"name": "缅甸", "currency": "MMK", "symbol": "Ks", "locale": "my_MM"},
    "MN": {"name": "蒙古", "currency": "MNT", "symbol": "₮", "locale": "mn_MN"},
    "MO": {"name": "澳门", "currency": "MOP", "symbol": "MOP$", "locale": "zh_MO"},
    "MS": {"name": "蒙特塞拉特", "currency": "XCD", "symbol": "$", "locale": "en_MS"},
    "MT": {"name": "马耳他", "currency": "EUR", "symbol": "€", "locale": "mt_MT"},
    "MU": {"name": "毛里求斯", "currency": "MUR", "symbol": "₨", "locale": "en_MU"},
    "MW": {"name": "马拉维", "currency": "MWK", "symbol": "MK", "locale": "en_MW"},
    "MX": {"name": "墨西哥", "currency": "MXN", "symbol": "$", "locale": "es_MX"},
    "MY": {"name": "马来西亚", "currency": "MYR", "symbol": "RM", "locale": "ms_MY"},
    "MZ": {"name": "莫桑比克", "currency": "MZN", "symbol": "MT", "locale": "pt_MZ"},
    "NA": {"name": "纳米比亚", "currency": "NAD", "symbol": "$", "locale": "en_NA"},
    "NE": {"name": "尼日尔", "currency": "XOF", "symbol": "CFA", "locale": "fr_NE"},
    "NG": {"name": "尼日利亚", "currency": "NGN", "symbol": "₦", "locale": "en_NG"},
    "NI": {"name": "尼加拉瓜", "currency": "NIO", "symbol": "C$", "locale": "es_NI"},
    "NL": {"name": "荷兰", "currency": "EUR", "symbol": "€", "locale": "nl_NL"},
    "NO": {"name": "挪威", "currency": "NOK", "symbol": "kr", "locale": "no_NO"},
    "NP": {"name": "尼泊尔", "currency": "NPR", "symbol": "₨", "locale": "ne_NP"},
    "NZ": {"name": "新西兰", "currency": "NZD", "symbol": "NZ$", "locale": "en_NZ"},
    "OM": {"name": "阿曼", "currency": "OMR", "symbol": "ر.ع.", "locale": "ar_OM"},
    "PA": {"name": "巴拿马", "currency": "USD", "symbol": "$", "locale": "es_PA"},
    "PE": {"name": "秘鲁", "currency": "PEN", "symbol": "S/", "locale": "es_PE"},
    "PG": {"name": "巴布亚新几内亚", "currency": "PGK", "symbol": "K", "locale": "en_PG"},
    "PH": {"name": "菲律宾", "currency": "PHP", "symbol": "₱", "locale": "en_PH"},
    "PK": {"name": "巴基斯坦", "currency": "PKR", "symbol": "₨", "locale": "ur_PK"},
    "PL": {"name": "波兰", "currency": "PLN", "symbol": "zł", "locale": "pl_PL"},
    "PT": {"name": "葡萄牙", "currency": "EUR", "symbol": "€", "locale": "pt_PT"},
    "PY": {"name": "巴拉圭", "currency": "PYG", "symbol": "₲", "locale": "es_PY"},
    "QA": {"name": "卡塔尔", "currency": "QAR", "symbol": "ر.ق", "locale": "ar_QA"},
    "RO": {"name": "罗马尼亚", "currency": "RON", "symbol": "lei", "locale": "ro_RO"},
    "RS": {"name": "塞尔维亚", "currency": "RSD", "symbol": "дин", "locale": "sr_RS"},
    "RU": {"name": "俄罗斯", "currency": "RUB", "symbol": "₽", "locale": "ru_RU"},
    "RW": {"name": "卢旺达", "currency": "RWF", "symbol": "FRw", "locale": "rw_RW"},
    "SA": {"name": "沙特阿拉伯", "currency": "SAR", "symbol": "ر.س", "locale": "ar_SA"},
    "SB": {"name": "所罗门群岛", "currency": "SBD", "symbol": "$", "locale": "en_SB"},
    "SC": {"name": "塞舌尔", "currency": "SCR", "symbol": "₨", "locale": "fr_SC"},
    "SE": {"name": "瑞典", "currency": "SEK", "symbol": "kr", "locale": "sv_SE"},
    "SG": {"name": "新加坡", "currency": "SGD", "symbol": "S$", "locale": "en_SG"},
    "SI": {"name": "斯洛文尼亚", "currency": "EUR", "symbol": "€", "locale": "sl_SI"},
    "SK": {"name": "斯洛伐克", "currency": "EUR", "symbol": "€", "locale": "sk_SK"},
    "SL": {"name": "塞拉利昂", "currency": "SLL", "symbol": "Le", "locale": "en_SL"},
    "SN": {"name": "塞内加尔", "currency": "XOF", "symbol": "CFA", "locale": "fr_SN"},
    "SR": {"name": "苏里南", "currency": "SRD", "symbol": "$", "locale": "nl_SR"},
    "ST": {"name": "圣多美和普林西比", "currency": "STN", "symbol": "Db", "locale": "pt_ST"},
    "SV": {"name": "萨尔瓦多", "currency": "USD", "symbol": "$", "locale": "es_SV"},
    "SZ": {"name": "斯威士兰", "currency": "SZL", "symbol": "E", "locale": "en_SZ"},
    "TC": {"name": "特克斯和凯科斯群岛", "currency": "USD", "symbol": "$", "locale": "en_TC"},
    "TD": {"name": "乍得", "currency": "XAF", "symbol": "FCFA", "locale": "fr_TD"},
    "TH": {"name": "泰国", "currency": "THB", "symbol": "฿", "locale": "th_TH"},
    "TJ": {"name": "塔吉克斯坦", "currency": "TJS", "symbol": "ЅМ", "locale": "tg_TJ"},
    "TM": {"name": "土库曼斯坦", "currency": "TMT", "symbol": "m", "locale": "tk_TM"},
    "TN": {"name": "突尼斯", "currency": "TND", "symbol": "د.ت", "locale": "ar_TN"},
    "TO": {"name": "汤加", "currency": "TOP", "symbol": "T$", "locale": "to_TO"},
    "TR": {"name": "土耳其", "currency": "TRY", "symbol": "₺", "locale": "tr_TR"},
    "TT": {"name": "特立尼达和多巴哥", "currency": "TTD", "symbol": "$", "locale": "en_TT"},
    "TW": {"name": "台湾", "currency": "TWD", "symbol": "NT$", "locale": "zh_TW"},
    "TZ": {"name": "坦桑尼亚", "currency": "TZS", "symbol": "TSh", "locale": "en_TZ"},
    "UA": {"name": "乌克兰", "currency": "UAH", "symbol": "₴", "locale": "uk_UA"},
    "UG": {"name": "乌干达", "currency": "UGX", "symbol": "USh", "locale": "en_UG"},
    "US": {"name": "美国", "currency": "USD", "symbol": "$", "locale": "en_US"},
    "UY": {"name": "乌拉圭", "currency": "UYU", "symbol": "$", "locale": "es_UY"},
    "UZ": {"name": "乌兹别克斯坦", "currency": "UZS", "symbol": "сўм", "locale": "uz_UZ"},
    "VC": {"name": "圣文森特和格林纳丁斯", "currency": "XCD", "symbol": "$", "locale": "en_VC"},
    "VE": {"name": "委内瑞拉", "currency": "VES", "symbol": "Bs.", "locale": "es_VE"},
    "VG": {"name": "英属维尔京群岛", "currency": "USD", "symbol": "$", "locale": "en_VG"},
    "VN": {"name": "越南", "currency": "VND", "symbol": "₫", "locale": "vi_VN"},
    "WS": {"name": "萨摩亚", "currency": "WST", "symbol": "T", "locale": "sm_WS"},
    "YE": {"name": "也门", "currency": "YER", "symbol": "﷼", "locale": "ar_YE"},
    "ZA": {"name": "南非", "currency": "ZAR", "symbol": "R", "locale": "en_ZA"},
    "ZM": {"name": "赞比亚", "currency": "ZMW", "symbol": "ZK", "locale": "en_ZM"},
}

# Create a mapping from Chinese names to country codes for easy lookup
COUNTRY_NAME_TO_CODE = {info["name"]: code for code, info in SUPPORTED_COUNTRIES.items()}

# Create a set of all valid country inputs (codes and names)
VALID_COUNTRY_INPUTS = set(COUNTRY_NAME_TO_CODE.keys()) | set(SUPPORTED_COUNTRIES.keys())

# Standard Unicode flag emojis
# Source: https://emojipedia.org/flags
UNICODE_FLAG_EMOJIS = {
    "AE": "🇦🇪",
    "AG": "🇦🇬",
    "AI": "🇦🇮",
    "AL": "🇦🇱",
    "AM": "🇦🇲",
    "AO": "🇦🇴",
    "AR": "🇦🇷",
    "AT": "🇦🇹",
    "AU": "🇦🇺",
    "AZ": "🇦🇿",
    "BB": "🇧🇧",
    "BE": "🇧🇪",
    "BF": "🇧🇫",
    "BG": "🇧🇬",
    "BH": "🇧🇭",
    "BJ": "🇧🇯",
    "BM": "🇧🇲",
    "BN": "🇧🇳",
    "BO": "🇧🇴",
    "BR": "🇧🇷",
    "BS": "🇧🇸",
    "BW": "🇧🇼",
    "BY": "🇧🇾",
    "BZ": "🇧🇿",
    "CA": "🇨🇦",
    "CH": "🇨🇭",
    "CL": "🇨🇱",
    "CN": "🇨🇳",
    "CO": "🇨🇴",
    "CR": "🇨🇷",
    "CV": "🇨🇻",
    "CY": "🇨🇾",
    "CZ": "🇨🇿",
    "DE": "🇩🇪",
    "DK": "🇩🇰",
    "DM": "🇩🇲",
    "DO": "🇩🇴",
    "DZ": "🇩🇿",
    "EC": "🇪🇨",
    "EE": "🇪🇪",
    "EG": "🇪🇬",
    "ES": "🇪🇸",
    "FI": "🇫🇮",
    "FJ": "🇫🇯",
    "FM": "🇫🇲",
    "FR": "🇫🇷",
    "GB": "🇬🇧",
    "GD": "🇬🇩",
    "GH": "🇬🇭",
    "GM": "🇬🇲",
    "GR": "🇬🇷",
    "GT": "🇬🇹",
    "GW": "🇬🇼",
    "GY": "🇬🇾",
    "HK": "🇭🇰",
    "HN": "🇭🇳",
    "HR": "🇭🇷",
    "HU": "🇭🇺",
    "ID": "🇮🇩",
    "IE": "🇮🇪",
    "IL": "🇮🇱",
    "IN": "🇮🇳",
    "IO": "🇮🇴",
    "IQ": "🇮🇶",
    "IR": "🇮🇷",
    "IS": "🇮🇸",
    "IT": "🇮🇹",
    "JM": "🇯🇲",
    "JO": "🇯🇴",
    "JP": "🇯🇵",
    "KE": "🇰🇪",
    "KG": "🇰🇬",
    "KH": "🇰🇭",
    "KN": "🇰🇳",
    "KR": "🇰🇷",
    "KW": "🇰🇼",
    "KY": "🇰🇾",
    "KZ": "🇰🇿",
    "LA": "🇱🇦",
    "LB": "🇱🇧",
    "LC": "🇱🇨",
    "LI": "🇱🇮",
    "LK": "🇱🇰",
    "LT": "🇱🇹",
    "LU": "🇱🇺",
    "LV": "🇱🇻",
    "MA": "🇲🇦",
    "MD": "🇲🇩",
    "MG": "🇲🇬",
    "MK": "🇲🇰",
    "ML": "🇲🇱",
    "MM": "🇲🇲",
    "MN": "🇲🇳",
    "MO": "🇲🇴",
    "MS": "🇲🇸",
    "MT": "🇲🇹",
    "MU": "🇲🇺",
    "MW": "🇲🇼",
    "MX": "🇲🇽",
    "MY": "🇲🇾",
    "MZ": "🇲🇿",
    "NA": "🇳🇦",
    "NE": "🇳🇪",
    "NG": "🇳🇬",
    "NI": "🇳🇮",
    "NL": "🇳🇱",
    "NO": "🇳🇴",
    "NP": "🇳🇵",
    "NZ": "🇳🇿",
    "OM": "🇴🇲",
    "PA": "🇵🇦",
    "PE": "🇵🇪",
    "PG": "🇵🇬",
    "PH": "🇵🇭",
    "PK": "🇵🇰",
    "PL": "🇵🇱",
    "PT": "🇵🇹",
    "PY": "🇵🇾",
    "QA": "🇶🇦",
    "RO": "🇷🇴",
    "RS": "🇷🇸",
    "RU": "🇷🇺",
    "RW": "🇷🇼",
    "SA": "🇸🇦",
    "SB": "🇸🇧",
    "SC": "🇸🇨",
    "SD": "🇸🇩",
    "SE": "🇸🇪",
    "SG": "🇸🇬",
    "SI": "🇸🇮",
    "SK": "🇸🇰",
    "SL": "🇸🇱",
    "SN": "🇸🇳",
    "SO": "🇸🇴",
    "SR": "🇸🇷",
    "SS": "🇸🇸",
    "ST": "🇸🇹",
    "SV": "🇸🇻",
    "SY": "🇸🇾",
    "SZ": "🇸🇿",
    "TC": "🇹🇨",
    "TD": "🇹🇩",
    "TH": "🇹🇭",
    "TJ": "🇹🇯",
    "TM": "🇹🇲",
    "TN": "🇹🇳",
    "TO": "🇹🇴",
    "TR": "🇹🇷",
    "TT": "🇹🇹",
    "TV": "🇹🇻",
    "TW": "🇹🇼",
    "TZ": "🇹🇿",
    "UA": "🇺🇦",
    "UG": "🇺🇬",
    "US": "🇺🇸",
    "UY": "🇺🇾",
    "UZ": "🇺🇿",
    "VC": "🇻🇨",
    "VE": "🇻🇪",
    "VG": "🇻🇬",
    "VN": "🇻🇳",
    "WS": "🇼🇸",
    "YE": "🇾🇪",
    "ZA": "🇿🇦",
    "ZM": "🇿🇲",
    "ZW": "🇿🇼",
}


def get_country_flag(country_code: str) -> str:
    """Returns the standard Unicode flag emoji for a given country code."""
    return UNICODE_FLAG_EMOJIS.get(country_code.upper(), "🏳️")
