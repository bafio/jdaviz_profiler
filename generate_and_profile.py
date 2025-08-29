#!/usr/bin/env python3
"""
Script to generate the profiler notebooks from a template and run the profiler on them.
"""
import argparse
import asyncio
import logging
from os import path as os_path

from generate_profiler_notebooks import generate_profiler_notebooks
from profiler import profile


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


async def generate_and_profile(
        template_path: str, output_dir_path: str, url: str, token: str, headless: bool,
        wait_after_execute: int, log_level: str = "INFO"
) -> None:
    """
    Generate profiler notebooks from a template and run the profiler on them.
    Parameters
    ----------
    template_path : str
        Path to the notebook template file.
    output_dir_path : str
        Path to save the generated profiler notebooks.
    url : str
        The URL of the JupyterLab instance where the notebook is going to be profiled.
    token : str
        The token to access the JupyterLab instance.
    headless : bool
        Whether to run in headless mode.
    wait_after_execute : int
        Time to wait after executing each cell (in seconds).
    log_level : str, optional
        Set the logging level (default: "INFO").
    """
    # Set up logging
    logger.setLevel(log_level.upper())

    output_paths = generate_profiler_notebooks(
        template_path=template_path, output_dir_path=output_dir_path, log_level=log_level
    )
    nb_input_paths = [os_path.join(output_dir_path, os_path.split(p)[-1]) for p in output_paths]

    # Limit to first 5 notebooks for profiling
    nb_input_paths = nb_input_paths[:5]

    for nb_input_path in nb_input_paths:
        logger.info(f"Profiling notebook: {nb_input_path}")

        await profile(
            url=url, token=token, nb_input_path=nb_input_path, headless=headless,
            wait_after_execute=wait_after_execute, log_level=log_level
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = (
            "Script to generate the profiler notebooks from a template and "
            "run the profiler on them."
        )
    )
    parser.add_argument(
        "--template_path",
        help = "Path to the notebook template file.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--output_dir_path",
        help="Path to save the generated profiler notebooks.",
        required=False,
        type=str,
        default="notebooks",
    )
    parser.add_argument(
        "--url",
        help = "The URL of the JupyterLab instance where the notebook is going to be profiled.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--token",
        help = "The token to access the JupyterLab instance.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--headless",
        help = "Whether to run in headless mode (default: False).",
        required = False,
        type = bool,
        default = False,
        choices = [True, False],
    )
    parser.add_argument(
        "--wait_after_execute",
        help = "Time to wait after executing each cell (in seconds, default: 5).",
        required = False,
        type = int,
        default = 5,
    )
    parser.add_argument(
        "--log_level",
        help = "Set the logging level (default: INFO).",
        default = "INFO",
        choices = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(generate_and_profile(**vars(parser.parse_args())))
