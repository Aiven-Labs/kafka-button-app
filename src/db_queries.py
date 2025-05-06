import clickhouse_connect
from abc import ABC, abstractmethod
import typing


class StatsDBQueries(ABC):
    @abstractmethod
    def count_for_this_session(self, session_id: str) -> str:
        pass

    @abstractmethod
    def count_for_this_country_all_time(self, country_name: str):
        pass

    @abstractmethod
    def count_for_this_country_last_hour(self, country_name: str, last_hour: int):
        pass


class ClickhouseDBQueries(StatsDBQueries):
    def __init__(
        self,
        client: clickhouse_connect.driver.AsyncClient,
        table_name: str,
    ):

        self.client = client
        self.table_name = table_name

    def count_for_this_session(self, session_id: str):
        return self.client.command(
            "SELECT COUNT(*) FROM {table:Identifier}"
            " WHERE session_id = {session_id:String} AND action == 'PressButton'",
            parameters={"session_id": session_id, "table": self.table_name},
        )

    def count_for_this_country_all_time(self, country_name: str):
        return self.client.command(
            "SELECT COUNT(*) FROM {table:Identifier}"
            " WHERE country_name = {country_name:String} AND action == 'PressButton'",
            parameters={"country_name": country_name, "table": self.table_name},
        )

    def count_for_this_country_last_hour(self, country_name: str, last_hour: int):
        return self.client.command(
            "SELECT COUNT(*) FROM {table:Identifier}"
            " WHERE country_name = {country_name:String}"
            " AND action == 'PressButton'"
            " AND timestamp > {last_hour:DateTime64(6,'UTC')}",
            parameters={
                "country_name": country_name,
                "last_hour": last_hour,
                "table": self.table_name,
            },
        )
