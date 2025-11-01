import csv
import json
import logging
import random
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import cached_property
from io import BytesIO
from os.path import join as os_path_join
from time import perf_counter_ns
from typing import Any, ClassVar

from chromedriver_py import binary_path
from nbformat import NO_CONVERT, NotebookNode
from nbformat import read as nb_read
from PIL import Image
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from urllib3.exceptions import ReadTimeoutError

from src.executable_cell import ExecutableCell
from src.jupyterlab_helper import JupyterLabHelper
from src.metrics import SOURCE_METRIC_COMBO, CellExecutionStatus, NotebookMetrics
from src.utils import (
    MEGABYTE,
    explicit_wait,
    get_logger,
    get_notebook_cell_indexes_for_tag,
    get_notebook_parameters,
)
from src.viz_element import VizElement

# Initialize logger
logger: logging.Logger = get_logger()


@dataclass(eq=False)
class Profiler:
    """Class to profile a Jupyter notebook using Selenium."""

    kernel_name: str
    nb_input_path: str
    headless: bool
    max_wait_time: int
    screenshots_dir_path: str | None
    metrics_dir_path: str | None
    jupyterlab_helper: JupyterLabHelper
    driver: WebDriver | None = field(default=None, repr=False, init=False)
    viz_element: WebElement | None = field(default=None, repr=False, init=False)
    executable_cells: tuple[ExecutableCell, ...] = field(
        default_factory=tuple, repr=False, init=False
    )
    nb_params_dict: OrderedDict[str, Any] = field(
        default_factory=OrderedDict, repr=False, init=False
    )
    ui_network_throttling_value: float | None = field(
        default=None, repr=False, init=False
    )
    skip_profiling_cell_indexes: frozenset = field(
        default_factory=frozenset, repr=False, init=False
    )
    wait_for_viz_cell_indexes: frozenset = field(
        default_factory=frozenset, repr=False, init=False
    )
    metrics: NotebookMetrics = field(
        default_factory=NotebookMetrics, repr=False, init=False
    )

    # The width and height to set for the browser viewport to make the page really tall
    # to avoid scrollbars and scrolling issues
    VIEWPORT_SIZE: ClassVar[dict[str, int]] = {"width": 2000, "height": 20000}

    # Window size options
    WINDOW_SIZE_OPTION: ClassVar[str] = (
        f"--window-size={VIEWPORT_SIZE['width']},{VIEWPORT_SIZE['height']}"
    )

    # CSS style to disable the pulsing animation that can interfere
    # with screenshots taking
    PAGE_STYLE_TAG_CONTENT: ClassVar[str] = (
        ".viewer-label.pulse {animation: none !important;}"
    )

    # Selector for the notebook element
    NB_SELECTOR: ClassVar[str] = ".jp-Notebook"

    # Selector for all code cells in the notebook
    NB_CELLS_SELECTOR: ClassVar[str] = (
        ".jp-WindowedPanel-viewport>.lm-Widget.jp-Cell.jp-CodeCell.jp-Notebook-cell"
    )

    # The value of the cell tag marked as to skip metrics collections during profiling
    SKIP_PROFILING_CELL_TAG: ClassVar[str] = "skip_profiling"

    # The value of the cell tag marked as to wait for the viz
    WAIT_FOR_VIZ_CELL_TAG: ClassVar[str] = "wait_for_viz"

    # The value of the cell tag holding the notebook parameters
    PARAMETERS_CELL_TAG: ClassVar[str] = "parameters"

    # The parameter name holding the ui_network_throttling value
    UI_NETWORK_THROTTLING_PARAM: ClassVar[str] = "ui_network_throttling"

    # Selector for the jdaviz app viz element
    VIZ_ELEMENT_SELECTOR: ClassVar[str] = ".jdaviz.imviz"

    @cached_property
    def kernel_id(self) -> str:
        """
        Get the kernel id from the kernel name.
         Returns
        -------
        str
            The kernel id.
        """
        return self.jupyterlab_helper.get_kernel_id_from_name(self.kernel_name)

    def run_notebook(self) -> None:
        """
        Run the notebook profiling process.
        """
        logger.info("Starting profiling...")
        self.setup_profiler()
        self.setup_web_driver()
        self.go_to_notebook_url()
        self.setup_network_throttling()
        self.apply_custom_settings_to_ui()
        explicit_wait(5)  # Wait a bit to ensure the page is fully loaded
        self.build_executable_cells_from_ui()
        with logging_redirect_tqdm([logger]):
            self.execute_notebook_cells()
        self.metrics.compute()
        logger.info(str(self.metrics))
        self.save_metrics_to_csv()
        logger.info("Profiling completed.")

    def setup_profiler(self) -> None:
        """
        Set up the profiler by reading the notebook and extracting relevant information.
        """
        # Read the notebook file
        nb: NotebookNode = nb_read(self.nb_input_path, NO_CONVERT)
        # Extract cell indexes for skip_profiling and wait_for_viz tags
        self.skip_profiling_cell_indexes = frozenset(
            get_notebook_cell_indexes_for_tag(nb, self.SKIP_PROFILING_CELL_TAG)
        )
        self.wait_for_viz_cell_indexes = frozenset(
            get_notebook_cell_indexes_for_tag(nb, self.WAIT_FOR_VIZ_CELL_TAG)
        )
        # Extract notebook parameters
        self.nb_params_dict = get_notebook_parameters(nb, self.PARAMETERS_CELL_TAG)
        # Set total cells in performance metrics
        self.metrics.total_cells = len(nb.cells)

    def setup_web_driver(self) -> None:
        """
        Set up the Selenium browser and page.
        """
        options: Options = Options()
        # Set window size option
        options.add_argument(self.WINDOW_SIZE_OPTION)
        # Enable performance logging to capture network events
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        # Set headless mode if specified
        if self.headless:
            options.add_argument("--headless=new")

        # Launch the browser and create a new page
        self.driver: WebDriver = Chrome(
            options=options,
            service=ChromeService(executable_path=binary_path),
        )

    def go_to_notebook_url(self) -> None:
        """
        Navigate to the notebook URL and wait for it to load.
        """
        # Navigate to the notebook URL
        url: str = self.jupyterlab_helper.get_notebook_url(self.nb_input_path)
        logger.info(f"Navigating to {url}")
        self.driver.get(url)

        # Wait for the notebook to load
        self.wait_for_notebook_to_load()

    def setup_network_throttling(self) -> None:
        """
        Set up network throttling if the parameter is specified in the
        notebook parameters.
        """
        if not self.nb_params_dict.get(self.UI_NETWORK_THROTTLING_PARAM):
            logger.debug(
                "No network throttling parameter found, "
                "hence no network throttling applied."
            )
            return
        # If ui_network_throttling_value is not None, set up the network throttling
        download_throughput: int = self.nb_params_dict[self.UI_NETWORK_THROTTLING_PARAM]
        self.driver.set_network_conditions(
            offline=False,
            latency=0,
            download_throughput=download_throughput,
            # -1 means no throttling
            upload_throughput=-1,
        )
        logger.debug(
            f"Network throttling download_throughput={download_throughput} applied."
        )

    def apply_custom_settings_to_ui(self) -> None:
        """
        Apply custom settings to the notebook UI such as viewport size and CSS styles.
        """
        # Apply custom viewport size
        self.driver.set_window_size(*self.VIEWPORT_SIZE.values())
        logger.debug(f"Page viewport set to {self.VIEWPORT_SIZE}.")

        # Apply custom CSS styles
        self.driver.execute_script(
            "const style = document.createElement('style'); "
            f"style.innerHTML = `{self.PAGE_STYLE_TAG_CONTENT}`; "
            "document.head.appendChild(style);"
        )
        logger.debug("Page style added.")

    def build_executable_cells_from_ui(self) -> None:
        """
        Collect all code cells in the notebook from the loaded ui and return them
        as a list of ExecutableCell instances.
        """
        # Collect all code cells in the notebook
        nb_ui_cells: list[WebElement] = self.driver.find_elements(
            By.CSS_SELECTOR, self.NB_CELLS_SELECTOR
        )

        # Ensure the number of collected cells matches the expected total cells
        assert len(nb_ui_cells) == self.metrics.total_cells

        # Build ExecutableCell instances for each code cell
        self.executable_cells = tuple(
            ExecutableCell(
                cell=nb_ui_cell,
                index=i,
                max_wait_time=self.max_wait_time,
                skip_profiling=i in self.skip_profiling_cell_indexes,
                wait_for_viz=i in self.wait_for_viz_cell_indexes,
                profiler=self,
            )
            for i, nb_ui_cell in enumerate(nb_ui_cells, 1)
        )
        logger.info(
            f"Number of executable cells in the notebook: {len(self.executable_cells)}."
        )

    def execute_notebook_cells(self) -> None:
        """
        Loop through and execute each notebook cell, collecting performance metrics.
        """
        logger.info("Executing notebook cells...")

        # Execute each cell and collect metrics
        for ec in tqdm(
            self.executable_cells,
            desc="Notebook Cells Execution Progress",
            position=1,
            leave=False,
        ):
            try:
                # Execute the cell
                ec.execute()
            except Exception as e:
                logger.exception(f"Exception while executing cell {ec.index}: {e}")
            logging.info(f"Cell execution: {ec.metrics.execution_status}")
            # Collect metrics from the executed cell
            self.collect_executable_cell_metrics(ec)

            # If the cell execution did not complete successfully,
            # stop further executions
            if ec.metrics.execution_status != CellExecutionStatus.COMPLETED:
                break

            # Wait a bit to ensure stability before moving to the next cell
            explicit_wait(2)

    def collect_executable_cell_metrics(self, executable_cell: ExecutableCell) -> None:
        """
        Collect performance metrics from an executed cell and update the
        notebook performance metrics.
        Parameters
        ----------
        executable_cell : ExecutableCell
            The executed cell to collect metrics from.
        """
        self.metrics.executed_cells += 1
        # If the cell is marked to skip profiling, do not collect its metrics
        if executable_cell.skip_profiling:
            return
        self.metrics.profiled_cells += 1
        self.metrics.total_execution_time += (
            executable_cell.metrics.total_execution_time
        )
        self.metrics.client_total_data_received += (
            executable_cell.metrics.client_total_data_received
        )
        # Append source-metric combinations to the corresponding lists
        for s, m in SOURCE_METRIC_COMBO:
            getattr(self.metrics, f"{s}_{m}_list").extend(
                getattr(executable_cell.metrics, f"{s}_{m}_list")
            )

    def save_metrics_to_csv(self) -> None:
        """
        Save the profiling metrics to a CSV file.
        """
        # If no metrics directory path is provided, do not save metrics
        if self.metrics_dir_path is None:
            logger.debug("Not saving metrics.")
            return
        try:
            file_path_name: str = os_path_join(
                self.metrics_dir_path, f"{perf_counter_ns()}_metrics.csv"
            )
            # Set the first column as the notebook path
            notebook_path: dict[str, str] = {"notebook_path": self.nb_input_path}
            # Append notebook parameters with '_param' suffix
            nb_params_dict: dict[str, Any] = {
                f"{key}_param": value for key, value in self.nb_params_dict.items()
            }
            # Append performance metrics with '_metric' suffix
            metrics_dict: dict[str, Any] = {
                f"{key}_metric": value
                for key, value in asdict(
                    self.metrics,
                    dict_factory=NotebookMetrics.dict_factory,
                ).items()
            }
            # Combine all into a single OrderedDict for CSV writing
            data: list[OrderedDict[str, Any]] = [
                OrderedDict(**notebook_path, **nb_params_dict, **metrics_dict)
            ]
            # Write metrics to CSV file
            with open(file_path_name, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=list(data[0].keys()))
                writer.writeheader()
                writer.writerows(data)

            logger.info(f"Metrics saved successfully to {file_path_name}")
        except Exception as e:
            # In case of an exception: log it and move on (do not block!)
            logger.exception(f"An exception occurred during metrics saving: {e}")

    def wait_for_notebook_to_load(self) -> None:
        """
        Wait for the notebook to load by checking for the presence of the notebook
        element in the DOM.
        Retries a few times with exponential backoff in case of failure.
        """
        max_retries: int = 5
        # Initial delay in seconds with jitter
        retry_delay: float = 10 + random.uniform(0, 1)
        for attempt in range(max_retries):
            try:
                WebDriverWait(self.driver, timeout=retry_delay, poll_frequency=1).until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, self.NB_SELECTOR)
                    )
                )
                logger.debug("Notebook loaded.")
                return
            except TimeoutException:
                logger.warning(
                    "Error waiting for notebook to load, "
                    f"retrying... {attempt + 1}/{max_retries}."
                )
                # Double the delay for the next attempt
                retry_delay *= 2
                # Add jitter
                retry_delay += random.uniform(0, 1)
        raise TimeoutException("Notebook did not load in time after multiple attempts.")

    def close(self) -> None:
        """
        Close the Selenium driver.
        """
        self.driver is not None and hasattr(self.driver, "quit") and self.driver.quit()
        logger.debug("Driver closed.")

    def get_client_data_received(
        self, timestamp_start: datetime, timestamp_end: datetime
    ) -> float:
        """
        Get the total data received between two timestamps from the
        client performance logs.
        Parameters
        ----------
        timestamp_start : datetime
            The start timestamp.
        timestamp_end : datetime
            The end timestamp.
        Returns
        -------
        float
            The total data received in MB.
        """
        data_received: float = 0
        try:
            performance_entries: dict[str, Any] = self.driver.get_log("performance")
        except ReadTimeoutError:
            logger.warning("ReadTimeoutError when getting performance logs.")
            return data_received
        for entry in performance_entries:
            timestamp_entry: datetime = datetime.fromtimestamp(
                entry["timestamp"] / 1000
            )
            if timestamp_start < timestamp_entry < timestamp_end:
                message: dict[str, Any] = json.loads(entry.get("message", {})).get(
                    "message", {}
                )
                if message.get("method", "") == "Network.dataReceived":
                    data_received += message.get("params", {}).get("dataLength", 0)
        return data_received / MEGABYTE

    def detect_viz_element(self) -> None:
        """
        Detect the viz element based on the CSS classes given to the viz app.
        """
        viz_element: WebElement = self.driver.find_element(
            By.CSS_SELECTOR, self.VIZ_ELEMENT_SELECTOR
        )
        if viz_element:
            self.viz_element: VizElement = VizElement(
                element=viz_element, profiler=self
            )
            logger.debug("Viz element detected and assigned.")

    def log_screenshots(self, cell_index: int, screenshots: list[bytes]) -> None:
        """
        Save screenshots of a cell to a determined directory path.
        Parameters
        ----------
        cell_index : int
            The index of the cell.
        screenshots : list[bytes]
            The list of screenshot (in bytes) to save.
        """
        try:
            if self.screenshots_dir_path is None:
                logger.debug("Not logging screenshots.")
                return

            # Log screenshots
            logger.debug("Logging screenshots...")

            file_path_name: str = os_path_join(
                self.screenshots_dir_path, f"{perf_counter_ns()}_cell{cell_index}"
            )

            for i, screenshot in enumerate(screenshots):
                # Save first screenshot as PNG
                Image.open(BytesIO(screenshot)).save(f"{file_path_name}_{i}.png")

            logger.debug("Screenshots logged.")

        except Exception as e:
            # In case of an exception: log it and move on (do not block!)
            logger.exception(f"An exception occurred during screenshots logging: {e}")

    def get_current_kernel_pid(self) -> int:
        """
        Get the PID of the current process running on the kernel.
        Returns
        -------
        int
            The PID of the current process running on the kernel.
        """
        return self.jupyterlab_helper.get_current_kernel_pid(self.kernel_id)

    def get_kernel_usage(self) -> dict[str, Any]:
        """
        Get the current resource usage of the kernel.
        Returns
        -------
        dict[str, Any]
            The current resource usage of the kernel.
        """
        return self.jupyterlab_helper.get_kernel_usage(self.kernel_id)
