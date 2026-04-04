"""
App Store 网页搜索 API 封装

负责 App Store 网页搜索和应用详情页面获取
"""

import logging
import re
from typing import Dict, Optional

import httpx
from bs4 import BeautifulSoup

from utils.constants import HTTP_TIMEOUT_MEDIUM

from .constants import MINIMAL_HEADERS, WEB_SEARCH_LIMIT

logger = logging.getLogger(__name__)

# iTunes Lookup API 批量查询上限
_LOOKUP_BATCH_SIZE = 50


async def _itunes_lookup(app_ids: list[int], country: str = "us") -> dict[int, dict]:
    """批量查询 iTunes Lookup API 获取应用元数据（图标、真实名称、开发者等）

    Args:
        app_ids: App ID 列表
        country: 国家代码

    Returns:
        {app_id: {trackName, artistName, artworkUrl100, ...}} 映射
    """
    if not app_ids:
        return {}

    ids_str = ",".join(str(aid) for aid in app_ids[:_LOOKUP_BATCH_SIZE])
    url = "https://itunes.apple.com/lookup"
    params = {"id": ids_str, "country": country}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=HTTP_TIMEOUT_MEDIUM)
            resp.raise_for_status()
            data = resp.json()

        result = {}
        for item in data.get("results", []):
            track_id = item.get("trackId")
            if track_id:
                result[track_id] = item
        return result
    except Exception as e:
        logger.warning(f"iTunes Lookup API 失败: {type(e).__name__}: {e}")
        return {}


class AppStoreWebAPI:
    """App Store 网页 API 客户端"""

    @staticmethod
    async def fetch_app_page(app_id: int, country_code: str) -> Optional[str]:
        """
        获取应用详情页面的 HTML 内容

        Args:
            app_id: App ID
            country_code: 国家代码

        Returns:
            HTML 内容，失败返回 None
        """
        url = f"https://apps.apple.com/{country_code.lower()}/app/id{app_id}"

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                logger.info(f"获取应用页面: {url}")
                response = await client.get(
                    url, headers=MINIMAL_HEADERS, timeout=HTTP_TIMEOUT_MEDIUM
                )
                response.raise_for_status()
                return response.text

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"App 'id{app_id}' 在 {country_code} 未上架 (404)")
            else:
                logger.error(f"HTTP 错误 {e.response.status_code}: {url}")
            return None

        except httpx.RequestError as e:
            logger.error(f"网络请求失败: {url} - {e}")
            return None

        except Exception as e:
            logger.error(f"未知错误: {url} - {e}")
            return None

    @staticmethod
    async def search_apps_by_web(
        query: str,
        country: str = "us",
        platform: str = "iphone",
        limit: int = WEB_SEARCH_LIMIT,
    ) -> Dict:
        """
        使用 App Store 网页搜索应用，再通过 iTunes Lookup API 补齐元数据

        流程：
        1. 网页搜索提取 App ID 列表（覆盖率高于 iTunes Search API）
        2. 批量调用 iTunes Lookup API 获取图标、真实名称、开发者等

        Args:
            query: 搜索关键词
            country: 国家代码 (默认 us)
            platform: 平台类型 (iphone, ipad, mac, tv, watch, vision)
            limit: 返回结果数量

        Returns:
            包含搜索结果的字典
        """
        url = f"https://apps.apple.com/{country.lower()}/{platform}/search"
        params = {"term": query}

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                logger.info(
                    f"网页搜索: query='{query}', country={country}, platform={platform}"
                )

                response = await client.get(
                    url,
                    params=params,
                    headers=MINIMAL_HEADERS,
                    timeout=HTTP_TIMEOUT_MEDIUM,
                )
                response.raise_for_status()

                html_content = response.text
                soup = BeautifulSoup(html_content, "lxml")

                # 从 HTML 提取 App ID 列表
                app_ids = []
                seen_ids = set()

                app_links = soup.select('a[href*="/app/"]')

                for link in app_links:
                    href = link.get("href", "")
                    match = re.search(r"/app/[^/]+/id(\d+)", href)
                    if not match:
                        match = re.search(r"/app/id(\d+)", href)
                        if not match:
                            continue

                    app_id = int(match.group(1))
                    if app_id in seen_ids:
                        continue
                    seen_ids.add(app_id)
                    app_ids.append(app_id)

                    if len(app_ids) >= limit:
                        break

                logger.info(f"网页搜索提取到 {len(app_ids)} 个 App ID")

                if not app_ids:
                    return {
                        "results": [],
                        "query": query,
                        "country": country,
                        "platform": platform,
                        "source": "web_search",
                    }

            # 批量调用 iTunes Lookup API 补齐元数据
            lookup_data = await _itunes_lookup(app_ids, country)
            logger.info(f"iTunes Lookup 返回 {len(lookup_data)} 个结果")

            results = []
            for app_id in app_ids:
                meta = lookup_data.get(app_id)
                if meta:
                    # Lookup API 返回了完整元数据
                    results.append(
                        {
                            "trackId": app_id,
                            "trackName": meta.get("trackName", ""),
                            "kind": meta.get("kind", "software"),
                            "artistName": meta.get("artistName", ""),
                            "artworkUrl100": meta.get("artworkUrl100", ""),
                            "trackViewUrl": meta.get("trackViewUrl", ""),
                            "formattedPrice": meta.get("formattedPrice", ""),
                            "source": "web_search+lookup",
                        }
                    )
                else:
                    # Lookup 未返回，用 App ID 构建基本信息
                    results.append(
                        {
                            "trackId": app_id,
                            "trackName": f"App {app_id}",
                            "kind": "software",
                            "artistName": "",
                            "artworkUrl100": "",
                            "trackViewUrl": f"https://apps.apple.com/{country}/app/id{app_id}",
                            "source": "web_search",
                        }
                    )

            logger.info(f"网页搜索完成: {len(results)} 个应用（其中 {len(lookup_data)} 个有完整元数据）")

            return {
                "results": results,
                "query": query,
                "country": country,
                "platform": platform,
                "source": "web_search",
            }

        except Exception as e:
            logger.error(f"网页搜索失败: {type(e).__name__}: {e}")
            return {
                "results": [],
                "query": query,
                "country": country,
                "platform": platform,
                "source": "web_search",
                "error": str(e),
            }
