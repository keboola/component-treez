import logging
from datetime import datetime
from typing import Dict, List, Literal

import pytz
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from keboola.component.exceptions import UserException
from dateparser import parse as parse_natural_date

VALID_ORDER_STATUSES = {
    "VERIFICATION_PENDING",
    "AWAITING_PROCESSING",
    "IN_PROCESS",
    "PACKED_READY",
    "OUT_FOR_DELIVERY",
    "COMPLETED",
    "CANCELED"
}


class Authorization(BaseModel):
    dispensary_name: str
    client_id: str = Field(alias="#client_id")
    api_key: str = Field(alias="#api_key")

    @field_validator("dispensary_name", "client_id", "api_key")
    def must_not_be_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"Field '{info.field_name}' cannot be empty")
        return value


class Endpoints(BaseModel):
    tickets: bool = Field(default=False, description="Download ticket data")
    customers: bool = Field(default=False, description="Download customer records")
    caregivers: bool = Field(default=False, description="Download caregiver records")
    products: bool = Field(default=False, description="Download product data")
    order_status: List[str] = Field(default=[], description="Order statuses to filter ticket data")

    @model_validator(mode='after')
    def validate_order_statuses(cls, model):
        invalid = [s for s in model.order_status if s not in VALID_ORDER_STATUSES]
        if invalid:
            raise ValueError(f"Invalid order statuses: {', '.join(invalid)}")
        return model


class SyncOptions(BaseModel):
    sync_mode: Literal["full_sync", "incremental_sync"] = Field(default="full_sync")
    date_from: str = Field(default="1 month ago")
    date_to: str = Field(default="now")

    def _parse_natural_date(self, input_str: str) -> datetime:
        date_obj = parse_natural_date(input_str, settings={"TIMEZONE": "UTC"})
        if date_obj is None:
            raise UserException(f"Invalid date string: '{input_str}'")
        return date_obj.replace(tzinfo=pytz.UTC)

    def resolved_date_from(self, state: Dict[str, str]) -> datetime:
        input_value = self.date_from.strip().lower()

        if input_value in {"last", "lastrun", "last_run", "last run"}:
            last_run = state.get("last_successful_run")
            if not last_run:
                raise UserException(
                    "You used 'last run' as date_from, but no previous run state was found."
                )
            return self._parse_natural_date(last_run)

        return self._parse_natural_date(input_value)

    def resolved_date_to(self) -> datetime:
        return self._parse_natural_date(self.date_to.strip().lower())

    def date_range_strings(self, state: Dict[str, str]) -> tuple[str, str]:
        from_dt = self.resolved_date_from(state)
        to_dt = self.resolved_date_to()

        if from_dt > to_dt:
            raise UserException("date_from cannot be after date_to.")

        return from_dt.strftime("%Y-%m-%d"), to_dt.strftime("%Y-%m-%d")


class Configuration(BaseModel):
    authorization: Authorization
    endpoints: Endpoints
    sync_options: SyncOptions
    debug: bool = False

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            error_messages = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Validation Error: {', '.join(error_messages)}")

        if self.debug:
            logging.debug("Component will run in Debug mode")
