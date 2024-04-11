import asyncio
import json
import pprint

import aiohttp
import httpx


class Parser:
    # Урезать функционал, сделать базовым классом для FootballParser, CSParser
    root_url = 'https://football.esportsbattle.com/api'
    status_codes_endpoint = '/statuses'
    tournament_endpoint = '/tournaments'
    tournament_matches_endpoint = '/tournaments/{}/matches'

    def __init__(self, config):
        self.config = config

    async def handle_data(self, data: dict | list) -> None:
        pprint.pprint(data)

    async def get_data_once(self) -> aiohttp.client.ClientResponse:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://football.esportsbattle.com/api/tournaments?dateFrom=2024/04/11+03:00') as req:
                return req

    async def run_infinite_loop(self) -> None:
        while True:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        'https://football.esportsbattle.com/api/tournaments?dateFrom=2024/04/11+03:00') as resp:
                    if resp.status == 200:
                        resp = await resp.json()
                        await self.handle_data(resp)
            await asyncio.sleep(60)

    async def get_status_codes(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    'https://football.esportsbattle.com/api/statuses') as resp:
                if resp.status == 200:
                    return await resp.json()


class FootballParser(Parser):
    pass


class CSParser(Parser):
    pass


def load_config() -> dict | list:
    with open('config.json', 'r') as f:
        return json.load(f)


async def main() -> None:
    config = load_config()
    await Parser(config=config).run_infinite_loop()


if __name__ == '__main__':
    asyncio.run(main())
