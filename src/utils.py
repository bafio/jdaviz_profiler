import ast
import itertools
import json
import logging
from collections import OrderedDict
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

KILOBYTE: int = 1024
MEGABYTE: int = 1024 * KILOBYTE


async def load_dict_from_json_file(file_path: str) -> dict[str, Any]:
    """
    Load a dictionary of key-value pairs from a JSON file.
    Parameters
    ----------
    file_path : str
        Path to the JSON file.
    Returns
    -------
    dict
        Dictionary containing the key-value pairs.
    Raises
    ------
    FileNotFoundError
        If the JSON file does not exist.
    ValueError
        If the JSON file is empty or improperly formatted.
    """
    with open(file_path, "r") as f:
        data: dict = json.loads(f.read())
    if not data:
        msg: str = f"No data found in {file_path}"
        logger.error(msg)
        raise ValueError(msg)
    return data


async def parse_assignments(src: str) -> OrderedDict[str, Any]:
    """
    Parse top-level variable assignments from Python source and return an OrderedDict
    of name->value.
    Features:
    - Handles simple Assign and AnnAssign nodes.
    - Uses ast.literal_eval for safe evaluation of literals
        (numbers, strings, tuples, lists, dicts).
    - Supports unary literals (e.g. -1).
    - Skips assignments whose values are non-literal expressions
        (function calls, names, comprehensions, etc).
    - Skips targets that are not simple names (e.g. tuple unpacking).
    Parameters
    ----------
    src : str
        Python source code as a string.
    Returns
    -------
    OrderedDict[str, Any]
        Ordered dictionary mapping variable names to their evaluated literal values.
    """
    tree: ast.AST = ast.parse(src)
    result: OrderedDict[str, Any] = OrderedDict()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            # e.g. a = 1 or a = (1,2)
            try:
                value: Any = ast.literal_eval(node.value)
            except Exception:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id]: Any = value
        elif isinstance(node, ast.AnnAssign):
            # e.g. a: int = 1
            target: ast.Name | None = node.target
            if isinstance(target, ast.Name) and node.value is not None:
                try:
                    value: Any = ast.literal_eval(node.value)
                except Exception:
                    continue
                result[target.id]: Any = value
    return result


async def dict_combinations(input_dict: dict) -> list[dict[str, Any]]:
    """
    Generate all combinations of values from a dictionary.
    Parameters
    ----------
    input_dict : dict
        Dictionary containing parameter names and their possible values.
    Returns
    -------
    list of dict
        List of dictionaries, each representing a unique combination of parameters.
    """
    keys: list[str] = input_dict.keys()
    values: list[list[Any]] = input_dict.values()
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]
