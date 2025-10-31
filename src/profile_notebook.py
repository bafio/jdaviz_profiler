import logging
from os import makedirs
from os.path import basename, splitext
from os.path import join as os_path_join
from time import gmtime, strftime

from src.jupyterlab_helper import JupyterLabHelper
from src.profiler import Profiler
from src.utils import get_logger

# Initialize logger
logger: logging.Logger = get_logger()


def profile_notebook(
    url: str,
    token: str,
    kernel_name: str,
    nb_input_path: str,
    headless: bool,
    max_wait_time: int,
    screenshots_dir_path: str | None = None,
    metrics_dir_path: str | None = None,
) -> None:
    """
    Profile the notebook at the specified URL using Selenium.
    Parameters
    ----------
    url : str
        The URL of the JupyterLab instance where the notebook is going to be profiled.
    token : str
        The token to access the JupyterLab instance.
    kernel_name : str
        The name of the kernel to use for the notebook.
    nb_input_path : str
        Path of the input notebook to be profiled.
    headless : bool
        Whether to run in headless mode.
    max_wait_time : int
        Max time to wait after executing each cell (in minutes).
    screenshots_dir_path : str, optional
        Path to the directory to where screenshots will be stored, if not passed as
        an argument, screenshots will not be logged.
    metrics_dir_path : str, optional
        Path to the directory to where metrics will be stored, if not passed as
        an argument, metrics will not be saved to file.
    Raises
    ------
    FileNotFoundError
        If the notebook file does not exist.
    requests.exceptions.RequestException
        If there is an error communicating with the JupyterLab server.
    Exception
        For any other unexpected errors.
    """
    logger.debug(
        "Starting profiler with "
        f"URL: {url} -- "
        f"Token: {token} -- "
        f"Kernel Name: {kernel_name} -- "
        f"Input Notebook Path: {nb_input_path} -- "
        f"Headless: {headless} -- "
        f"Max Wait Time: {max_wait_time} -- "
        f"Screenshots Dir Path: {screenshots_dir_path} -- "
        f"Metrics Dir Path: {metrics_dir_path}"
    )

    if screenshots_dir_path:
        # Create the directory(ies), if not yet created, in where the screenshots
        # will be saved. e.g.: <screenshots_dir_path>/<nb_filename_wo_ext>/<YYYY_MM_DD>/
        screenshots_dir_path = os_path_join(
            screenshots_dir_path,
            splitext(basename(nb_input_path))[0],
            strftime("%Y_%m_%d", gmtime()),
        )
        makedirs(screenshots_dir_path, exist_ok=True)

    if metrics_dir_path:
        # Create the directory(ies), if not yet created, in where the metrics
        # will be saved. e.g.: <metrics_dir_path>/<nb_filename_wo_ext>/<YYYY_MM_DD>/
        metrics_dir_path = os_path_join(
            metrics_dir_path,
            splitext(basename(nb_input_path))[0],
            strftime("%Y_%m_%d", gmtime()),
        )
        makedirs(metrics_dir_path, exist_ok=True)

    # Initialize JupyterLab helper
    jupyterlab_helper: JupyterLabHelper = JupyterLabHelper(url=url, token=token)

    # Prepare JupyterLab environment
    jupyterlab_helper.clear_all_jupyterlab_sessions()
    jupyterlab_helper.restart_kernel(kernel_name)
    jupyterlab_helper.upload_notebook(nb_input_path)

    try:
        # Start Selenium and run the profiler
        profiler: Profiler = Profiler(
            kernel_name=kernel_name,
            nb_input_path=nb_input_path,
            headless=headless,
            # Convert minutes to seconds
            max_wait_time=max_wait_time * 60,
            screenshots_dir_path=screenshots_dir_path,
            metrics_dir_path=metrics_dir_path,
            jupyterlab_helper=jupyterlab_helper,
        )
        profiler.run_notebook()
    finally:
        profiler.close()
        # Clean up by deleting the uploaded notebook
        notebook_filename = jupyterlab_helper.get_notebook_filename(nb_input_path)
        jupyterlab_helper.delete_notebook(notebook_filename)
