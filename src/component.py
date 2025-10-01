"""
Treez Extractor Component main class.
"""
import logging
from datetime import datetime, UTC

from keboola.component.base import ComponentBase
from keboola.component.exceptions import UserException

from configuration import Configuration
from api_client import TreezAPIClient
from utils import write_output_table_if_data


class Component(ComponentBase):
    def __init__(self):
        super().__init__()

    def run(self):
        run_time = datetime.now(UTC)
        run_time_str = run_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        config = Configuration(**self.configuration.parameters)
        state = self.get_state_file()
        new_state = {}

        api_client = TreezAPIClient(config=config, state=state)

        if config.endpoints.tickets:
            if not config.endpoints.order_status:
                logging.warning("Tickets sync skipped: No order_status values provided.")
            else:
                logging.info(f"Fetching tickets for statuses: {', '.join(config.endpoints.order_status)}")
                ticket_records = list(api_client.get_tickets_by_status())

                write_output_table_if_data(
                    self,
                    name="tickets",
                    records=ticket_records,
                    primary_key=["ticket_id"],
                    incremental=(config.sync_options.sync_mode == "incremental_sync")
                )

                write_output_table_if_data(
                    self,
                    name="employees",
                    records=list(api_client.employees.values()),
                    primary_key=["employee_id"],
                    incremental=(config.sync_options.sync_mode == "incremental_sync")
                )

                write_output_table_if_data(
                    self,
                    name="ticket_items",
                    records=api_client.ticket_items,
                    primary_key=["id", "product_id"],
                    incremental=(config.sync_options.sync_mode == "incremental_sync")
                )

                write_output_table_if_data(
                    self,
                    name="ticket_items_discounts",
                    records=api_client.ticket_items_discounts,
                    primary_key=["discount_id", "item_id"],
                    incremental=(config.sync_options.sync_mode == "incremental_sync")
                )

                write_output_table_if_data(
                    self,
                    name="ticket_items_tax",
                    records=api_client.ticket_items_tax,
                    primary_key=["id", "item_id"],
                    incremental=(config.sync_options.sync_mode == "incremental_sync")
                )

                write_output_table_if_data(
                    self,
                    name="ticket_payments",
                    records=api_client.ticket_payments,
                    primary_key=["payment_id"],
                    incremental=(config.sync_options.sync_mode == "incremental_sync")
                )

        if config.endpoints.customers:
            logging.info("Fetching customers...")
            write_output_table_if_data(
                self,
                name="customers",
                records=api_client.get_customers(),
                primary_key=["email"],
                incremental=(config.sync_options.sync_mode == "incremental_sync")
            )

        if config.endpoints.products:
            logging.info("Fetching products...")
            product_records = list(api_client.get_products())

            write_output_table_if_data(
                self,
                name="products",
                records=product_records,
                primary_key=["product_id"],
                incremental=(config.sync_options.sync_mode == "incremental_sync")
            )

            write_output_table_if_data(
                self,
                name="products_configurable_fields",
                records=api_client.products_configurable_fields,
                primary_key=["product_id"],
                incremental=(config.sync_options.sync_mode == "incremental_sync")
            )

            write_output_table_if_data(
                self,
                name="products_pricing",
                records=api_client.products_pricing,
                primary_key=["product_id"],
                incremental=(config.sync_options.sync_mode == "incremental_sync")
            )

            write_output_table_if_data(
                self,
                name="products_discounts",
                records=api_client.products_discounts,
                primary_key=["product_id", "discount_id"],
                incremental=(config.sync_options.sync_mode == "incremental_sync")
            )

            write_output_table_if_data(
                self,
                name="products_discount_condition_detail",
                records=api_client.products_discount_condition_detail,
                primary_key=["discount_id", "discount_condition_type", "discount_condition_value"],
                incremental=(config.sync_options.sync_mode == "incremental_sync")
            )

        if config.endpoints.caregivers:
            logging.info("Fetching caregivers...")
            write_output_table_if_data(
                self,
                name="caregivers",
                records=api_client.get_caregivers(),
                primary_key=["id"],
                incremental=(config.sync_options.sync_mode == "incremental_sync")
            )

        new_state["last_successful_run"] = run_time_str
        logging.info("Saving component state...")
        self.write_state_file(new_state)
        logging.info("Data processing completed!")


"""
Main entrypoint
"""
if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
