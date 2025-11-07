#!/usr/bin/env python3

import argparse
from typing import Any

from src.generate_and_profile import generate_and_profile
from src.utils import set_logger

if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Script to generate the profiler notebooks from a template and "
            "run the profiler on them."
        )
    )
    parser.add_argument(
        "--input_dir_path",
        help=(
            "Path to the directory containing the template notebook and params.json "
            "file."
        ),
        required=True,
        type=str,
    )
    parser.add_argument(
        "--url",
        help=(
            "The URL of the JupyterLab instance where the notebook is going to be "
            "profiled."
        ),
        required=True,
        type=str,
    )
    parser.add_argument(
        "--token",
        help="The token to access the JupyterLab instance.",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--kernel_name",
        help="The name of the kernel to use for the notebook.",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--headless",
        help="Whether to run in headless mode (default: False).",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--max_wait_time",
        help="Max time to wait after executing each cell (in seconds, default: 300).",
        required=False,
        type=int,
        default=300,
    )
    parser.add_argument(
        "--log_screenshots",
        help="Whether to log screenshots or not (default: False).",
        action=argparse.BooleanOptionalAction,
        default=False,
    )
    parser.add_argument(
        "--save_metrics",
        help="Whether to save profiling metrics to a CSV file (default: False).",
        action=argparse.BooleanOptionalAction,
        default=False,
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
    generate_and_profile(**_kwargs)
