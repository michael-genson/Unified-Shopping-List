from typing import Any, Type, TypeVar

from humps.main import camelize
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class SQSMessage(BaseModel):
    message_id: str
    receipt_handle: str
    body: str
    attributes: dict[str, str]
    message_attributes: dict[str, Any]

    def parse_body(self, cls: Type[T]) -> T:
        """Return the body of the message as a Pydantic model"""

        return cls.parse_raw(self.body)

    class Config:
        alias_generator = camelize
        allow_population_by_field_name = True


class SQSEvent(BaseModel):
    records: list[SQSMessage] = Field(..., alias="Records")
