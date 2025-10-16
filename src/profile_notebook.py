import logging
from os import makedirs
from os.path import basename, splitext
from os.path import join as os_path_join
from time import gmtime, strftime

from src.jupyter_lab_helper import JupyterLabHelper
from src.profiler import Profiler

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


async def profile_notebook(
    url: str,
    token: str,
    kernel_name: str,
    nb_input_path: str,
    headless: bool,
    screenshots_dir_path: str | None = None,
    metrics_dir_path: str | None = None,
    log_level: str = "INFO",
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
        Path to the input notebook to be profiled.
    headless : bool
        Whether to run in headless mode.
    screenshots_dir_path : str, optional
        Path to the directory to where screenshots will be stored, if not passed as
        an argument, screenshots will not be logged.
    metrics_dir_path : str, optional
        Path to the directory to where metrics will be stored, if not passed as
        an argument, metrics will not be saved to file.
    log_level : str, optional
        Set the logging level (default: INFO).
    Raises
    ------
    FileNotFoundError
        If the notebook file does not exist.
    requests.exceptions.RequestException
        If there is an error communicating with the JupyterLab server.
    Exception
        For any other unexpected errors.
    """
    # Set up logging
    logger.setLevel(log_level.upper())
    logger.debug(
        "Starting profiler with "
        f"URL: {url} -- "
        f"Token: {token} -- "
        f"Kernel Name: {kernel_name} -- "
        f"Input Notebook Path: {nb_input_path} -- "
        f"Headless: {headless} -- "
        f"Screenshots Dir Path: {screenshots_dir_path} -- "
        f"Metrics Dir Path: {metrics_dir_path} -- "
        f"Log Level: {log_level}"
    )

    # Initialize JupyterLab helper and clear any existing sessions
    jupyter_lab_helper: JupyterLabHelper = JupyterLabHelper(
        url=url,
        token=token,
        kernel_name=kernel_name,
        nb_input_path=nb_input_path,
    )
    await jupyter_lab_helper.clear_jupyterlab_sessions()
    await jupyter_lab_helper.restart_kernel()
    await jupyter_lab_helper.upload_notebook()

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

    # Start Selenium and run the profiler
    profiler: Profiler = Profiler(
        url=jupyter_lab_helper.notebook_url,
        headless=headless,
        nb_input_path=nb_input_path,
        screenshots_dir_path=screenshots_dir_path,
        metrics_dir_path=metrics_dir_path,
    )
    try:
        await profiler.setup()
        await profiler.run()
    finally:
        await profiler.close()
        # Clean up by deleting the uploaded notebook
        await jupyter_lab_helper.delete_notebook()
