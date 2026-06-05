import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class AccountRequest(BaseModel):
    account_id: uuid.UUID
    state: str | None = None


class TokenExchangeRequest(BaseModel):
    account_id: uuid.UUID
    request_token: str = Field(min_length=1)


class SharekhanOrderPayload(BaseModel):
    customerId: str | None = None
    scripCode: int | None = None
    tradingSymbol: str | None = None
    exchange: str | None = None
    transactionType: Literal["B", "S"] | None = None
    quantity: int | None = Field(default=None, gt=0)
    disclosedQty: int = Field(ge=0, default=0)
    price: Decimal | None = Field(default=None, ge=0)
    triggerPrice: Decimal = Field(default=Decimal("0"), ge=0)
    rmsCode: str = "ANY"
    afterHour: Literal["Y", "N"] = "N"
    orderType: str = "NORMAL"
    channelUser: str | None = None
    validity: str = "GFD"
    requestType: Literal["NEW", "MODIFY", "CANCEL"] = "NEW"
    productType: str | None = "INVESTMENT"
    orderId: str | None = None
    instrumentType: str | None = None
    strikePrice: Decimal | None = None
    optionType: str | None = None
    expiry: str | None = None

    @field_validator("tradingSymbol", "exchange", "productType")
    @classmethod
    def uppercase_required_fields(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("field cannot be blank")
        return value.upper()

    @model_validator(mode="after")
    def validate_action(self) -> "SharekhanOrderPayload":
        required_for_new = [
            "customerId",
            "scripCode",
            "tradingSymbol",
            "exchange",
            "transactionType",
            "quantity",
            "price",
            "channelUser",
            "productType",
        ]
        if self.requestType == "NEW":
            missing = [field for field in required_for_new if getattr(self, field) in (None, "")]
            if missing:
                raise ValueError(f"missing required fields for NEW order: {', '.join(missing)}")
        if self.requestType in {"MODIFY", "CANCEL"} and not self.orderId:
            raise ValueError("orderId is required for MODIFY and CANCEL")
        return self


class WsSubscription(BaseModel):
    symbols: list[str] = Field(min_length=1)
    exchange: str


class BrokerResponse(BaseModel):
    ok: bool
    data: dict[str, Any]
    normalized: dict[str, Any] | None = None
    paper_trading: bool = False
