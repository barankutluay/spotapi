import functools
import inspect
from collections.abc import Generator, Iterable, Mapping, Sequence
from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    ParamSpec,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

__all__ = ["enforce_types", "EnforceMeta", "enforce"]

_EnforceType = TypeVar("_EnforceType", bound=type)
R = TypeVar("R")
P = ParamSpec("P")


def enforce_types(func: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator to enforce type annotations on function arguments and return value.
    """
    type_hints: Dict[str, Any] = getattr(func, "__annotations__", {})
    return_type: Optional[Any] = type_hints.get("return")

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        for arg_name, arg_value in bound_args.arguments.items():
            if arg_name in type_hints:
                expected_type = type_hints[arg_name]
                if not _is_instance_of(arg_value, expected_type):
                    raise TypeError(
                        f"Argument '{arg_name}' must be of type {_format_type(expected_type)}, "
                        f"but got {_format_type(type(arg_value))}"
                    )

        result: R = func(*args, **kwargs)

        if return_type is not None and not _is_instance_of(result, return_type):
            raise TypeError(
                f"Return value must be of type {_format_type(return_type)}, "
                f"but got {_format_type(type(result))}"
            )

        return result

    return wrapper


def _is_instance_of(value: Any, expected_type: Any) -> bool:
    """
    Recursively check if value matches the expected type.
    """
    origin = get_origin(expected_type)
    args = get_args(expected_type)

    if origin is None:
        try:
            return isinstance(value, expected_type)
        except TypeError:
            return True  # fallback for unknown types
    if origin is Union:
        return any(_is_instance_of(value, t) for t in args)
    if origin is list:
        return isinstance(value, list) and all(
            _is_instance_of(v, args[0]) for v in value
        )
    if origin is tuple:
        return (
            isinstance(value, tuple)
            and len(value) == len(args)
            and all(_is_instance_of(v, t) for v, t in zip(value, args))
        )
    if origin is dict:
        return isinstance(value, dict) and all(
            _is_instance_of(k, args[0]) and _is_instance_of(v, args[1])
            for k, v in value.items()
        )
    if origin is Sequence:
        return isinstance(value, (list, tuple))
    if origin is Iterable:
        return isinstance(value, Iterable)
    if origin is Mapping:
        return isinstance(value, Mapping)
    if origin is Generator:
        return isinstance(value, Generator)

    return isinstance(value, expected_type)


def _format_type(t: Any) -> str:
    """
    Nicely format types for error messages.
    """
    origin = get_origin(t)
    args = get_args(t)

    if origin is Union:
        return f"Union[{', '.join(_format_type(arg) for arg in args)}]"
    if origin is list:
        return f"List[{_format_type(args[0])}]"
    if origin is tuple:
        return f"Tuple[{', '.join(_format_type(arg) for arg in args)}]"
    if origin is dict:
        return f"Dict[{_format_type(args[0])}, {_format_type(args[1])}]"
    if origin is Sequence:
        return f"Sequence[{_format_type(args[0])}]"
    if origin is Iterable:
        return f"Iterable[{_format_type(args[0])}]"
    if origin is Mapping:
        return f"Mapping[{_format_type(args[0])}, {_format_type(args[1])}]"
    if origin is Generator:
        return f"Generator[{', '.join(_format_type(arg) for arg in args)}]"

    return str(t)


def enforce(cls: _EnforceType) -> _EnforceType:
    """
    Decorator to enforce type checking on all methods of a class.
    """
    for attr_name in dir(cls):
        attr_value = getattr(cls, attr_name)

        if isinstance(attr_value, property):
            continue
        if callable(attr_value) and not attr_name.startswith("__"):
            setattr(cls, attr_name, enforce_types(attr_value))

    return cls


class EnforceMeta(type):
    """
    Optional metaclass for auto-enforcing types on class methods.
    """

    def __new__(
        cls: Type[type], name: str, bases: tuple[type, ...], dct: Dict[str, Any]
    ) -> type:
        for attr_name, attr_value in dct.items():
            if callable(attr_value) and not attr_name.startswith("__"):
                dct[attr_name] = enforce_types(attr_value)
        return super().__new__(cls, name, bases, dct)
