import inspect
from typing import TypeVar

from fastapi import Form
from humps.main import camelize
from pydantic import BaseModel
from pydantic.fields import ModelField

T = TypeVar("T", bound=BaseModel)


def as_form(cls):
    """
    Allows a Pydantic model to be used as a FastAPI form

    Use this @as_form decorator on your model, then reference it in FastAPI using Depends(YourModel.as_form)
    For type hinting add "as_form: ClassVar[Callable[..., YourModel]]" to your model and import __future__.annotations

    https://stackoverflow.com/questions/60127234/how-to-use-a-pydantic-model-with-form-data-in-fastapi
    """

    new_parameters = []

    for model_field in cls.__fields__.values():
        model_field: ModelField  # type: ignore

        new_parameters.append(
            inspect.Parameter(
                model_field.alias,
                inspect.Parameter.POSITIONAL_ONLY,
                default=Form(...) if model_field.required else Form(model_field.default),
                annotation=model_field.outer_type_,
            )
        )

    async def as_form_func(**data):
        return cls(**data)

    sig = inspect.signature(as_form_func)
    sig = sig.replace(parameters=new_parameters)
    as_form_func.__signature__ = sig  # type: ignore
    setattr(cls, "as_form", as_form_func)
    return cls


class APIBase(BaseModel):
    class Config:
        alias_generator = camelize
        allow_population_by_field_name = True

    def cast(self, cls: type[T], **kwargs) -> T:
        """
        Cast the current model to another with additional arguments. Useful for
        transforming DTOs into models that are saved to a database
        """
        create_data = {field: getattr(self, field) for field in self.__fields__ if field in cls.__fields__}
        create_data.update(kwargs or {})
        return cls(**create_data)

    def map_to(self, dest: T) -> T:
        """
        Map matching values from the current model to another model. Model returned
        for method chaining.
        """

        for field in self.__fields__:
            if field in dest.__fields__:
                setattr(dest, field, getattr(self, field))

        return dest

    def map_from(self, src: BaseModel):
        """
        Map matching values from another model to the current model.
        """

        for field in src.__fields__:
            if field in self.__fields__:
                setattr(self, field, getattr(src, field))

    def merge(self, src: T, replace_null=False):
        """
        Replace matching values from another instance to the current instance.
        """

        for field in src.__fields__:
            val = getattr(src, field)
            if field in self.__fields__ and (val is not None or replace_null):
                setattr(self, field, val)
