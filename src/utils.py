import ast
import itertools
import json
import logging
from collections import OrderedDict
from time import sleep, time
from typing import Any

from nbformat import NotebookNode

KILOBYTE: int = 1024
MEGABYTE: int = 1024 * KILOBYTE
LOGGER_NAME = "jdaviz_profiler"


def set_logger(log_level: str) -> None:
    """
    Set up the logger with the specified log level.
    Parameters
    ----------
    log_level : str
        The logging level (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
    """
    # Configure logger
    _logger: logging.Logger = logging.getLogger(LOGGER_NAME)
    _logger.setLevel(log_level)
    console_handler: logging.StreamHandler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s//%(module)s:%(funcName)s@%(lineno)d "
            "-->> %(message)s"
        )
    )
    _logger.addHandler(console_handler)
    _logger.propagate = False


def get_logger() -> logging.Logger:
    """
    Get the configured logger.
    Returns
    -------
    logging.Logger
        The configured logger instance.
    """
    return logging.getLogger(LOGGER_NAME)


def explicit_wait(seconds: int | float) -> None:
    """
    Pause execution for a specified number of seconds.
    Parameters
    ----------
    seconds : int | float
        Number of seconds to pause execution.
    """
    sleep(seconds)


def elapsed_time(from_time: float = 0) -> float:
    """
    Calculate the elapsed time since a given starting time.
    Parameters
    ----------
    from_time : float, optional
        The starting time in seconds since the epoch. Default is 0.
    Returns
    -------
    float
        The elapsed time in seconds.
    """
    return time() - from_time


def load_dict_from_json_file(file_path: str) -> dict[str, Any]:
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
        if not (data := json.loads(f.read())):
            msg: str = f"No data found in {file_path}"
            raise ValueError(msg)
        return data


def parse_assignments(src: str) -> OrderedDict[str, Any]:
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


def dict_combinations(input_dict: dict) -> list[dict[str, Any]]:
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


def get_notebook_cell_indexes_for_tag(
    notebook: NotebookNode, cell_tag: str
) -> list[int]:
    """
    Collect the indexes of notebook cells marked with the requested tag `cell_tag`.
    Parameters
    ----------
    notebook : NotebookNode
        The notebook to read from.
    """
    cell_indexes: list[int] = []
    for cell_index, cell in enumerate(notebook.cells, 1):
        # Get the nb cell tagged with the specified cell_tag
        if cell_tag in cell.metadata.get("tags", []):
            cell_indexes.append(cell_index)
    return cell_indexes


def get_notebook_parameters(
    notebook: NotebookNode, cell_tag: str
) -> OrderedDict[str, Any]:
    """
    Return the parameters as an ordered dictionary from the notebook's cell
    tagged as `cell_tag`.
    Parameters
    ----------
    notebook : NotebookNode
        The notebook to read from.
    cell_tag: str
        The cell tag
    """
    for cell in notebook.cells:
        # Get the nb cell tagged with the specified cell_tag
        if cell_tag in cell.metadata.get("tags", []):
            cell_source: str = cell.source or ""
            return parse_assignments(cell_source)
    return OrderedDict()
