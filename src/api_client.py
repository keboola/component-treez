import json

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

        access_token = auth_data.get("access_token")
        if not access_token:
            raise RuntimeError(f"Auth failed: {auth_data}")
        return access_token

    def get_tickets_by_status(self) -> Generator[Dict[str, Any], None, None]:
        """
        Streams ticket records grouped by status from Treez.
        Matches actual API response structure: data["ticketList"].
        """
        statuses = self.config.endpoints.order_status

        for status in statuses:
            page = 1
            while True:
                url = f"{self.base_url}/ticket/status/{status}/page/{page}/pagesize/{DEFAULT_PAGE_SIZE}"
                logging.debug(f"Requesting tickets: {url}")

                try:
                    response = requests.get(url, headers=self.headers)
                    response.raise_for_status()
                    data = response.json()
                except Exception as e:
                    logging.warning(f"Failed to fetch tickets for status '{status}' on page {page}: {e}")
                    break

                records = data.get("ticketList", [])

                if not isinstance(records, list):
                    logging.warning(
                        "Unexpected ticket response format for status "
                        f"'{status}':\n{json.dumps(data, indent=2)}"
                    )
                    break

                if not records:
                    logging.info(f"No more tickets for status '{status}' on page {page}.")
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
        """
        Streams product records from the Treez API with pagination.
        Matches response structure where products are under data["product_list"].
        """
        page = 1
        while True:
            url = f"{self.base_url}/product/product_list?page={page}"
            logging.debug(f"Requesting products: {url}")

            try:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
            except Exception as e:
                logging.warning(f"Failed to fetch products on page {page}: {e}")
                break

            product_container = data.get("data", {})
            records = product_container.get("product_list", [])

            if not isinstance(records, list):
                logging.warning(f"Unexpected product response format:\n{json.dumps(data, indent=2)}")
                break

            if not records:
                logging.info(f"No more product records at page {page}.")
                break

            for record in records:
                yield record

            page += 1

    def get_caregivers(self) -> Generator[Dict[str, Any], None, None]:
        """
        Fetches caregiver records from the Treez API.
        This endpoint does not support pagination.
        Handles empty or unexpected structures gracefully.
        """
        url = f"{self.base_url}/customer/caregivers"
        logging.debug(f"Requesting caregivers: {url}")

        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logging.warning(f"Failed to fetch caregivers: {e}")
            return

        caregiver_container = data.get("data", {})
        caregivers = caregiver_container.get("caregiver_list", [])

        if not isinstance(caregivers, list):
            logging.warning("Unexpected caregivers response structure: %s", json.dumps(data, indent=2))
            return

        if not caregivers:
            logging.info("No caregiver records found.")
            return

        for record in caregivers:
            yield record
