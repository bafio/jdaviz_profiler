#!/usr/bin/env python3

import argparse
from typing import Any

from src.generate_notebooks import generate_notebooks
from src.utils import set_logger

NOTEBOOK_TEMPLATE_FILENAME: str = "template.ipynb"
PARAMS_FILENAME: str = "params.json"
OUTPUT_DIR_PATH: str = "notebooks"


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Script to generate the parameterized notebooks from a template.ipynb and "
            "params.json."
        )
    )
    parser.add_argument(
        "--input_dir_path",
        help=(
            "Path to the directory containing the template.ipynb and params.json files."
        ),
        required=True,
        type=str,
    )
    parser.add_argument(
        "--log_file",
        help="Path to the log file.",
        required=False,
        type=str,
        default=None,
    )
    parser.add_argument(
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    # Parse arguments
    _args: argparse.Namespace = parser.parse_args()

    # Set logger with given log_level and log_file
    set_logger(log_level=_args.log_level, log_file=_args.log_file)

    # Convert args into a dictionary, remove log_level and log_file
    _kwargs: dict[str, Any] = vars(_args)
    del _kwargs["log_level"]
    del _kwargs["log_file"]

    # Generate notebooks with the given arguments
    generate_notebooks(**_kwargs)
