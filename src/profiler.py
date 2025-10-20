import csv
import json
import logging
import random
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from io import BytesIO
from os.path import join as os_path_join
from time import perf_counter_ns, sleep
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

from src.executable_cell import ExecutableCell
from src.performance_metrics import NotebookPerformanceMetrics
from src.utils import MEGABYTE, parse_assignments
from src.viz_element import VizElement

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


@dataclass(eq=False)
class Profiler:
    """Class to profile a Jupyter notebook using Selenium."""

    url: str
    headless: bool
    nb_input_path: str
    screenshots_dir_path: str | None = field(default=None, repr=True)
    metrics_dir_path: str | None = field(default=None, repr=True)
    driver: WebDriver | None = field(default=None, repr=False)
    viz_element: WebElement | None = field(default=None, repr=False)
    executable_cells: tuple[ExecutableCell, ...] = field(
        default_factory=tuple, repr=False
    )
    nb_params_dict: OrderedDict[str, Any] = field(
        default_factory=OrderedDict, repr=False
    )
    ui_network_throttling_value: float | None = field(default=None, repr=False)
    skip_profiling_cell_indexes: frozenset = field(
        default_factory=frozenset, repr=False
    )
    wait_for_viz_cell_indexes: frozenset = field(default_factory=frozenset, repr=False)
    performance_metrics: NotebookPerformanceMetrics = field(
        default_factory=NotebookPerformanceMetrics, repr=False
    )

    # The width and height to set for the browser viewport to make the page really tall
    # to avoid scrollbars and scrolling issues
    VIEWPORT_SIZE: ClassVar[dict[str, int]] = {"width": 1600, "height": 20000}

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

    def setup(self) -> None:
        """
        Set up the Selenium browser and page.
        """
        # Inspect the notebook file to find "skip_profiling" cells and
        # "network_bandwith" value
        self.inspect_notebook()

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

        # Navigate to the notebook URL
        logger.info(f"Navigating to {self.url}")
        self.driver.get(self.url)

        # Wait for the notebook to load
        self.wait_for_notebook_to_load()

        # If ui_network_throttling_value is not None, set up the network throttling
        if self.nb_params_dict.get(self.UI_NETWORK_THROTTLING_PARAM) is not None:
            self.driver.set_network_conditions(
                offline=False,
                latency=0,
                download_throughput=self.nb_params_dict[
                    self.UI_NETWORK_THROTTLING_PARAM
                ],
                upload_throughput=-1,  # -1 means no throttling
            )

        # Apply custom viewport size
        self.driver.set_window_size(*self.VIEWPORT_SIZE.values())
        logger.debug("Page viewport set")

        # Apply custom CSS styles
        self.driver.execute_script(
            "const style = document.createElement('style'); "
            f"style.innerHTML = `{self.PAGE_STYLE_TAG_CONTENT}`; "
            "document.head.appendChild(style);"
        )
        logger.debug("Page style added")

    def run(self) -> None:
        """
        Run the profiling process.
        """
        # Wait a bit to ensure the page is fully loaded
        sleep_time: float = 5
        logger.info(f"Sleeping {sleep_time} seconds to ensure full load...")
        sleep(sleep_time)

        # Collect cells to execute
        self.collect_executable_cells()

        # Start profiling
        logger.info("Starting profiling...")

        sleep_time = 2
        # Execute each cell and wait for outputs
        for executable_cell in self.executable_cells:
            executable_cell.execute()
            # Wait a bit to ensure stability before moving to the next cell
            logger.info(f"Sleeping {sleep_time} seconds to ensure stability...")
            sleep(sleep_time)

            if not executable_cell.skip_profiling:
                self.performance_metrics.total_execution_time += (
                    executable_cell.performance_metrics.total_execution_time
                )
                self.performance_metrics.client_average_cpu_usage_list.append(
                    executable_cell.performance_metrics.client_average_cpu_usage
                )
                self.performance_metrics.client_average_memory_usage_list.append(
                    executable_cell.performance_metrics.client_average_memory_usage
                )
                self.performance_metrics.client_total_data_received += (
                    executable_cell.performance_metrics.client_total_data_received
                )

        # Compute performance metrics
        self.performance_metrics.compute_metrics()

        # Log the performance metrics
        logger.info(str(self.performance_metrics))

        # save the profiling metrics to a csv file
        self.save_performance_metrics_to_csv()

        logger.info("Profiling completed.")

    def get_data_received(
        self, timestamp_start: datetime, timestamp_end: datetime
    ) -> float:
        """
        Get the total data received between two timestamps from the performance logs.
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
        for entry in self.driver.get_log("performance"):
            timestamp_entry = datetime.fromtimestamp(entry["timestamp"] / 1000)
            if timestamp_start < timestamp_entry < timestamp_end:
                message: dict[str, Any] = json.loads(entry.get("message", {})).get(
                    "message", {}
                )
                if message.get("method", "") == "Network.dataReceived":
                    data_received += message.get("params", {}).get("dataLength", 0)
        return data_received / MEGABYTE  # in MB

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
            logger.debug("Viz element detected and assigned")

    def save_performance_metrics_to_csv(self) -> None:
        """
        Save the profiling metrics to a CSV file.
        """
        try:
            if self.metrics_dir_path is None:
                logger.debug("Not saving metrics")
                return
            file_path_name: str = os_path_join(
                self.metrics_dir_path, f"{perf_counter_ns()}_metrics.csv"
            )
            notebook_path: dict[str, str] = {"notebook_path": self.nb_input_path}
            nb_params_dict: dict[str, Any] = {
                f"{key}_param": value for key, value in self.nb_params_dict.items()
            }
            metrics_dict: dict[str, Any] = {
                f"{key}_metric": value
                for key, value in asdict(
                    self.performance_metrics,
                    dict_factory=NotebookPerformanceMetrics.dict_factory,
                ).items()
            }
            data: list[OrderedDict[str, Any]] = [
                OrderedDict(**notebook_path, **nb_params_dict, **metrics_dict)
            ]
            fieldnames: list[str] = list(data[0].keys())
            with open(file_path_name, "w", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)

            logger.info(f"Metrics saved successfully to {file_path_name}")
        except Exception as e:
            # In case of an exception: log it and move on (do not block!)
            logger.exception(f"An exception occurred during metrics saving: {e}")

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
                logger.debug("Not logging screenshots")
                return

            # Log screenshots
            logger.debug("Logging screenshots...")

            file_path_name: str = os_path_join(
                self.screenshots_dir_path, f"{perf_counter_ns()}_cell{cell_index}"
            )

            for i, screenshot in enumerate(screenshots):
                # Save first screenshot as PNG
                Image.open(BytesIO(screenshot)).save(f"{file_path_name}_{i}.png")

            logger.debug("Screenshots logged")

        except Exception as e:
            # In case of an exception: log it and move on (do not block!)
            logger.exception(f"An exception occurred during screenshots logging: {e}")

    def collect_executable_cells(self) -> list[ExecutableCell]:
        """
        Collect all code cells in the notebook and return them as a list of
        ExecutableCell instances.
        Returns
        -------
        list[ExecutableCell]
            List of ExecutableCell instances representing the code cells
            in the notebook.
        """
        # Collect all code cells in the notebook
        nb_cells: list[WebElement] = self.driver.find_elements(
            By.CSS_SELECTOR, self.NB_CELLS_SELECTOR
        )

        # Store cells in an ordered dictionary with their index
        self.executable_cells = tuple(
            ExecutableCell(
                cell=cell,
                index=i,
                skip_profiling=i in self.skip_profiling_cell_indexes,
                wait_for_viz=i in self.wait_for_viz_cell_indexes,
                profiler=self,
            )
            for i, cell in enumerate(nb_cells, 1)
        )
        logger.info(f"Number of cells in the notebook: {len(self.executable_cells)}")

    def inspect_notebook(self) -> None:
        """
        Inspect the notebook file to find "skip_profiling" cells and
        "network_bandwith" value.
        """
        nb: NotebookNode = nb_read(self.nb_input_path, NO_CONVERT)
        self.collect_cells_metadata(nb)
        self.extract_nb_parameters_as_ordered_dict(nb)
        self.performance_metrics.total_cells = len(nb.cells)
        self.performance_metrics.profiled_cells = (
            self.performance_metrics.total_cells - len(self.skip_profiling_cell_indexes)
        )

    def collect_cells_metadata(self, notebook: NotebookNode) -> None:
        """
        Collect the indexes of cells marked with specific tags, such as:
        - SKIP_PROFILING_CELL_TAG
        - WAIT_FOR_VIZ_CELL_TAG
        Parameters
        ----------
        notebook : NotebookNode
            The notebook to read from.
        """
        skip_profiling_cell_indexes: list[int] = []
        wait_for_viz_cell_indexes: list[int] = []
        for cell_index, cell in enumerate(notebook.cells, 1):
            # Get the nb cell tags
            tags: list[str] = cell.metadata.get("tags", [])
            if self.SKIP_PROFILING_CELL_TAG in tags:
                skip_profiling_cell_indexes.append(cell_index)
            if self.WAIT_FOR_VIZ_CELL_TAG in tags:
                wait_for_viz_cell_indexes.append(cell_index)

        self.skip_profiling_cell_indexes = frozenset(skip_profiling_cell_indexes)
        logger.debug(
            "Profiling metrics for the following cells "
            f"{tuple(self.skip_profiling_cell_indexes)} will not be collected."
        )
        self.wait_for_viz_cell_indexes = frozenset(wait_for_viz_cell_indexes)
        logger.debug(
            "The following cells "
            f"{tuple(self.wait_for_viz_cell_indexes)} will only wait for "
            "viz changes (if viz is set)."
        )

    def extract_nb_parameters_as_ordered_dict(self, notebook: NotebookNode) -> None:
        """
        Collect the notebook parameters from the cell tagged as parameters and
        store them as an ordered dictionary.
        Parameters
        ----------
        notebook : NotebookNode
            The notebook to read from.
        """
        for cell in notebook.cells:
            # Get the nb cell tagged with the specified cell_tag
            tags: list[str] = cell.metadata.get("tags", [])
            if self.PARAMETERS_CELL_TAG in tags:
                cell_source: str = cell.source or ""
                self.nb_params_dict = parse_assignments(cell_source)
                logger.debug(f"Notebook parameters found: {self.nb_params_dict}")
                return
        logger.debug("No notebook parameters found.")

    def wait_for_notebook_to_load(self) -> None:
        """
        Wait for the notebook to load by checking for the presence of the notebook
        element in the DOM.
        Retries a few times with exponential backoff in case of failure.
        """
        max_retries: int = 5
        retry_delay: float = 10 + random.uniform(
            0, 1
        )  # Initial delay in seconds with jitter
        for attempt in range(max_retries):
            try:
                WebDriverWait(self.driver, timeout=retry_delay, poll_frequency=1).until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, self.NB_SELECTOR)
                    )
                )
                logger.debug("Notebook loaded")
                return
            except TimeoutException:
                logger.warning(
                    "Error waiting for notebook to load, "
                    f"retrying... {attempt + 1}/{max_retries}"
                )
                retry_delay *= 2  # Double the delay for the next attempt
                retry_delay += random.uniform(0, 1)  # Add jitter
        raise TimeoutException("Notebook did not load in time after multiple attempts.")

    def close(self) -> None:
        """
        Close the Selenium driver.
        """
        self.driver.quit()
        logger.debug("Driver closed")
