import asyncio
import collections
import datetime
import json
import logging
import os
import platform
import time
import traceback

import aiohttp
import aiohttp.client_exceptions
import psycopg_pool

from dotenv import load_dotenv

load_dotenv()


def parse_time_logger(func):
    async def wrapper(*args, **kwargs):
        start = time.time()
        res = await func(*args, **kwargs)
        end = time.time()
        logging.info(f"Parsed {args[2]}: took {round(end - start, 1)} sec.")
        return res

    return wrapper


class DBGateway:
    def __init__(self) -> None:
        conn_string = (
            f'host={os.getenv("POSTGRES_HOST")} port=5432 '
            f'dbname=postgres user=postgres password={os.getenv("POSTGRES_PASSWORD")}'
        )
        self.pg_pool = psycopg_pool.AsyncConnectionPool(conninfo=conn_string, open=True)

    async def create_table(self, name: str) -> None:
        async with self.pg_pool.connection() as conn:
            await conn.execute(
                f"""
                create table if not exists public.{name}
                    (
                        sport_name       varchar(30),
                        tournament_name  varchar(100),
                        match_start_time timestamp,
                        tournament_start_time timestamp,
                        team1_name       varchar(50),
                        team2_name       varchar(50),
                        unique (sport_name, tournament_name, match_start_time, team1_name, team2_name)
                    );
                """
            )

    async def insert_to_base(self, name: str, data: list) -> None:
        query = f"""
        INSERT INTO {name}(sport_name, tournament_name, match_start_time, tournament_start_time, team1_name, team2_name)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """

        async with self.pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                if data:
                    await cur.executemany(query, data)
                await cur.execute(
                    f"DELETE FROM {name} WHERE match_start_time < CURRENT_TIMESTAMP"
                )

    async def fetch(self, query: str, data: list | tuple | None = None) -> list:
        async with self.pg_pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, data)
                return await cur.fetchall()


class Parser:
    @staticmethod
    async def do_request(base_url: str, endpoint: str, req_params: dict | None = None) -> dict | list:

        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,"
            "*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 YaBrowser/24.1.0.0 Safari/537.36",
        }
        while True:
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(
                        base_url + endpoint, params=req_params
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        else:
                            logging.error(
                                f"Unable to fetch data from {endpoint} endpoint, code {resp.status}"
                            )
            except aiohttp.client_exceptions.ClientError:
                logging.critical(traceback.format_exc())
            await asyncio.sleep(1)

    @staticmethod
    def format_for_base(prefix: str, data: list) -> list:
        formatted_data = []
        for tournament in data:
            print(tournament)
            for match in tournament["upc_matches"]:
                formatted_data.append(
                    [
                        prefix,
                        tournament["token_international"],
                        datetime.datetime.strptime(match["date"], "%Y-%m-%dT%H:%M:%SZ"),
                        datetime.datetime.strptime(
                            tournament["date" if prefix == "cs2" else "start_date"],
                            "%Y-%m-%dT%H:%M:%SZ",
                        ),
                        match["participant1"]["team"]["token_international"],
                        match["participant2"]["team"]["token_international"],
                    ]
                )
        return formatted_data


class EsportsBattleParser(Parser):
    db_table_name = "esb_matches"
    available_sports = ["football", "cs2", "hockey", "basketball"]
    root_api_url_template = "https://{}.esportsbattle.com/api"
    status_codes_endpoint = "/statuses"
    tournaments_endpoint = "/tournaments"
    tournament_matches_endpoint_template = tournaments_endpoint + "/{}/matches"
    nearest_matches_endpoint = tournaments_endpoint + "/nearest-matches"

    def __init__(self, config: dict, db: DBGateway) -> None:
        self.config = config
        self.db = db
        self.most_far_tournaments_datetime_dict: dict = {}

    @staticmethod
    def reduce_event_list(acceptable_ids: list, event_list: list) -> list:
        for event in event_list[:]:
            if event["status_id"] not in acceptable_ids:
                event_list.remove(event)
        return event_list

    async def set_most_far_tournament_datetime_by_sport(self, prefix: str) -> None:
        res = await self.db.fetch(
            f"""
            SELECT max(tournament_start_time)
            FROM {self.db_table_name} 
            WHERE sport_name = %s
            """,
            (prefix,),
        )
        if res and res[0][0]:
            self.most_far_tournaments_datetime_dict[prefix] = res[0][0]

    async def get_valid_status_codes(self, url: str) -> dict[str, list]:
        acceptable_ids = collections.defaultdict(list)
        codes_response: dict = await self.do_request(url, self.status_codes_endpoint)

        for event_type, codes_list in codes_response.items():
            for code in codes_list:
                if code["token_international"] in self.config.get(
                    f"filter_status_code_{event_type}", []
                ):
                    acceptable_ids[event_type].append(code["id"])
        return acceptable_ids

    async def get_filtered_tournaments(
        self, url: str, prefix: str, status_codes: list, page: int = 1
    ) -> list:
        filtered_tournaments_list = []
        date_from = datetime.datetime.now() - datetime.timedelta(days=1)
        date_to = datetime.datetime.now() + datetime.timedelta(
            days=self.config["seek_forward_days"]
        )
        params = {
            "page": page,
            "dateFrom": max(
                self.most_far_tournaments_datetime_dict.get(prefix, date_from),
                date_from,
            ).strftime("%Y/%m/%d %H:%M"),
            "dateTo": date_to.strftime("%Y/%m/%d %H:%M"),
        }

        tournaments_data: dict = await self.do_request(
            url, self.tournaments_endpoint, params
        )
        filtered_tournaments_list.extend(tournaments_data["tournaments"])

        if page == 1:
            parse_tasks = []
            for next_page in range(2, tournaments_data["totalPages"] + 1):
                parse_tasks.append(
                    asyncio.create_task(
                        self.get_filtered_tournaments(
                            url, prefix, status_codes, next_page
                        )
                    )
                )
            parse_tasks_res = await asyncio.gather(*parse_tasks)

            filtered_tournaments_list.extend(
                [
                    tournament
                    for tournaments_chunk in parse_tasks_res
                    for tournament in self.reduce_event_list(
                        status_codes, tournaments_chunk
                    )
                ]
            )
            if filtered_tournaments_list:
                date_key = "date" if prefix == "cs2" else "start_date"
                filtered_tournaments_list.sort(key=lambda x: x[date_key], reverse=True)
                self.most_far_tournaments_datetime_dict[prefix] = (
                    datetime.datetime.strptime(
                        filtered_tournaments_list[0][date_key], "%Y-%m-%dT%H:%M:%SZ"
                    )
                )
        return filtered_tournaments_list

    async def enrich_tournaments_with_matches(self, url: str, tournaments_list: list, status_codes: list) -> list:
        parse_tasks = []
        for tournament in tournaments_list:
            parse_tasks.append(
                asyncio.create_task(
                    self.do_request(
                        url,
                        self.tournament_matches_endpoint_template.format(
                            tournament["id"]
                        ),
                    )
                )
            )
        parse_tasks_res = await asyncio.gather(*parse_tasks)

        for q, tournament in enumerate(parse_tasks_res):
            tournaments_list[q]["upc_matches"] = self.reduce_event_list(
                status_codes, tournament
            )
        return tournaments_list

    @parse_time_logger
    async def parse_once(self, target_url: str, prefix: str, status_codes_dict: dict) -> list:
        tournaments = await self.get_filtered_tournaments(
            target_url, prefix, status_codes_dict["tournament"]
        )
        upcoming_matches = await self.enrich_tournaments_with_matches(
            target_url, tournaments, status_codes_dict["match"]
        )
        return upcoming_matches

    async def parse_in_loop(self, prefix: str) -> None:
        target_url = self.root_api_url_template.format(prefix)
        status_codes = await self.get_valid_status_codes(target_url)
        await self.set_most_far_tournament_datetime_by_sport(prefix)

        while True:
            upcoming_matches = await self.parse_once(target_url, prefix, status_codes)

            formatted_data = self.format_for_base(prefix, upcoming_matches)
            await self.db.insert_to_base(self.db_table_name, formatted_data)

            await asyncio.sleep(self.config.get("parse_interval_sec", 60))

    async def start_parse(self) -> None:
        await self.db.create_table(self.db_table_name)
        async with asyncio.TaskGroup() as gr:
            for sport_name in self.config.get("sports_to_parse", []):
                if sport_name in self.available_sports:
                    logging.info(f"Discovered sport: {sport_name}")
                    gr.create_task(self.parse_in_loop(sport_name))


def load_config() -> dict:
    with open("config.json", "r") as f:
        return json.load(f)


async def main() -> None:
    config = load_config()
    if not os.path.exists("log"):
        os.mkdir("log")

    logging.basicConfig(
        level=config.get("log_level", 1),
        filename="log/py_log.log",
        filemode="w",
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    db_gateway = DBGateway()
    await EsportsBattleParser(config=config, db=db_gateway).start_parse()


if __name__ == "__main__":
    if platform.system() == "Windows":
        from asyncio import WindowsSelectorEventLoopPolicy

        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
