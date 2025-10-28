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
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    args: argparse.Namespace = parser.parse_args()

    # Set logger with given log_level
    set_logger(log_level=args.log_level)

    args: dict[str, Any] = vars(args)
    del args["log_level"]

    generate_notebooks(**args)
