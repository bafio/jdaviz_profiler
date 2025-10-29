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
        required=False,
        type=bool,
        default=False,
        choices=[True, False],
    )
    parser.add_argument(
        "--max_wait_time",
        help="Max time to wait after executing each cell (in minutes, default: 5).",
        required=False,
        type=int,
        default=5,
    )
    parser.add_argument(
        "--log_screenshots",
        help="Whether to log screenshots or not (default: False).",
        required=False,
        type=bool,
        default=False,
        choices=[True, False],
    )
    parser.add_argument(
        "--save_metrics",
        help="Whether to save profiling metrics to a CSV file (default: False).",
        required=False,
        type=bool,
        default=False,
        choices=[True, False],
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
    args: argparse.Namespace = parser.parse_args()

    # Set logger with given log_level
    set_logger(log_level=args.log_level)

    # Convert args to dictionary and remove log_level
    args: dict[str, Any] = vars(args)
    del args["log_level"]

    # Generate and profile notebooks with the given arguments
    generate_and_profile(**args)
