"""Tool registration and JSON-schema generation for the handwritten Agent."""

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union, get_args, get_origin, get_type_hints


@dataclass
class ToolDefinition:
    """A callable tool plus the schema exposed to the LLM."""

    name: str
    description: str
    func: Callable[..., Any]
    schema: Dict[str, Any]


class ToolRegistry:
    """Registers Python functions and dispatches tool calls by name."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, func: Optional[Callable[..., Any]] = None, *, name: str = "", description: str = ""):
        def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
            tool_def = build_tool_definition(
                target,
                name=name or target.__name__,
                description=description or inspect.getdoc(target) or "",
            )
            self._tools[tool_def.name] = tool_def
            return target

        if func is None:
            return decorator
        return decorator(func)

    def add(self, tool_def: ToolDefinition) -> None:
        self._tools[tool_def.name] = tool_def

    def schemas(self) -> List[Dict[str, Any]]:
        return [tool_def.schema for tool_def in self._tools.values()]

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def call(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self._tools:
            available = ", ".join(sorted(self._tools))
            raise KeyError(f"Unknown tool: {name}. Available tools: {available}")

        tool_def = self._tools[name]
        signature = inspect.signature(tool_def.func)
        accepted_arguments = {
            key: value
            for key, value in arguments.items()
            if key in signature.parameters
        }
        return tool_def.func(**accepted_arguments)


def tool(*, name: str = "", description: str = ""):
    """Decorator that marks a function as a standalone tool definition."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__tool_definition__ = build_tool_definition(  # type: ignore[attr-defined]
            func,
            name=name or func.__name__,
            description=description or inspect.getdoc(func) or "",
        )
        return func

    return decorator


def get_tool_definition(func: Callable[..., Any]) -> ToolDefinition:
    tool_def = getattr(func, "__tool_definition__", None)
    if tool_def is None:
        tool_def = build_tool_definition(func)
    return tool_def


def build_tool_definition(
    func: Callable[..., Any],
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> ToolDefinition:
    tool_name = name or func.__name__
    tool_description = description if description is not None else (inspect.getdoc(func) or "")
    parameters_schema = function_parameters_schema(func)
    schema = {
        "name": tool_name,
        "description": tool_description,
        "parameters": parameters_schema,
    }
    return ToolDefinition(
        name=tool_name,
        description=tool_description,
        func=func,
        schema=schema,
    )


def function_parameters_schema(func: Callable[..., Any]) -> Dict[str, Any]:
    signature = inspect.signature(func)
    type_hints = get_type_hints(func)
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for param_name, parameter in signature.parameters.items():
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue

        annotation = type_hints.get(param_name, Any)
        field_schema = type_to_schema(annotation)
        if parameter.default is not inspect.Parameter.empty:
            field_schema["default"] = parameter.default
        else:
            required.append(param_name)
        properties[param_name] = field_schema

    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def type_to_schema(annotation: Any) -> Dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation is Any or annotation is inspect.Parameter.empty:
        return {"type": "object"}

    if origin is Union:
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            schema = type_to_schema(non_none_args[0])
            schema["nullable"] = True
            return schema
        return {"anyOf": [type_to_schema(arg) for arg in non_none_args]}

    if origin in {list, List}:
        item_type = args[0] if args else Any
        return {
            "type": "array",
            "items": type_to_schema(item_type),
        }

    if origin in {dict, Dict}:
        return {"type": "object"}

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}

    return {"type": "object"}
