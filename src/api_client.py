import json

import requests
import logging
from typing import Generator, Dict, Any

from configuration import Configuration
from utils import normalize_to_utc_iso

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
        self.employees = {}
        self.ticket_items = []
        self.ticket_items_discounts = []
        self.ticket_items_tax = []
        self.ticket_payments = []
        self.products_configurable_fields = []
        self.products_pricing = []
        self.products_discounts = []
        self.products_discount_condition_detail = []

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
                if not isinstance(records, list) or not records:
                    logging.info(f"No more tickets for status '{status}' on page {page}.")
                    break

                for record in records:
                    ticket_id = record.get("ticket_id")

                    for ts_key in ("date_created", "last_updated_at", "date_closed"):
                        if record.get(ts_key):
                            record[ts_key] = normalize_to_utc_iso(record[ts_key])

                    created_by = record.pop("created_by_employee", None)
                    if isinstance(created_by, dict):
                        emp_id = created_by.get("employee_id")
                        record["created_by_employee_id"] = emp_id
                        if emp_id and emp_id not in self.employees:
                            self.employees[emp_id] = created_by

                    packed_by = record.pop("packed_by_employee", None)
                    if isinstance(packed_by, dict):
                        emp_id = packed_by.get("employee_id")
                        record["packed_by_employee_id"] = emp_id
                        if emp_id and emp_id not in self.employees:
                            self.employees[emp_id] = packed_by
                    else:
                        record["packed_by_employee_id"] = None

                    items = record.pop("items", [])
                    for item in items:
                        item_id = item.get("id")

                        flat_item = {
                            "ticket_id": ticket_id,
                            **{k: v for k, v in item.items() if k not in ("discounts", "tax")}
                        }
                        self.ticket_items.append(flat_item)

                        for discount in item.get("discounts", []):
                            self.ticket_items_discounts.append({
                                "ticket_id": ticket_id,
                                "item_id": item_id,
                                **discount
                            })

                        for tax in item.get("tax", []):
                            self.ticket_items_tax.append({
                                "ticket_id": ticket_id,
                                "item_id": item_id,
                                **tax
                            })

                    payments = record.pop("payments", [])
                    for payment in payments:
                        if payment.get("payment_date"):
                            payment["payment_date"] = normalize_to_utc_iso(payment["payment_date"])

                        self.ticket_payments.append({
                            "ticket_id": ticket_id,
                            **payment
                        })

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

            if not isinstance(records, list) or not records:
                break

            for record in records:
                product_id = record.get("product_id")

                configurable = record.pop("product_configurable_fields", {})
                if isinstance(configurable, dict):
                    self.products_configurable_fields.append({
                        "product_id": product_id,
                        **configurable
                    })

                pricing = record.pop("pricing", {})
                if isinstance(pricing, dict):
                    self.products_pricing.append({
                        "product_id": product_id,
                        **pricing
                    })

                discounts = record.pop("discounts", [])
                for discount in discounts or []:
                    discount_id = discount.get("discount_id")
                    condition_details = discount.pop("discount_condition_detail", [])
                    self.products_discounts.append({
                        "product_id": product_id,
                        **discount
                    })

                    for condition in condition_details or []:
                        self.products_discount_condition_detail.append({
                            "discount_id": discount_id,
                            **condition
                        })

                for nested_key in ["product_configurable_fields", "pricing", "discounts"]:
                    record.pop(nested_key, None)

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
