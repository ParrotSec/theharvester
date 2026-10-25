from typing import Any

from theHarvester.discovery.constants import MissingKey
from theHarvester.lib.core import AsyncFetcher, Core


class SearchDymo:
    """Dymo API data verifier source.

    Dymo provides a verification endpoint that takes a domain (and optionally
    an email/url/ip/phone) and returns metadata such as MX presence, fraud
    flags, free-subdomain detection, ``didYouMean`` suggestions and the
    canonical domain. theHarvester does not call it for bulk discovery; it
    treats it as a low-volume enrichment pass that can confirm the target
    domain and surface near-miss suggestions as additional host candidates.

    API docs: https://docs.tpeoficial.com/docs/dymo-api/private/data-verifier
    """

    VERIFY_URL = 'https://api.tpeoficial.com/v1/private/secure/verify'

    def __init__(self, word) -> None:
        self.word = word
        self.totalhosts: set[str] = set()
        self.results: dict[str, Any] = {}
        self.key = Core.dymo_key()
        if self.key is None:
            raise MissingKey('dymo')
        self.proxy = False

    def _headers(self) -> dict[str, str]:
        return {
            'User-Agent': Core.get_user_agent(),
            'Authorization': f'Bearer {self.key}',
            'Content-Type': 'application/json',
        }

    async def do_search(self) -> None:
        payload = {
            'domain': self.word,
            'url': f'https://{self.word}',
        }
        response = await AsyncFetcher.post_fetch(
            self.VERIFY_URL,
            headers=self._headers(),
            data=payload,
            json=True,
            proxy=self.proxy,
        )
        if not isinstance(response, dict):
            return

        self.results = response

        domain_block = response.get('domain') if isinstance(response.get('domain'), dict) else {}
        url_block = response.get('url') if isinstance(response.get('url'), dict) else {}

        for block in (domain_block, url_block):
            candidate = block.get('domain') if isinstance(block, dict) else None
            if isinstance(candidate, str) and self.word in candidate:
                self.totalhosts.add(candidate)

            suggestion = block.get('didYouMean') if isinstance(block, dict) else None
            if isinstance(suggestion, str) and self.word in suggestion:
                self.totalhosts.add(suggestion)

    async def get_hostnames(self) -> set:
        return self.totalhosts

    async def get_results(self) -> dict[str, Any]:
        return self.results

    async def process(self, proxy: bool = False) -> None:
        self.proxy = proxy
        await self.do_search()
