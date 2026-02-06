#!/usr/bin/env python3

"""
Create a new directory with an example template notebook and a
parameters file that can be filled-in to run a new profiling
"use case" (a new combination of example notebook and parameters).
"""

import argparse
import json
import shutil
from pathlib import Path

from src.generate_notebooks import (
    NOTEBOOK_TEMPLATE_FILENAME,
    OUTPUT_DIR_PATH,
    PARAMS_FILENAME,
)
from src.utils import set_logger

USECASES_DIR_PATH: Path = Path(__file__).parent / "usecases"


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Script to add new use cases for notebook generation and profiling."
        )
    )
    parser.add_argument(
        "--name",
        help="The name of the new use case.",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--log_file",
        help="Path to the log file.",
        required=False,
        type=Path,
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

    new_usecase_name: str = _args.name.strip()
    if not new_usecase_name:
        raise ValueError("The use case name cannot be empty or whitespace.")

    # Create new use case directory
    new_usecase_dir_path: Path = USECASES_DIR_PATH / new_usecase_name
    if new_usecase_dir_path.exists():
        raise FileExistsError(
            f"The use case directory '{new_usecase_dir_path}' already exists."
        )
    new_usecase_dir_path.mkdir(parents=True)

    try:
        # Create empty template.ipynb and params.json files
        notebook_template_path: Path = new_usecase_dir_path / NOTEBOOK_TEMPLATE_FILENAME
        example_template_path: Path = USECASES_DIR_PATH / "example_template.ipynb"
        shutil.copy(
            USECASES_DIR_PATH / "example_template.ipynb", notebook_template_path
        )

        # Create example params.json file
        params_path: Path = new_usecase_dir_path / PARAMS_FILENAME
        example_params = {
            "paramA_value": [1, 2, 3],
            "paramB_value": ["x", "y", "z"],
            "paramC_value": [True, False],
        }
        with params_path.open(mode="w", encoding="utf-8") as params_file:
            json.dump(example_params, params_file, indent=4)

        # Create notebooks output directory
        notebooks_dir_path: Path = new_usecase_dir_path / OUTPUT_DIR_PATH
        notebooks_dir_path.mkdir()
        (notebooks_dir_path / ".keep").touch()
    except Exception as e:
        # Clean up by removing the created use case directory
        for child in new_usecase_dir_path.rglob("*"):
            if child.is_file():
                child.unlink()
            else:
                child.rmdir()
        new_usecase_dir_path.rmdir()
        raise e
