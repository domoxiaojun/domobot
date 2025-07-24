import datetime
import urllib.parse
import logging
from typing import Optional, Tuple, Dict, List

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

from utils.command_factory import command_factory
from utils.permissions import Permission
from utils.config_manager import get_config
from utils.formatter import foldable_text_v2, foldable_text_with_markdown_v2
from utils.message_manager import send_message_with_auto_delete, delete_user_command

# 全局变量
cache_manager = None
httpx_client = None

def set_dependencies(c_manager, h_client):
    global cache_manager, httpx_client
    cache_manager = c_manager
    httpx_client = h_client

WEATHER_ICONS = {
    '100': '☀️', '101': '🌤️', '102': '☁️', '103': '🌥️', '104': '⛅',
    '150': '🍃', '151': '🌬️', '152': '💨', '153': '🌪️', '300': '🌦️',
    '301': '🌧️', '302': '🌧️', '303': '⛈️', '304': '🌦️', '305': '🌧️',
    '306': '🌧️', '307': '⛈️', '308': '🌧️', '309': '🌦️', '310': '🌧️',
    '311': '🌧️', '312': '⛈️', '313': '🌧️', '314': '🌧️', '315': '⛈️',
    '316': '🌧️', '317': '🌧️', '318': '⛈️', '350': '🌨️', '351': '🌨️',
    '399': '🌨️', '400': '❄️', '401': '❄️', '402': '❄️', '403': '❄️',
    '404': '🌨️', '405': '❄️', '406': '❄️', '407': '❄️', '408': '❄️🌨️',
    '409': '❄️🌨️', '410': '❄️🌨️', '456': '🌪️', '457': '🌪️', '499': '❓',
    '500': '⛈️', '501': '⛈️', '502': '⛈️', '503': '⛈️', '504': '⛈️',
    '507': '⛈️🌨️', '508': '⛈️🌨️', '509': '⚡', '510': '⚡', '511': '⚡',
    '512': '⚡', '513': '⚡', '514': '⚡', '515': '⚡', '800': '☀️',
    '801': '🌤️', '802': '☁️', '803': '☁️', '804': '☁️', '805': '🌫️',
    '806': '🌫️', '807': '🌧️', '900': '🌪️', '901': '🌀', '999': '❓'
}

INDICES_EMOJI = {
    "1": "🏃",  # 运动
    "2": "🚗",  # 洗车
    "3": "👕",  # 穿衣
    "4": "🎣",  # 钓鱼
    "5": "☀️",  # 紫外线
    "6": "🏞️",  # 旅游
    "7": "🤧",  # 过敏
    "8": "😊",  # 舒适度
    "9": "🤒",  # 感冒
    "10": "🌫️", # 空气污染扩散
    "11": "❄️", # 空调开启
    "12": "🕶️", # 太阳镜
    "13": "💄", # 化妆
    "14": "👔", # 晾晒
    "15": "🚦", # 交通
    "16": "🧴", # 防晒
}

# 生活指数的逻辑分类
CATEGORIES = {
    "户外活动": ["1", "4", "6"],           # 运动, 钓鱼, 旅游
    "出行建议": ["2", "15"],             # 洗车, 交通
    "生活起居": ["3", "8", "11", "14"],   # 穿衣, 舒适度, 空调, 晾晒
    "健康关注": ["7", "9", "10"],          # 过敏, 感冒, 空气污染扩散
    "美妆护理": ["5", "12", "13", "16"],  # 紫外线, 太阳镜, 化妆, 防晒
}

async def _get_api_response(endpoint: str, params: Dict) -> Optional[Dict]:
    config = get_config()
    if not config.qweather_api_key:
        logging.error("和风天气 API Key 未配置")
        return None
    try:
        base_url = "https://api.qweather.com/v7/" if not endpoint.startswith("geo/") else "https://geoapi.qweather.com/v2/"
        api_endpoint = endpoint.replace("geo/", "")
        all_params = {"key": config.qweather_api_key, "lang": "zh", **params}
        response = await httpx_client.get(f"{base_url}{api_endpoint}", params=all_params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == "200":
                return data
            else:
                logging.warning(f"和风天气 API ({endpoint}) 返回错误代码: {data.get('code')}")
                return data
        else:
            logging.warning(f"和风天气 API ({endpoint}) 请求失败: HTTP {response.status_code}")
    except Exception as e:
        logging.error(f"和风天气 API ({endpoint}) 请求异常: {e}")
    return None

async def get_location_id(location: str) -> Optional[Dict]:
    cache_key = f"weather_location_{location.lower()}"
    cached_data = await cache_manager.load_cache(cache_key, subdirectory="weather")
    if cached_data: return cached_data
    
    data = await _get_api_response("geo/city/lookup", {"location": location})
    if data and data.get("location"):
        location_data = data["location"][0]
        await cache_manager.save_cache(cache_key, location_data, subdirectory="weather")
        return location_data
    return None

def parse_date_param(param: str) -> tuple[str, Optional[datetime.date], Optional[datetime.date]]:
    today = datetime.date.today()
    if '-' in param:
        try:
            start_day, end_day = map(int, param.split('-'))
            start_date = today.replace(day=start_day)
            end_date = today.replace(day=end_day)
            if start_date < today: start_date = start_date.replace(month=start_date.month + 1) if today.month < 12 else start_date.replace(year=today.year + 1, month=1)
            if end_date < start_date: end_date = end_date.replace(month=end_date.month + 1) if today.month < 12 else end_date.replace(year=today.year + 1, month=1)
            if 0 <= (end_date - today).days <= 30: return 'date_range', start_date, end_date
            return 'out_of_range', None, None
        except (ValueError, IndexError): pass
    
    if param.startswith('day') and len(param) > 3 and param[3:].isdigit():
        try:
            day = int(param[3:])
            target_date = today.replace(day=day)
            if target_date < today: target_date = target_date.replace(month=target_date.month + 1) if today.month < 12 else target_date.replace(year=today.year + 1, month=1)
            if 0 <= (target_date - today).days <= 30: return 'specific_date', target_date, None
            return 'out_of_range', None, None
        except ValueError: pass

    if param.isdigit():
        try:
            days = int(param)
            if 1 <= days <= 30: return 'multiple_days', today, today + datetime.timedelta(days=days - 1)
            return 'out_of_range', None, None
        except ValueError: pass

    return 'invalid', None, None

def format_daily_weather(daily_data: list[dict]) -> str:
    """
    将每日天气数据格式化为详细的、类似代码1的树状结构。
    使用 MarkdownV2 进行格式化。
    """
    result_lines = []
    for day in daily_data:
        try:
            # --- 安全地获取并转义所有需要的数据 ---
            date_obj = datetime.datetime.strptime(day.get("fxDate", ""), "%Y-%m-%d")
            date_str = date_obj.strftime("%m-%d")
            
            moon_phase = day.get('moonPhase', '')
            temp_min = day.get('tempMin', 'N/A')
            temp_max = day.get('tempMax', 'N/A')
            
            day_icon = WEATHER_ICONS.get(day.get("iconDay"), "❓")
            text_day = day.get('textDay', 'N/A')
            wind_dir_day = day.get('windDirDay', 'N/A')
            wind_scale_day = day.get('windScaleDay', 'N/A')
            
            night_icon = WEATHER_ICONS.get(day.get("iconNight"), "❓")
            text_night = day.get('textNight', 'N/A')
            wind_dir_night = day.get('windDirNight', 'N/A')
            wind_scale_night = day.get('windScaleNight', 'N/A')
            
            humidity = day.get('humidity', 'N/A')
            precip = day.get('precip', 'N/A')
            sunrise = day.get('sunrise', 'N/A')
            sunset = day.get('sunset', 'N/A')
            vis = day.get('vis', 'N/A')
            uv_index = day.get('uvIndex', 'N/A')

            # --- 构建格式化字符串列表 ---
            # 注意：MarkdownV2 需要对 | ~ 等特殊字符进行转义
            daily_info = [
                f"🗓 *{date_str} {moon_phase}*",
                f"├─ 温度: {temp_min}~{temp_max}°C",
                f"├─ 日间: {day_icon} {text_day}",
                f"│   └─ {wind_dir_day} {wind_scale_day}级",
                f"├─ 夜间: {night_icon} {text_night}",
                f"│   └─ {wind_dir_night} {wind_scale_night}级",
                f"└─ 详情:",
                f"    💧 湿度: {humidity}% | ☔️ 降水: {precip}mm",
                f"    🌅 日出: {sunrise} | 🌄 日落: {sunset}",
                f"    👁️ 能见度: {vis}km | ☀️ UV指数: {uv_index}"
            ]
            
            result_lines.append("\n".join(daily_info))

        except Exception as e:
            logging.error(f"格式化单日天气数据时出错: {e}")
            continue
            
    # 每天的预报之间用两个换行符隔开，以获得更好的视觉间距
    return "\n\n".join(result_lines)

def format_hourly_weather(hourly_data: list[dict]) -> str:
    """
    将逐小时天气数据格式化为详细的、类似代码1的多行卡片结构。
    """
    result_lines = []
    for hour in hourly_data:
        try:
            # --- 安全地获取并转义所有需要的数据 ---
            time_str = escape_markdown(datetime.datetime.fromisoformat(hour.get("fxTime").replace('Z', '+00:00')).strftime('%H:%M'), version=2)
            temp = escape_markdown(hour.get('temp', 'N/A'), version=2)
            icon = WEATHER_ICONS.get(hour.get("icon"), "❓")
            text = escape_markdown(hour.get('text', 'N/A'), version=2)
            wind_dir = hour.get('windDir', 'N/A')
            wind_scale = hour.get('windScale', 'N/A')
            humidity = escape_markdown(hour.get('humidity', 'N/A'), version=2)
            # 和风天气API返回的pop是字符串"0"~"100"，直接用即可
            pop = escape_markdown(hour.get('pop', 'N/A'), version=2) 
            
            # --- 构建单个小时的格式化文本 ---
            hourly_info = [
                f"⏰ {time_str}",
                f"🌡️ {temp}°C {icon} {text}",
                f"💨 {wind_dir} {wind_scale}级",
                f"💧 湿度: {humidity}% | ☔️ 降水概率: {pop}%",
                "━━━━━━━━━━━━━━━━━━━━" # 分隔线
            ]
            result_lines.append("\n".join(hourly_info))

        except Exception as e:
            # 如果单条数据处理失败，记录日志并跳过，不影响其他数据显示
            logging.error(f"格式化单小时天气数据时出错: {e}")
            continue
            
    # 将每个小时的文本块用换行符连接起来
    return "\n".join(result_lines)

def format_minutely_rainfall(rainfall_data: dict) -> str:
    """
    将分钟级降水数据格式化为包含摘要和详细时间点的列表。
    """
    result = []

    # 1. 添加摘要和主分隔线
    summary = rainfall_data.get('summary', '暂无降水信息')
    result.append(f"📝 {summary}")
    result.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 2. 遍历每个时间点的数据并格式化
    for minute in rainfall_data.get("minutely", []):
        try:
            time_str = datetime.datetime.fromisoformat(minute.get("fxTime").replace('Z', '+00:00')).strftime('%H:%M')
            precip = minute.get('precip', 'N/A')
            
            precip_type_text = "雨" if minute.get("type") == "rain" else "雪"
            precip_type_icon = "🌧️" if minute.get("type") == "rain" else "❄️"
            
            # 构建单个时间点的信息块
            minute_info = (
                f"\n⏰ {time_str}\n"
                # ↓↓↓ 修正了这一行，为括号添加了转义符 \ ↓↓↓
                f"💧 预计降水: {precip}mm ({precip_type_icon} {precip_type_text})\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
            result.append(minute_info)

        except Exception as e:
            logging.error(f"格式化分钟级降水数据时出错: {e}")
            continue

    return "\n".join(result)

def format_indices_data(indices_data: dict) -> str:
    """
    将生活指数数据格式化为详细的、按日期和类别分组的结构。
    """
    result = []
    grouped_by_date = {}

    # 1. 首先按日期将所有指数分组
    for index in indices_data.get("daily", []):
        date = index.get("date")
        if date not in grouped_by_date:
            grouped_by_date[date] = []
        grouped_by_date[date].append(index)
    
    # 2. 遍历每个日期，生成该日期的指数报告
    for date, indices in sorted(grouped_by_date.items()):
        date_str = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%m-%d")
        result.append(f"\n📅 *{date_str} 天气生活指数*")

        # 3. 遍历预设的分类，在当前日期的指数中查找并显示
        for category_name, type_ids in CATEGORIES.items():
            # 筛选出属于当前分类的指数
            category_indices = [idx for idx in indices if idx.get("type") in type_ids]
            
            if category_indices:
                result.append(f"\n*【{escape_markdown(category_name, version=2)}】*")
                for index in category_indices:
                    index_type = index.get("type")
                    emoji = INDICES_EMOJI.get(index_type, "ℹ️") # 获取对应的Emoji
                    name = index.get('name', 'N/A')
                    level = index.get('category', 'N/A')
                    text = index.get('text', 'N/A')
                    
                    # 构建最终的图文并茂格式
                    result.append(f"{emoji} *{name}*: {level}")
                    result.append(f"    ↳ {text}")

    return "\n".join(result)

def format_air_quality(air_data: dict) -> str:
    aqi_data = air_data.get('now', {})
    aqi = aqi_data.get('aqi', 'N/A')
    category = aqi_data.get('category', 'N/A')
    primary = aqi_data.get('primary', 'NA')
    lines = [
        f"\n🌫️ *空气质量*：{aqi} ({category})",
        f"🔍 主要污染物：{primary}",
        f"🌬️ PM2.5：{aqi_data.get('pm2p5', 'N/A')}μg/m³ | PM10：{aqi_data.get('pm10', 'N/A')}μg/m³",
        f"🌡️ SO₂：{aqi_data.get('so2', 'N/A')}μg/m³ | NO₂：{aqi_data.get('no2', 'N/A')}μg/m³",
        f"💨 CO：{aqi_data.get('co', 'N/A')}mg/m³ | O₃：{aqi_data.get('o3', 'N/A')}μg/m³"
    ]
    return "\n".join(lines)

def format_realtime_weather(realtime_data: dict, location_name: str) -> str:
    now = realtime_data.get("now", {})
    icon = WEATHER_ICONS.get(now.get("icon"), "❓")
    obs_time_str = "N/A"
    try:
        obs_time_utc = datetime.datetime.fromisoformat(now.get('obsTime', '').replace('Z', '+00:00'))
        obs_time_local = obs_time_utc.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        obs_time_str = obs_time_local.strftime('%Y-%m-%d %H:%M')
    except: pass
    lines = [
        f"🌍 *{location_name}* 的实时天气：\n",
        f"🕐 观测时间：{obs_time_str}",
        f"🌤️ 天气：{icon} {now.get('text', 'N/A')}",
        f"🌡️ 温度：{now.get('temp', 'N/A')}°C",
        f"🌡️ 体感温度：{now.get('feelsLike', 'N/A')}°C",
        f"💨 {now.get('windDir', 'N/A')} {now.get('windScale', 'N/A')}级 ({now.get('windSpeed', 'N/A')}km/h)",
        f"💧 相对湿度：{now.get('humidity', 'N/A')}%",
        f"☔️ 降水量：{now.get('precip', 'N/A')}mm",
        f"👀 能见度：{now.get('vis', 'N/A')}km",
        f"☁️ 云量：{now.get('cloud', 'N/A')}%",
        f"🌫️ 露点温度：{now.get('dew', 'N/A')}°C",
        f"📈 气压：{now.get('pressure', 'N/A')}hPa"
    ]
    return "\n".join(lines)

HELP_TEXT = (
    "*天气查询帮助* `(和风天气)`\n\n"
    "`/tq [城市] [参数]`\n\n"
    "**参数说明:**\n"
    "• `(无)`: 当天天气和空气质量\n"
    "• `数字(1-30)`: 未来指定天数天气\n"
    "• `dayXX`: 指定日期天气\n"
    "• `XX-YY`: 指定日期范围天气\n"
    "• `[1-168]h`: 逐小时天气\n"
    "• `降水`: 分钟级降水\n"
    "• `指数`/`指数3`: 生活指数\n\n"
    "**示例:** `/tq 北京`, `/tq 上海 3`, `/tq 广州 24h`"
)

async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat: return
    await delete_user_command(context, update.effective_chat.id, update.message.message_id)

    if not context.args:
        await send_message_with_auto_delete(context, update.effective_chat.id, HELP_TEXT, parse_mode=ParseMode.MARKDOWN_V2)
        return

    location = context.args[0]
    param = context.args[1].lower() if len(context.args) > 1 else None
    
    safe_location = escape_markdown(location, version=2)
    message = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🔍 正在查询 *{safe_location}* 的天气\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)

    location_data = await get_location_id(location)
    if not location_data:
        await message.edit_text(f"❌ 找不到城市 *{safe_location}*，请检查拼写。", parse_mode=ParseMode.MARKDOWN_V2)
        return
    
    location_id = location_data['id']
    location_name = f"{location_data['name']}, {location_data['adm1']}"
    safe_location_name = escape_markdown(location_name, version=2)

    result_text = ""
    
    if not param:
        realtime_data = await _get_api_response("weather/now", {"location": location_id})
        air_data = await _get_api_response("air/now", {"location": location_id})
        
        if realtime_data:
            result_text = format_realtime_weather(realtime_data, location_name)
        else:
            result_text = f"❌ 获取 *{safe_location_name}* 实时天气失败。\n"
        
        if air_data:
            result_text += format_air_quality(air_data)
        else:
            result_text += f"\n*空气质量*: 获取失败"

    elif param.endswith('h') and param[:-1].isdigit() and 1 <= int(param[:-1]) <= 168:
        hours = int(param[:-1])
        endpoint = "weather/24h" if hours <= 24 else "weather/72h" if hours <= 72 else "weather/168h"
        data = await _get_api_response(endpoint, {"location": location_id})
        if data and data.get("hourly"):
            result_text = f"🌍 *{safe_location_name}* 未来 {hours} 小时天气预报：\n\n"
            result_text += format_hourly_weather(data["hourly"][:hours])
        else:
            result_text = f"❌ 获取 *{safe_location_name}* 的逐小时天气失败。"

    elif param == "降水":
        coords = f"{location_data['lon']},{location_data['lat']}"
        data = await _get_api_response("minutely/5m", {"location": coords})
        if data:
            result_text = f"🌍 *{safe_location_name}* 未来2小时分钟级降水预报：\n"
            result_text += format_minutely_rainfall(data)
        else:
            result_text = f"❌ 获取 *{safe_location_name}* 的分钟级降水失败。"
            
    elif param.startswith("指数"):
        days_param = "3d" if param.endswith("3") else "1d"
        data = await _get_api_response(f"indices/{days_param}", {"location": location_id, "type": "0"})
        if data:
            result_text = f"🌍 *{safe_location_name}* 的天气指数预报："
            result_text += format_indices_data(data)
        else:
            result_text = f"❌ 获取 *{safe_location_name}* 的生活指数失败。"
    
    else:
        query_type, date1, date2 = parse_date_param(param)
        if query_type == 'invalid':
            result_text = f"❌ 无效的参数: `{escape_markdown(param, version=2)}`。"
        elif query_type == 'out_of_range':
            result_text = "❌ 只支持查询未来30天内的天气预报。"
        else:
            days_needed = (date2 - datetime.date.today()).days + 1 if date2 else (date1 - datetime.date.today()).days + 1
            endpoint = "weather/3d" if days_needed <= 3 else "weather/7d" if days_needed <=7 else "weather/15d" if days_needed <= 15 else "weather/30d"
            data = await _get_api_response(endpoint, {"location": location_id})
            if data and data.get("daily"):
                if query_type == 'specific_date':
                    result_text = f"🌍 *{safe_location_name}* {escape_markdown(date1.strftime('%m月%d日'), version=2)} 天气预报：\n\n"
                    daily_data = [d for d in data["daily"] if d["fxDate"] == date1.strftime("%Y-%m-%d")]
                else:
                    start_str = date1.strftime('%m月%d日')
                    end_str = date2.strftime('%m月%d日')
                    title = f"未来 {(date2 - date1).days + 1} 天" if query_type == 'multiple_days' else f"{start_str}到{end_str}"
                    result_text = f"🌍 *{safe_location_name}* {escape_markdown(title, version=2)}天气预报：\n\n"
                    daily_data = [d for d in data["daily"] if date1 <= datetime.datetime.strptime(d["fxDate"], "%Y-%m-%d").date() <= date2]
                result_text += format_daily_weather(daily_data)
            else:
                result_text = f"\n❌ 获取 *{safe_location_name}* 的天气信息失败。"

    await message.edit_text(
    foldable_text_with_markdown_v2(result_text), # <--- 在这里把它包起来！
    parse_mode=ParseMode.MARKDOWN_V2, 
    disable_web_page_preview=True
)

    # 调度删除机器人回复消息，使用配置的延迟时间
    from utils.message_manager import _schedule_deletion
    config = get_config()
    await _schedule_deletion(context, update.effective_chat.id, message.message_id, config.auto_delete_delay)

command_factory.register_command(
    "tq",
    weather_command,
    permission=Permission.USER,
    description="查询天气预报，支持多日、小时、指数等"
)
