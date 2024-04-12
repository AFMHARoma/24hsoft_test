import asyncio
import datetime
import json
import pprint

import aiohttp
import httpx
from abc import ABC, abstractmethod

import requests


class Parser:
    async def write_logs(self):
        pass


class EsportsBattleParser(Parser):
    status_codes_endpoint = '/statuses'
    tournament_endpoint = '/tournaments'
    tournament_matches_endpoint = tournament_endpoint + '/{}/matches'
    nearest_matches_endpoint = tournament_endpoint + '/nearest-matches'

    async def handle_data(self, data: dict | list) -> None:
        pprint.pprint(data)

    async def get_tournaments(self, url) -> None:
        dateFrom = datetime.datetime.utcnow().strftime('%Y/%m/%d %H:%M')
        params = {
            'page': 1,
            "dateFrom": dateFrom
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}{self.tournament_endpoint}", params=params) as resp:
                if resp.status == 200:
                    resp = await resp.json()
                    await self.handle_data(resp)

    def get_status_codes(self, url):
        resp = requests.get(f"{url}{self.status_codes_endpoint}")
        if resp.status_code == 200:
            return resp.json()


class FootballParser(EsportsBattleParser):
    root_url = 'https://football.esportsbattle.com/api'

    def __init__(self, config: dict) -> None:
        self.config = config
        self.status_codes = self.get_status_codes(self.root_url)

    async def parse_data_loop(self):
        await self.get_tournaments(self.root_url)
        await asyncio.sleep(self.config['parse_interval_sec'])


class CSParser(EsportsBattleParser):
    pass


def load_config() -> dict | list:
    with open('config.json', 'r') as f:
        return json.load(f)


async def main() -> None:
    config = load_config()
    await FootballParser(config).parse_data_loop()


if __name__ == '__main__':
    asyncio.run(main())
