import asyncio
import time
import logging
import httpx
from typing import Optional

from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

class RateConverter:
    def __init__(self, api_keys: list, cache_manager: CacheManager, cache_duration_seconds: int = 3600):
        if not api_keys:
            raise ValueError("API keys list cannot be empty.")
        self.api_keys = api_keys
        self.cache_manager = cache_manager
        self.current_key_index = 0
        self.rates: dict = {}
        self.rates_timestamp: int = 0
        self.cache_duration = cache_duration_seconds
        self._lock = asyncio.Lock()

    def _get_next_api_key(self) -> str:
        """Rotates and returns the next available API key."""
        key = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return key

    async def _fetch_rates(self) -> Optional[dict]:
        """Fetches the latest exchange rates from the API."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        for _ in self.api_keys:
            api_key = self._get_next_api_key()
            url = f"https://openexchangerates.org/api/latest.json?app_id={api_key}"
            try:
                async with httpx.AsyncClient(headers=headers) as client:
                    response = await client.get(url, timeout=15)
                    response.raise_for_status()
                    data = response.json()
                    if "rates" in data and "timestamp" in data:
                        logger.info(f"Successfully fetched rates using API key ending in ...{api_key[-4:]}")
                        return data
            except httpx.HTTPStatusError as e:
                logger.warning(f"API key ...{api_key[-4:]} failed with status {e.response.status_code}. Trying next key.")
            except httpx.RequestError as e:
                logger.error(f"Request failed for API key ...{api_key[-4:]}: {e}")
        
        logger.error("All API keys failed. Could not fetch exchange rates.")
        return None

    async def get_rates(self, force_refresh: bool = False):
        """
        Loads rates from cache or fetches them from the API.
        Uses a lock to prevent concurrent fetches.
        """
        # First, check without a lock for the most common case (in-memory cache is fresh)
        current_time = time.time()
        if not force_refresh and self.rates and (current_time - self.rates_timestamp < self.cache_duration):
            return

        async with self._lock:
            # Re-check condition inside the lock to handle race conditions
            if not force_refresh and self.rates and (current_time - self.rates_timestamp < self.cache_duration):
                return

            cache_key = "exchange_rates"
            cached_data = self.cache_manager.load_cache(cache_key, subdirectory="exchange_rates")
            
            if not force_refresh and cached_data:
                cached_timestamp = cached_data.get("timestamp", 0)
                if current_time - cached_timestamp < self.cache_duration:
                    self.rates = cached_data["rates"]
                    self.rates_timestamp = cached_timestamp
                    logger.info(f"Loaded exchange rates from file cache. Data is from {time.ctime(cached_timestamp)}.")
                    return

            logger.info("Cache is stale or refresh is forced. Fetching new rates from API.")
            api_data = await self._fetch_rates()
            if api_data:
                self.rates = api_data["rates"]
                self.rates_timestamp = api_data["timestamp"]
                self.cache_manager.save_cache(cache_key, api_data, subdirectory="exchange_rates")
                logger.info(f"Fetched and cached new rates from API. Data timestamp: {time.ctime(self.rates_timestamp)}")


    async def convert(self, amount: float, from_currency: str, to_currency: str) -> Optional[float]:
        """Converts an amount from one currency to another."""
        await self.get_rates() # Ensure rates are loaded

        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if not self.rates:
            logger.error("Cannot perform conversion, exchange rates are not available.")
            return None

        if from_currency not in self.rates or to_currency not in self.rates:
            logger.warning(f"Attempted conversion with unknown currency: {from_currency} or {to_currency}")
            return None

        # Conversion is done via the base currency (USD)
        from_rate = self.rates[from_currency]
        to_rate = self.rates[to_currency]

        converted_amount = (amount / from_rate) * to_rate
        return round(converted_amount, 2)

async def main():
    # Example usage
    from .config_manager import get_config
    config = get_config()
    
    # Assuming API keys are comma-separated in the config
    api_keys = config.exchange_rate_api_keys
    
    if not api_keys:
        logger.error("No API keys configured for RateConverter.")
        return

    cache_manager = CacheManager(config.cache_dir)
    converter = RateConverter(api_keys, cache_manager, config.rate_cache_duration)
    
    # Test basic functionality
    try:
        cny_amount = 100
        usd_amount = await converter.convert(cny_amount, "CNY", "USD")
        if usd_amount is not None:
            logger.info(f"Rate converter test: {cny_amount} CNY ≈ {usd_amount} USD")

        eur_amount = 50
        gbp_amount = await converter.convert(eur_amount, "EUR", "GBP")
        if gbp_amount is not None:
            logger.info(f"Rate converter test: {eur_amount} EUR ≈ {gbp_amount} GBP")
    except Exception as e:
        logger.error(f"Rate converter test failed: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
