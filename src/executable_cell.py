import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from os import linesep
from typing import TYPE_CHECKING, ClassVar

import psutil
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from src.performance_metrics import CellExecutionStatus, CellPerformanceMetrics
from src.utils import elapsed_time, explicit_wait

# Avoid circular import
if TYPE_CHECKING:
    from src.profiler import Profiler

logger: logging.Logger = logging.getLogger(__name__)
# Default level is INFO
logger.setLevel(logging.INFO)
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


@dataclass(eq=False)
class ExecutableCell:
    """Class representing an executable cell in a Jupyter notebook."""

    cell: WebElement
    index: int
    max_wait_time: int
    skip_profiling: bool
    wait_for_viz: bool
    profiler: "Profiler"
    performance_metrics: CellPerformanceMetrics = field(
        default_factory=CellPerformanceMetrics, repr=False
    )

    # Seconds to wait after the execution command if no need to
    # collect profiling metrics
    SECONDS_TO_WAIT_IF_SKIP_PROFILING: ClassVar[float] = 2.5

    # Seconds to wait before checking the executed cell outputs
    WAIT_TIME_BEFORE_OUTPUT_CHECK: ClassVar[float] = 0.5

    # Selector for all output cells in a code cell
    OUTPUT_CELLS_SELECTOR: ClassVar[str] = ".lm-Widget.lm-Panel.jp-Cell-outputWrapper"

    # Selector for all text output cells in a code cell
    OUTPUT_CELLS_TEXT_SELECTOR: ClassVar[str] = (
        ".lm-Widget.jp-RenderedText.jp-mod-trusted.jp-OutputArea-output"
    )

    # Regex to identify the cell output containing the `DONE` text output
    OUTPUT_CELL_DONE_REGEX: ClassVar[str] = r"^.*(?P<DONE>DONE).*$"

    def __post_init__(self):
        self.performance_metrics.cell_index = self.index

    def execute(self) -> None:
        """
        Execute the cell and collect profiling metrics.
        """
        try:
            logger.info(f"Executing cell {self.index}")

            # Initialize variables to track the viz element and elapsed time
            viz_is_stable: bool = False
            done_found: bool = False
            start_time: float = elapsed_time()
            kernel_pid = self.profiler.get_current_kernel_pid()

            # Click on the cell
            self.cell.click()
            # Execute the cell
            self.cell.send_keys(Keys.SHIFT, Keys.ENTER)

            self.performance_metrics.execution_status = CellExecutionStatus.IN_PROGRESS

            first_iteration = True
            while True:
                not first_iteration and self.capture_metrics()
                first_iteration = False

                # Check for timeout
                if elapsed_time(start_time) > self.max_wait_time:
                    self.performance_metrics.execution_status = (
                        CellExecutionStatus.TIMED_OUT
                    )
                    logger.warning(
                        f"Cell {self.index} execution timed out after "
                        f"{self.max_wait_time} seconds"
                    )
                    break

                if kernel_pid != self.profiler.get_current_kernel_pid():
                    self.performance_metrics.execution_status = (
                        CellExecutionStatus.FAILED
                    )
                    logger.warning(
                        f"Cell {self.index} execution has been interrupted due to a"
                        "kernel restart."
                    )
                    break

                # Wait a bit before checking again
                explicit_wait(self.WAIT_TIME_BEFORE_OUTPUT_CHECK)

                # Check if the DONE statement is present in the cell result,
                # only if not yet encountered
                done_found = done_found or self.look_for_done_statement()
                if not done_found:
                    logger.debug(f"Cell {self.index} DONE statement not found yet...")
                    continue

                logger.debug(f"Cell {self.index} DONE statement found, moving on...")

                if not self.wait_for_viz:
                    logger.debug(
                        f"Cell {self.index} is not tagged as to wait for viz changes, "
                        "moving on..."
                    )
                    self.performance_metrics.execution_status = (
                        CellExecutionStatus.COMPLETED
                    )
                    break

                logger.debug(f"Cell {self.index} is tagged as to wait for viz changes.")
                if self.profiler.viz_element:
                    # If we have the viz element, check if it's stable
                    logger.debug(
                        "We already have the viz element, checking if it's stable..."
                    )
                    viz_is_stable = self.profiler.viz_element.is_stable(self.index)
                else:
                    # Look for the viz element in the page
                    logger.debug("Looking for the viz element in the page...")
                    self.profiler.detect_viz_element()

                if viz_is_stable:
                    logger.debug(
                        f"Cell {self.index} viz element is stable, moving on..."
                    )
                    self.performance_metrics.execution_status = (
                        CellExecutionStatus.COMPLETED
                    )
                    break

            self.capture_metrics()

            # Compute performance metrics
            self.compute_performance_metrics()

            # Log the performance metrics
            logger.info(str(self.performance_metrics))

        except Exception as e:
            logger.exception(
                f"An error occurred while executing cell {self.index}: {e}"
            )

    def capture_metrics(self, start_time: float) -> None:
        # Save time elapsed
        self.performance_metrics.total_execution_time = elapsed_time(start_time)

        # Capture client CPU usage
        self.performance_metrics.client_average_cpu_usage_list.append(
            psutil.cpu_percent(interval=self.WAIT_TIME_BEFORE_OUTPUT_CHECK)
        )
        # Capture client memory usage
        self.performance_metrics.client_average_memory_usage_list.append(
            psutil.virtual_memory().percent
        )

        # Get kernel usage metrics
        kernel_usage = self.profiler.get_kernel_usage()

        # Capture kernel CPU usage
        self.performance_metrics.kernel_average_cpu_usage_list.append(
            kernel_usage.get("kernel_cpu", 0)
        )

        # Capture kernel memory usage
        self.performance_metrics.kernel_average_memory_usage_list.append(
            kernel_usage.get("host_virtual_memory", {}).get("percent", 0)
        )

    def look_for_done_statement(self) -> bool:
        """
        Look for the DONE statement in the output cells of the cell.
        Returns
        -------
        bool
            True if the DONE statement is found, False otherwise.
        """
        output_cells: list[WebElement] = self.cell.find_elements(
            By.CSS_SELECTOR, self.OUTPUT_CELLS_SELECTOR
        )
        if not output_cells:
            logger.debug(f"Cell {self.index} has no output cells yet, waiting...")
            return False
        for output_cell in output_cells:
            text_output_cells: list[WebElement] = output_cell.find_elements(
                By.CSS_SELECTOR, self.OUTPUT_CELLS_TEXT_SELECTOR
            )
            logger.debug(f"Found {len(text_output_cells)} text output cells")
            if not text_output_cells:
                continue
            output_txt: str = linesep.join(
                [text_output_cell.text for text_output_cell in text_output_cells]
            )
            match: re.Match | None = re.search(
                self.OUTPUT_CELL_DONE_REGEX, output_txt, re.MULTILINE
            )
            if match and match.group("DONE"):
                logger.info(f"Cell {self.index} DONE statement found!")
                return True
        return False

    def compute_performance_metrics(self) -> None:
        """
        Compute profiling metrics for the cell.
        """
        if self.skip_profiling:
            self.performance_metrics.total_execution_time = 0
            self.performance_metrics.client_total_data_received = 0
            self.performance_metrics.client_average_cpu_usage = 0
            self.performance_metrics.client_average_memory_usage = 0
            self.performance_metrics.kernel_average_cpu_usage = 0
            self.performance_metrics.kernel_average_memory_usage = 0
            return

        timestamp_end: datetime = datetime.now()
        timestamp_start: datetime = timestamp_end - timedelta(
            seconds=self.performance_metrics.total_execution_time
        )
        self.performance_metrics.client_total_data_received = (
            self.profiler.get_client_data_received(timestamp_start, timestamp_end)
        )
        self.performance_metrics.compute_metrics()
