#!/usr/bin/env python3
"""
Uses Selenium to launch and interact with JupyterLab, executing each notebook cell and
recording performance metrics.

Usage:
$> python profiler.py --url <JupyterLab URL> --token <API Token> \
    --kernel_name <kernel name> --nb_input_path <notebook path>
"""

import argparse
import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import BytesIO
from os import linesep, makedirs
from os.path import basename, splitext
from os.path import join as os_path_join
from time import gmtime, perf_counter_ns, strftime, time

import nbformat
import psutil
from chromedriver_py import binary_path
from PIL import Image
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from jupyter_lab_helper import JupyterLabHelper

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

KILOBYTE = 1024
MEGABYTE = 1024 * KILOBYTE


@dataclass(eq=False, frozen=True)
class VizElement:
    """Class representing the viz element in a Jupyter notebook."""

    element: WebElement
    profiler: "Profiler"

    # Seconds to wait during the screenshots taking
    WAIT_TIME_DURING_SCREENSHOTS = 0.5

    async def is_stable(self, cell_index: int) -> bool:
        """
        Check if the viz element is stable (i.e., not changing).
        Returns
        -------
        bool
            True if the viz element is stable, False otherwise.
        """
        if self.element is None:
            logger.debug("Viz element element is None, cannot be stable")
            return False

        # Take a screenshot of the viz element
        screenshot_before = self.element.screenshot_as_png

        # Wait a short period before taking another screenshot
        await asyncio.sleep(self.WAIT_TIME_DURING_SCREENSHOTS)

        # Take another screenshot of the viz element
        screenshot_after = self.element.screenshot_as_png

        # Log screenshots
        await self.profiler.log_screenshots(
            cell_index, [screenshot_before, screenshot_after]
        )

        # Compare the two screenshots
        screenshots_are_the_same = screenshot_before == screenshot_after
        logger.debug(f"screenshots_are_the_same: {screenshots_are_the_same}")
        return screenshots_are_the_same


@dataclass
class PerformanceMetrics:
    """Class representing performance metrics."""

    total_execution_time: float = 0
    average_cpu_usage: float = 0
    average_memory_usage: float = 0
    total_data_received: float = 0
    average_cpu_usage_list: list[float] = field(default_factory=list, repr=False)
    average_memory_usage_list: list[float] = field(default_factory=list, repr=False)

    def compute_metrics(self) -> None:
        """Compute the average CPU and memory usage from the recorded lists."""
        if self.average_cpu_usage_list:
            self.average_cpu_usage = sum(self.average_cpu_usage_list) / len(
                self.average_cpu_usage_list
            )
        if self.average_memory_usage_list:
            self.average_memory_usage = sum(self.average_memory_usage_list) / len(
                self.average_memory_usage_list
            )

    def __str__(self) -> str:
        return (
            f"Total Execution Time: {self.total_execution_time:.2f} seconds. "
            f"Average CPU usage: {self.average_cpu_usage:.2f}%. "
            f"Average Memory usage: {self.average_memory_usage:.2f}%. "
            f"Total Data received: {self.total_data_received:.2f} MB."
        )


@dataclass
class CellPerformanceMetrics(PerformanceMetrics):
    """Class representing cell performance metrics."""

    cell_index: int = 0

    def __str__(self) -> str:
        return f"Cell {self.cell_index}: {super().__str__()}"


@dataclass
class NotebookPerformanceMetrics(PerformanceMetrics):
    """Class representing notebook performance metrics."""

    total_cells: int = 0
    profiled_cells: int = 0

    def __str__(self) -> str:
        return (
            f"Notebook with {self.total_cells} cells, "
            f"of which {self.profiled_cells} were profiled. "
            f"{super().__str__()}"
        )


@dataclass
class ExecutableCell:
    """Class representing an executable cell in a Jupyter notebook."""

    cell: WebElement
    index: int
    skip_profiling: bool
    wait_for_viz: bool
    profiler: "Profiler"
    performance_metrics: CellPerformanceMetrics = field(
        default_factory=CellPerformanceMetrics, repr=False
    )

    # Seconds to wait after the execution command if no need to
    # collect profiling metrics
    SECONDS_TO_WAIT_IF_SKIP_PROFILING = 2.5

    # Seconds to wait before checking the executed cell outputs
    WAIT_TIME_BEFORE_OUTPUT_CHECK = 0.5

    # Selector for all output cells in a code cell
    OUTPUT_CELLS_SELECTOR = ".lm-Widget.lm-Panel.jp-Cell-outputWrapper"

    # Selector for all text output cells in a code cell
    OUTPUT_CELLS_TEXT_SELECTOR = (
        ".lm-Widget.jp-RenderedText.jp-mod-trusted.jp-OutputArea-output"
    )

    # Regex to identify the cell output containing the `DONE` text output
    OUTPUT_CELL_DONE_REGEX = r"^.*(?P<DONE>DONE).*$"

    def __post_init__(self):
        self.performance_metrics.cell_index = self.index

    async def look_for_done_statement(self) -> bool:
        """
        Look for the DONE statement in the output cells of the cell.
        Returns
        -------
        bool
            True if the DONE statement is found, False otherwise.
        """
        output_cells = self.cell.find_elements(
            By.CSS_SELECTOR, self.OUTPUT_CELLS_SELECTOR
        )
        if not output_cells:
            logger.debug(f"Cell {self.index} has no output cells yet, waiting...")
            return False
        for output_cell in output_cells:
            text_output_cells = output_cell.find_elements(
                By.CSS_SELECTOR, self.OUTPUT_CELLS_TEXT_SELECTOR
            )
            logger.debug(f"Found {len(text_output_cells)} text output cells")
            if not text_output_cells:
                continue
            output_txt = linesep.join(
                [text_output_cell.text for text_output_cell in text_output_cells]
            )
            match = re.search(self.OUTPUT_CELL_DONE_REGEX, output_txt, re.MULTILINE)
            if match and match.group("DONE"):
                logger.info(f"Cell {self.index} DONE statement found!")
                return True
        return False

    async def compute_performance_metrics(self) -> None:
        """
        Compute profiling metrics for the cell.
        """
        if self.skip_profiling:
            self.performance_metrics.total_execution_time = 0
            self.performance_metrics.average_cpu_usage = 0
            self.performance_metrics.average_memory_usage = 0
            self.performance_metrics.total_data_received = 0
            return

        timestamp_end = datetime.now()
        timestamp_start = timestamp_end - timedelta(
            seconds=self.performance_metrics.total_execution_time
        )
        self.performance_metrics.total_data_received = (
            await self.profiler.get_data_received(timestamp_start, timestamp_end)
        )
        self.performance_metrics.compute_metrics()

    async def execute(self) -> None:
        """
        Execute the cell and collect profiling metrics.
        """
        try:
            logger.info(f"Executing cell {self.index}")

            # Initialize variables to track the viz element and elapsed time
            viz_is_stable = False
            start_time = time()

            # Click on the cell
            self.cell.click()
            # Execute the cell
            self.cell.send_keys(Keys.SHIFT, Keys.ENTER)

            while True:
                # Capture CPU usage
                self.performance_metrics.average_cpu_usage_list.append(
                    psutil.cpu_percent(interval=self.WAIT_TIME_BEFORE_OUTPUT_CHECK)
                )
                # Capture memory usage
                self.performance_metrics.average_memory_usage_list.append(
                    psutil.virtual_memory().percent
                )

                # Wait a bit before checking again
                await asyncio.sleep(self.WAIT_TIME_BEFORE_OUTPUT_CHECK)

                # Check if the DONE statement
                done_found = await self.look_for_done_statement()
                if not done_found:
                    logger.debug(f"Cell {self.index} DONE statement not found yet...")
                    continue

                logger.debug(f"Cell {self.index} DONE statement found, moving on...")

                if not self.wait_for_viz:
                    logger.debug(
                        f"Cell {self.index} is not tagged as to wait for viz changes, "
                        "moving on..."
                    )
                    # Save time elapsed
                    self.performance_metrics.total_execution_time = time() - start_time
                    break

                logger.debug(f"Cell {self.index} is tagged as to wait for viz changes.")
                if self.profiler.viz_element:
                    # If we have the viz element, check if it's stable
                    logger.debug(
                        "We already have the viz element, checking if it's stable..."
                    )
                    viz_is_stable = await self.profiler.viz_element.is_stable(
                        self.index
                    )
                else:
                    # Look for the viz element in the page
                    logger.debug("Looking for the viz element in the page...")
                    await self.profiler.detect_viz_element()

                if viz_is_stable:
                    logger.debug(
                        f"Cell {self.index} viz element is stable, moving on..."
                    )
                    # Save time elapsed
                    self.performance_metrics.total_execution_time = time() - start_time
                    break

            # Capture CPU usage
            self.performance_metrics.average_cpu_usage_list.append(
                psutil.cpu_percent(interval=self.WAIT_TIME_BEFORE_OUTPUT_CHECK)
            )
            # Capture memory usage
            self.performance_metrics.average_memory_usage_list.append(
                psutil.virtual_memory().percent
            )

            # Compute performance metrics
            await self.compute_performance_metrics()

            # Log the performance metrics
            logger.info(str(self.performance_metrics))

        except Exception as e:
            logger.exception(
                f"An error occurred while executing cell {self.index}: {e}"
            )


@dataclass
class Profiler:
    """Class to profile a Jupyter notebook using Selenium."""

    url: str
    headless: bool
    nb_input_path: str
    screenshots_dir_path: str | None = None
    driver: WebDriver | None = field(default=None, repr=False)
    viz_element: WebElement | None = field(default=None, repr=False)
    executable_cells: tuple = field(default_factory=tuple, repr=False)
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
    VIEWPORT_SIZE = {"width": 1600, "height": 20000}

    # Window size options
    WINDOW_SIZE_OPTION = (
        f"--window-size={VIEWPORT_SIZE['width']},{VIEWPORT_SIZE['height']}"
    )

    # CSS style to disable the pulsing animation that can interfere
    # with screenshots taking
    PAGE_STYLE_TAG_CONTENT = ".viewer-label.pulse {animation: none !important;}"

    # Selector for the notebook element
    NB_SELECTOR = ".jp-Notebook"

    # Selector for all code cells in the notebook
    NB_CELLS_SELECTOR = (
        ".jp-WindowedPanel-viewport>.lm-Widget.jp-Cell.jp-CodeCell.jp-Notebook-cell"
    )

    # The value of the cell tag marked as to skip metrics collections during profiling
    SKIP_PROFILING_CELL_TAG = "skip_profiling"

    # The value of the cell tag marked as to wait for the viz
    WAIT_FOR_VIZ_CELL_TAG = "wait_for_viz"

    # The value of the cell tag holding the notebook parameters
    PARAMETERS_CELL_TAG = "parameters"

    # The parameter name holding the ui_network_throttling value
    UI_NETWORK_THROTTLING_PARAM = "ui_network_throttling"

    # The regex to find the ui_network_throttling value
    UI_NETWORK_THROTTLING_REGEX = (
        rf".*{UI_NETWORK_THROTTLING_PARAM}\s*\=\s*(?P<value>[-+]?\d+).*"
    )

    # Selector for the jdaviz app viz element
    VIZ_ELEMENT_SELECTOR = ".jdaviz.imviz"

    async def setup(self) -> None:
        """
        Set up the Selenium browser and page.
        """
        # Inspect the notebook file to find "skip_profiling" cells and
        # "network_bandwith" value
        await self.inspect_notebook()

        options = Options()
        # Set window size option
        options.add_argument(self.WINDOW_SIZE_OPTION)
        # Enable performance logging to capture network events
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        # Set headless mode if specified
        if self.headless:
            options.add_argument("--headless=new")

        # Launch the browser and create a new page
        self.driver = Chrome(
            options=options,
            service=ChromeService(executable_path=binary_path),
        )

        # Navigate to the notebook URL
        logger.info(f"Navigating to {self.url}")
        self.driver.get(self.url)

        # Wait for the notebook to load
        await self.wait_for_notebook_to_load()

        # If ui_network_throttling_value is not None, set up the network throttling
        if self.ui_network_throttling_value is not None:
            self.driver.set_network_conditions(
                offline=False,
                latency=0,
                download_throughput=self.ui_network_throttling_value,
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

    async def run(self) -> None:
        """
        Run the profiling process.
        """
        # Wait a bit to ensure the page is fully loaded
        sleep_time = 5
        logger.info(f"Sleeping {sleep_time} seconds to ensure full load...")
        await asyncio.sleep(sleep_time)

        # Collect cells to execute
        await self.collect_executable_cells()

        # Start profiling
        logger.info("Starting profiling...")

        sleep_time = 2
        # Execute each cell and wait for outputs
        for executable_cell in self.executable_cells:
            await executable_cell.execute()
            # Wait a bit to ensure stability before moving to the next cell
            logger.info(f"Sleeping {sleep_time} seconds to ensure stability...")
            await asyncio.sleep(sleep_time)

            if not executable_cell.skip_profiling:
                self.performance_metrics.total_execution_time += (
                    executable_cell.performance_metrics.total_execution_time
                )
                self.performance_metrics.average_cpu_usage_list.append(
                    executable_cell.performance_metrics.average_cpu_usage
                )
                self.performance_metrics.average_memory_usage_list.append(
                    executable_cell.performance_metrics.average_memory_usage
                )
                self.performance_metrics.total_data_received += (
                    executable_cell.performance_metrics.total_data_received
                )

        # Compute performance metrics
        self.performance_metrics.compute_metrics()

        # Log the performance metrics
        logger.info(str(self.performance_metrics))

        # # # save the profiling metrics to a csv file
        # # await self.save_performance_metrics()

        logger.info("Profiling completed.")

    # async def save_performance_metrics(self) -> None:
    #     """
    #     Save the profiling metrics to a CSV file.
    #     """
    #     # # Collect performance metrics
    #     # await self.collect_performance_metrics()

    #     csv_file_path = f"{splitext(self.nb_input_path)[0]}_profiling_metrics.csv"
    #     logger.info(f"Saving profiling metrics to {csv_file_path}...")
    #     with open(csv_file_path, "w") as f:
    #         # Write header
    #         f.write(
    #             "cell_index,skip_profiling,wait_for_viz,execution_time,cpu_usage,"
    #             "memory_usage,data_received\n"
    #         )
    #         # Write metrics for each cell
    #         for executable_cell in self.executable_cells:
    #             f.write(
    #                 f"{executable_cell.index},{executable_cell.skip_profiling},"
    #                 f"{executable_cell.wait_for_viz},{executable_cell.execution_time},"
    #                 f"{executable_cell.cpu_usage},{executable_cell.memory_usage},"
    #                 f"{executable_cell.data_received}\n"
    #             )

    async def get_data_received(
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
        data_received = 0
        for entry in self.driver.get_log("performance"):
            timestamp_entry = datetime.fromtimestamp(entry["timestamp"] / 1000)
            if timestamp_start < timestamp_entry < timestamp_end:
                message = json.loads(entry.get("message", {})).get("message", {})
                if message.get("method", "") == "Network.dataReceived":
                    data_received += message.get("params", {}).get("dataLength", 0)
        return data_received / MEGABYTE  # in MB

    async def detect_viz_element(self) -> None:
        """
        Detect the viz element based on the CSS classes given to the viz app.
        """
        viz_element = self.driver.find_element(
            By.CSS_SELECTOR, self.VIZ_ELEMENT_SELECTOR
        )
        if viz_element:
            self.viz_element = VizElement(element=viz_element, profiler=self)
            logger.debug("Viz element detected and assigned")

    async def log_screenshots(self, cell_index: int, screenshots: list[bytes]) -> None:
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

            file_path_name = os_path_join(
                self.screenshots_dir_path, f"{perf_counter_ns()}_cell{cell_index}"
            )

            for i, screenshot in enumerate(screenshots):
                # Save first screenshot
                image_file_path_name = f"{file_path_name}_{i}.png"
                image = Image.open(BytesIO(screenshot))
                image.save(image_file_path_name)

            logger.debug("Screenshots logged")

        except Exception as e:
            # In case of an exception: log it and move on (do not block!)
            logger.exception(f"An exception occurred during screenshots logging: {e}")

    async def collect_executable_cells(self) -> list[ExecutableCell]:
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
        nb_cells = self.driver.find_elements(By.CSS_SELECTOR, self.NB_CELLS_SELECTOR)

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

    async def inspect_notebook(self) -> None:
        """
        Inspect the notebook file to find "skip_profiling" cells and
        "network_bandwith" value.
        """
        nb = nbformat.read(self.nb_input_path, nbformat.NO_CONVERT)
        await self.collect_cells_metadata(nb)
        await self.get_ui_network_throttling_value(nb)
        self.performance_metrics.total_cells = len(nb.cells)
        self.performance_metrics.profiled_cells = (
            self.performance_metrics.total_cells - len(self.skip_profiling_cell_indexes)
        )

    async def collect_cells_metadata(self, notebook: nbformat.NotebookNode) -> None:
        """
        Collect the indexes of cells marked with specific tags, such as:
        - SKIP_PROFILING_CELL_TAG
        - WAIT_FOR_VIZ_CELL_TAG
        Parameters
        ----------
        notebook : nbformat.NotebookNode
            The notebook to read from.
        """
        skip_profiling_cell_indexes = []
        wait_for_viz_cell_indexes = []
        for cell_index, cell in enumerate(notebook.cells, 1):
            # Get the nb cell tags
            tags = cell.metadata.get("tags", [])
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

    async def get_ui_network_throttling_value(
        self, notebook: nbformat.NotebookNode
    ) -> None:
        """
        Collect the ui network throttling value from the notebook if set in the
        cell tagged as parameters.
        Parameters
        ----------
        notebook : nbformat.NotebookNode
            The notebook to read from.
        """
        for cell in notebook.cells:
            # Get the nb cell tagged with the specified cell_tag
            tags = cell.metadata.get("tags", [])
            if self.PARAMETERS_CELL_TAG in tags:
                cell_source = cell.source or ""
                match = re.search(self.UI_NETWORK_THROTTLING_REGEX, cell_source)
                if match and match.group("value"):
                    value = int(match.group("value"))
                    if value > 0:
                        self.ui_network_throttling_value = value * MEGABYTE
                # Once a cell tagged as parameters has been found, there is no need
                # to keep looking
                return

    async def wait_for_notebook_to_load(self) -> None:
        """
        Wait for the notebook to load by checking for the presence of the notebook
        element in the DOM.
        Retries a few times with exponential backoff in case of failure.
        """
        max_retries = 5
        retry_delay = 10 + random.uniform(0, 1)  # Initial delay in seconds with jitter
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
                    f"Error waiting for notebook to load, retrying... {attempt + 1}/{max_retries}"
                )
                retry_delay *= 2  # Double the delay for the next attempt
                retry_delay += random.uniform(0, 1)  # Add jitter
        raise TimeoutException("Notebook did not load in time after multiple attempts.")

    async def close(self) -> None:
        """
        Close the Selenium driver.
        """
        self.driver.quit()
        logger.debug("Driver closed")


async def profile_notebook(
    url: str,
    token: str,
    kernel_name: str,
    nb_input_path: str,
    headless: bool,
    screenshots_dir_path: str | None = None,
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
        f"Log Level: {log_level}"
    )

    # Initialize JupyterLab helper and clear any existing sessions
    jupyter_lab_helper = JupyterLabHelper(
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

    # Start Selenium and run the profiler
    profiler = Profiler(
        url=jupyter_lab_helper.notebook_url,
        headless=headless,
        nb_input_path=nb_input_path,
        screenshots_dir_path=screenshots_dir_path,
    )
    try:
        await profiler.setup()
        await profiler.run()
    finally:
        await profiler.close()

    # Clean up by deleting the uploaded notebook
    await jupyter_lab_helper.delete_notebook()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
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
        required=False,
        type=bool,
        default=False,
        choices=[True, False],
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
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(profile_notebook(**vars(parser.parse_args())))
