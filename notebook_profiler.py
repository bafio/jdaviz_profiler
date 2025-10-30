#!/usr/bin/env python3

import argparse
from typing import Any

from src.profile_notebook import profile_notebook
from src.utils import set_logger

if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Script that Uses Selenium to launch and interact with JupyterLab, "
            "executing each notebook cell and recording performance metrics."
        )
    )
    parser.add_argument(
        "--url",
        help=(
            "The URL of the JupyterLab instance where the notebook is going to "
            "be profiled."
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
        "--nb_input_path",
        help="Path to the input notebook to be profiled.",
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
        help="Max time to wait after executing each cell (in minutes, default: 5).",
        required=False,
        type=int,
        default=5,
    )
    parser.add_argument(
        "--screenshots_dir_path",
        help=(
            "Path to the directory to where screenshots will be stored (default: None)."
        ),
        required=False,
        type=str,
        default=None,
    )
    parser.add_argument(
        "--metrics_dir_path",
        help=("Path to the directory to where metrics will be stored (default: None)."),
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
    args: argparse.Namespace = parser.parse_args()

    # Set logger with given log_level
    set_logger(log_level=args.log_level)

    # Convert args to dict and remove log_level
    args: dict[str, Any] = vars(args)
    del args["log_level"]

    # Profile the notebook with the given arguments
    profile_notebook(**args)
