from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.lower()
    if not EMAIL_PATTERN.match(normalized):
        raise ValueError("must be a valid email address")
    return normalized


def blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value or None


def require_update_fields(model: BaseModel) -> BaseModel:
    if not model.model_fields_set:
        raise ValueError("at least one field must be provided")
    return model


def validate_date_range(start_date: Optional[date], end_date: Optional[date]) -> None:
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date cannot be after end_date")


class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


class RecordType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class TrendGranularity(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, use_enum_values=True)


class LoginRequest(APIModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value) or value


class UserCreateRequest(APIModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Role
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value) or value


class UserUpdateRequest(APIModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    email: Optional[str] = Field(default=None, min_length=5, max_length=255)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    role: Optional[Role] = None
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        return normalize_email(value)

    @model_validator(mode="after")
    def ensure_fields_present(self) -> "UserUpdateRequest":
        return require_update_fields(self)


class RecordCreateRequest(APIModel):
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    type: RecordType
    category: str = Field(min_length=1, max_length=80)
    date: date
    notes: Optional[str] = Field(default=None, max_length=500)


class RecordUpdateRequest(APIModel):
    amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"), max_digits=12, decimal_places=2)
    type: Optional[RecordType] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=80)
    date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def ensure_fields_present(self) -> "RecordUpdateRequest":
        return require_update_fields(self)


class RecordListQuery(APIModel):
    type: Optional[RecordType] = None
    category: Optional[str] = Field(default=None, max_length=80)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    q: Optional[str] = Field(default=None, max_length=100)
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("category", "q")
    @classmethod
    def collapse_blank_strings(cls, value: Optional[str]) -> Optional[str]:
        return blank_to_none(value)

    @model_validator(mode="after")
    def validate_dates(self) -> "RecordListQuery":
        validate_date_range(self.start_date, self.end_date)
        return self


class SummaryQuery(APIModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    recent_limit: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def validate_dates(self) -> "SummaryQuery":
        validate_date_range(self.start_date, self.end_date)
        return self


class TrendQuery(APIModel):
    granularity: TrendGranularity = TrendGranularity.MONTHLY
    periods: int = Field(default=6, ge=1, le=24)
    end_date: Optional[date] = None
    category: Optional[str] = Field(default=None, max_length=80)

    @field_validator("category")
    @classmethod
    def collapse_blank_category(cls, value: Optional[str]) -> Optional[str]:
        return blank_to_none(value)
