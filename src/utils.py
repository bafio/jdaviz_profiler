import ast
import itertools
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import StrEnum, unique
from pathlib import Path
from time import sleep, time
from typing import Any

from nbformat import NotebookNode

KILOBYTE: int = 1024
MEGABYTE: int = 1024 * KILOBYTE
LOGGER_NAME = "jdaviz_profiler"


@dataclass
class ProfilerContext:
    """
    Context dataclass to hold all necessary parameters for profiling.
    Attributes
    ----------
    kernel_name : str
        The name of the kernel to use for the notebook.
    headless : bool
        Whether to run in headless mode.
    max_wait_time : int
        Max time to wait after executing each cell (in seconds).
    url : str
        The URL of the JupyterLab instance where the notebook is going to be profiled.
    token : str
        The token to access the JupyterLab instance.
    nb_input_path : Path
        Path of the input notebook to be profiled.
    screenshots_dir_path : Path | None
        Path to the directory to where screenshots will be stored, if not passed as
        an argument, screenshots will not be logged.
    notebook_metrics_file_path : Path | None
        Path to the file to where the notebook metrics will be stored, if not passed as
        an argument,notebook metrics will not be saved to file.
    cell_metrics_file_path : Path | None
        Path to the file to where the cell metrics will be stored, if not passed as
        an argument, cell metrics will not be saved to file.
    """

    kernel_name: str
    headless: bool
    max_wait_time: int
    url: str = ""
    token: str = ""
    nb_input_path: Path = field(default_factory=Path)
    screenshots_dir_path: Path | None = field(default=None)
    notebook_metrics_file_path: Path | None = field(default=None)
    cell_metrics_file_path: Path | None = field(default=None)

    def __repr__(self) -> str:
        return " -- ".join(
            (
                f"URL: {self.url}",
                f"Token: {self.token}",
                f"Kernel Name: {self.kernel_name}",
                f"Input Notebook Path: {self.nb_input_path}",
                f"Headless: {self.headless}",
                f"Max Wait Time: {self.max_wait_time}",
                f"Screenshots Dir Path: {self.screenshots_dir_path}",
                f"Notebook Metrics File Path: {self.notebook_metrics_file_path}",
                f"Cell Metrics File Path: {self.cell_metrics_file_path}",
            )
        )


@unique
class CellExecutionStatus(StrEnum):
    """
    Represents the various possible statuses of a notebook cell execution process.
    """

    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    TIMED_OUT = "Timed Out"

    @property
    def is_not_final(self) -> bool:
        """Returns True if the status is not a final state, False otherwise."""
        return self in {CellExecutionStatus.PENDING, CellExecutionStatus.IN_PROGRESS}

    @property
    def is_final(self) -> bool:
        """Returns True if the status is a final state, False otherwise."""
        return not self.is_not_final


def set_logger(log_level: str = "INFO", log_file: Path | None = None) -> None:
    """
    Set up the logger with the specified log level.
    Parameters
    ----------
    log_level : str
        The logging level (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
        Default is 'INFO'.
    log_file : Path | None
        The path to the log file. If None, logs will only be printed to console.
        Default is None.
    """
    # Configure logger
    logging_formatter: logging.Formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s/%(module)s:%(funcName)s@%(lineno)d "
        "-->> %(message)s"
    )
    _logger: logging.Logger = logging.getLogger(LOGGER_NAME)
    _logger.setLevel(log_level)
    #  Add console handler
    console_handler: logging.StreamHandler = logging.StreamHandler()
    console_handler.setFormatter(logging_formatter)
    _logger.addHandler(console_handler)
    if log_file is not None:
        # Add file handler
        file_handler: logging.FileHandler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging_formatter)
        _logger.addHandler(file_handler)
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


def load_dict_from_json_file(file_path: Path) -> dict[str, Any]:
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
    with file_path.open("r") as f:
        if not (data := json.loads(f.read())):
            raise ValueError(f"No data found in {file_path}")
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
    tree: ast.Module = ast.parse(src)
    result: OrderedDict[str, Any] = OrderedDict()
    value: Any | None
    target: Any | None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            # e.g. a = 1 or a = (1,2)
            try:
                value = ast.literal_eval(node.value)
            except Exception:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = value
        elif isinstance(node, ast.AnnAssign):
            # e.g. a: int = 1
            target = node.target
            if isinstance(target, ast.Name) and node.value is not None:
                try:
                    value = ast.literal_eval(node.value)
                except Exception:
                    continue
                result[target.id] = value
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
    return [
        dict(zip(input_dict.keys(), combo))
        for combo in itertools.product(*input_dict.values())
    ]


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
