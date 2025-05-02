import requests
import logging
from typing import Generator, Dict, Any

from configuration import Configuration

DEFAULT_PAGE_SIZE = 50
API_BASE_URL = "https://api.treez.io/v2.0/dispensary"


class TreezAPIClient:
    def __init__(self, config: Configuration, state: Dict[str, str]):
        self.config = config
        self.state = state
        self.base_url = f"{API_BASE_URL}/{config.authorization.dispensary_name}"
        self.client_id = config.authorization.client_id
        self.api_key = config.authorization.api_key
        self.access_token = self._authenticate()
        self.headers = {
            "authorization": self.access_token,
            "client_id": self.client_id
        }

    def _authenticate(self) -> str:
        url = f"{self.base_url}/config/api/gettokens"
        data = {
            "client_id": self.client_id,
            "apikey": self.api_key
        }
        logging.debug(f"Authenticating with Treez at: {url}")
        response = requests.post(url, data=data)
        response.raise_for_status()
        auth_data = response.json()

        access_token = auth_data.get("accessToken")
        if not access_token:
            raise RuntimeError(f"Auth failed: {auth_data}")
        return access_token

    def get_tickets_by_status(self) -> Generator[Dict[str, Any], None, None]:
        statuses = self.config.endpoints.order_status
        for status in statuses:
            page = 1
            while True:
                url = f"{self.base_url}/ticket/status/{status}/page/{page}/pagesize/{DEFAULT_PAGE_SIZE}"
                logging.debug(f"Requesting tickets: {url}")
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()

                records = data.get("data")
                if not isinstance(records, list) or not records:
                    break

                for record in records:
                    yield record
                page += 1

    def get_customers(self) -> Generator[Dict[str, Any], None, None]:
        start_date, end_date = self.config.sync_options.date_range_strings(self.state)
        page = 1
        while True:
            url = (
                f"{self.base_url}/customer/signup/from/{start_date}/to/{end_date}/"
                f"page/{page}/pagesize/{DEFAULT_PAGE_SIZE}"
            )
            logging.debug(f"Requesting customers: {url}")
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

            records = data.get("data")
            if not isinstance(records, list) or not records:
                break

            for record in records:
                yield record
            page += 1

    def get_products(self) -> Generator[Dict[str, Any], None, None]:
        page = 1
        while True:
            url = f"{self.base_url}/product/product_list?page={page}"
            logging.debug(f"Requesting products: {url}")
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()

            records = data.get("data")
            if not isinstance(records, list) or not records:
                break

            for record in records:
                yield record
            page += 1

    def get_caregivers(self) -> Generator[Dict[str, Any], None, None]:
        """
        Fetches caregiver records from the Treez API.
        This endpoint does not support pagination.
        """
        url = f"{self.base_url}/customer/caregivers"
        logging.debug(f"Requesting caregivers: {url}")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()

        data = response.json()
        records = data.get("data") or []

        if not isinstance(records, list):
            logging.warning("Unexpected caregivers response structure: %s", data)
            return

        for record in records:
            yield record
