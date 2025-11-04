import logging
import os
import os.path as os_path
from time import gmtime, perf_counter_ns, strftime
from typing import Any

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from src.generate_notebooks import generate_notebooks
from src.profile_notebook import profile_notebook
from src.utils import ProfilerContext, get_logger

# Initialize logger
logger: logging.Logger = get_logger()


def generate_and_profile(
    input_dir_path: str,
    url: str,
    token: str,
    kernel_name: str,
    headless: bool,
    max_wait_time: int,
    log_screenshots: bool = False,
    save_metrics: bool = False,
) -> None:
    """
    Generate profiler notebooks from a template and run the profiler on them.
    Parameters
    ----------
    input_dir_path : str
        Path to the directory containing the template notebook and params.json file.
    url : str
        The URL of the JupyterLab instance where the notebook is going to be profiled.
    token : str
        The token to access the JupyterLab instance.
    kernel_name : str
        The name of the kernel to use for the notebook.
    headless : bool
        Whether to run in headless mode.
    max_wait_time : int
        Max time to wait after executing each cell (in seconds).
    log_screenshots : bool, optional
        Whether to log screenshots or not (default: False).
    save_metrics : bool, optional
        Whether to save profiling metrics to a CSV file (default: False).
    """
    logger.debug(
        "Generating and profiling notebooks with "
        f"Input Directory Path: {input_dir_path} -- "
        f"URL: {url} -- "
        f"Token: {token} -- "
        f"Kernel Name: {kernel_name} -- "
        f"Headless: {headless} -- "
        f"Max Wait Time: {max_wait_time} -- "
        f"Log Screenshots: {log_screenshots} -- "
        f"Save Metrics: {save_metrics}"
    )

    # Generate notebooks from template
    nb_input_paths: list[str] = generate_notebooks(input_dir_path=input_dir_path)

    # Set up the partial context for the `profile_notebook` call
    profiler_context: ProfilerContext = ProfilerContext(
        url=url,
        token=token,
        kernel_name=kernel_name,
        headless=headless,
        max_wait_time=max_wait_time,
    )

    if log_screenshots:
        # Create the directory(ies), if not yet created, in where the screenshots
        # will be saved. e.g.: <input_dir_path>/screenshots/<YYYY_MM_DD>/
        screenshots_dir_path: str = os_path.join(
            input_dir_path,
            "screenshots",
            strftime("%Y_%m_%d", gmtime()),
        )
        os.makedirs(screenshots_dir_path, exist_ok=True)
        profiler_context.screenshots_dir_path = screenshots_dir_path

    if save_metrics:
        # Create the directory(ies), if not yet created, in where the metrics
        # will be saved. e.g.: <input_dir_path>/metrics/<YYYY_MM_DD>/
        metrics_dir_path: str = os_path.join(
            input_dir_path,
            "metrics",
            strftime("%Y_%m_%d", gmtime()),
        )
        os.makedirs(metrics_dir_path, exist_ok=True)

        # Create the file in where the metrics will be saved.
        metrics_filename: str = f"metrics_{perf_counter_ns()}.csv"
        notebook_metrics_file_path: str = os_path.join(
            metrics_dir_path, f"notebook_{metrics_filename}"
        )
        open(notebook_metrics_file_path, "a").close()
        cell_metrics_file_path: str = os_path.join(
            metrics_dir_path, f"cell_{metrics_filename}"
        )
        open(cell_metrics_file_path, "a").close()
        profiler_context.notebook_metrics_file_path = notebook_metrics_file_path
        profiler_context.cell_metrics_file_path = cell_metrics_file_path

    # Set up progress bar arguments
    progress_bar_kwargs: dict[str, Any] = {
        "iterable": nb_input_paths,
        "desc": "Profiling Notebooks Progress",
        "position": 2,
        "leave": False,
    }

    # Profile each generated notebook
    with logging_redirect_tqdm([logger]):
        for nb_input_path in tqdm(**progress_bar_kwargs):
            logger.info(f"Profiling notebook: {nb_input_path}")
            profiler_context.nb_input_path = nb_input_path
            profile_notebook(profiler_context)
