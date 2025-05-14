import clickhouse_connect
from abc import ABC, abstractmethod
import typing


class StatsDBQueries(ABC):
    @abstractmethod
    def count_for_this_session(self, session_id: str) -> str:
        pass

    @abstractmethod
    def count_single_country(self, country_name: str, last_hour: int):
        pass

    @abstractmethod
    def count_by_country(self):
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

    def count_single_country(self, country_name: str, last_hour):
        return self.client.command(
            "SELECT COUNT(*) as total_count,"
            " SUM(if(timestamp > {last_hour:DateTime64(6,'UTC')}, 1, 0)) as hour_count"
            " FROM {table:Identifier}"
            " WHERE country_name = {country_name:String}"
            " AND action == 'PressButton'",
            parameters={
                "country_name": country_name,
                "table": self.table_name,
                "last_hour": last_hour,
            },
        )

    def count_by_country(self):
        """Fetches the list of all countries and their count. Excludes countries that have no representation"""
        return self.client.query(
            "SELECT country_name as country, COUNT(*) as click_count"
            " FROM {table:Identifier}"
            " WHERE action = 'PressButton'"
            " GROUP BY country"
            " ORDER BY click_count DESC;",
            parameters={
                "table": self.table_name,
            },
        )
