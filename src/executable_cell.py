import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from os import linesep
from typing import TYPE_CHECKING, Any, ClassVar

import psutil
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement

from src.performance_metrics import CellExecutionStatus, CellPerformanceMetrics
from src.utils import elapsed_time, explicit_wait, get_logger

# Avoid circular import
if TYPE_CHECKING:
    from src.profiler import Profiler

# Initialize logger
logger: logging.Logger = get_logger()


@dataclass(frozen=True, eq=False)
class ExecutableCell:
    """Class representing an executable cell in a Jupyter notebook."""

    cell: WebElement
    index: int
    max_wait_time: int
    skip_profiling: bool
    wait_for_viz: bool
    profiler: "Profiler"
    performance_metrics: CellPerformanceMetrics = field(
        default_factory=CellPerformanceMetrics, repr=False, init=False
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
        """Post-initialization to set the cell index in performance metrics."""
        self.performance_metrics.cell_index = self.index

    def execute(self) -> None:
        """
        Execute the cell and collect profiling metrics.
        """
        try:
            logger.info(f"Executing cell {self.index}")

            # Initialize variables to track the progress of the cell execution
            viz_is_stable: bool = False
            done_found: bool = False
            start_time: float = elapsed_time()
            kernel_pid: int = self.profiler.get_current_kernel_pid()

            # Click on the cell
            self.cell.click()
            # Execute the cell
            self.cell.send_keys(Keys.SHIFT, Keys.ENTER)

            # Set initial execution status to IN_PROGRESS
            self.performance_metrics.execution_status = CellExecutionStatus.IN_PROGRESS

            # Used to skip the first metrics capture
            first_iter: bool | None = True
            while True:
                # Capture metrics after the first iteration
                first_iter = not first_iter and self.capture_metrics(start_time)

                # Loop exit check: check for timeout
                if _elapsed_time := elapsed_time(start_time) > self.max_wait_time:
                    self.performance_metrics.execution_status = (
                        CellExecutionStatus.TIMED_OUT
                    )
                    logger.warning(
                        f"Cell {self.index} execution stopped after "
                        f"{_elapsed_time} seconds"
                    )
                    break

                # Loop exit check: check if the kernel has restarted
                if kernel_pid != self.profiler.get_current_kernel_pid():
                    self.performance_metrics.execution_status = (
                        CellExecutionStatus.FAILED
                    )
                    logger.warning(
                        f"Cell {self.index} execution has been interrupted due to a "
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

                # Loop exit check: if we don't need to wait for viz changes, we are done
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

                # Loop exit check: if the viz is stable, we are done
                if viz_is_stable:
                    logger.debug(
                        f"Cell {self.index} viz element is stable, moving on..."
                    )
                    self.performance_metrics.execution_status = (
                        CellExecutionStatus.COMPLETED
                    )
                    break

            # Capture metrics one last time after loop exit
            self.capture_metrics(start_time)

            # Compute performance metrics
            self.performance_metrics.compute_metrics()

            # Log the performance metrics
            logger.info(str(self.performance_metrics))

        except Exception as e:
            logger.exception(
                f"An error occurred while executing cell {self.index}: {e}"
            )

    def capture_metrics(self, start_time: float) -> None:
        """
        Capture profiling metrics for the cell execution.
        Parameters
        ----------
        start_time : float
            The start time of the cell execution.
        """
        # Skip metrics capture if profiling is skipped or
        # if execution has already finished and is failed
        if (
            self.skip_profiling
            or self.performance_metrics.execution_status == CellExecutionStatus.FAILED
        ):
            return

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

        # Get kernel usage metrics only if present
        kernel_usage: dict[str, Any] = self.profiler.get_kernel_usage()
        if "kernel_cpu" in kernel_usage and "host_virtual_memory" in kernel_usage:
            # Capture kernel CPU usage
            self.performance_metrics.kernel_average_cpu_usage_list.append(
                kernel_usage["kernel_cpu"]
            )
            # Capture kernel memory usage
            self.performance_metrics.kernel_average_memory_usage_list.append(
                kernel_usage["host_virtual_memory"]["percent"]
            )
        else:
            logger.warning(
                f"Kernel usage metrics not available for cell {self.index}, "
                "skipping kernel metrics capture."
            )

        # Capture client data received from the profiler only when
        # execution is not in progress
        if self.performance_metrics.execution_status not in (
            CellExecutionStatus.PENDING,
            CellExecutionStatus.IN_PROGRESS,
        ):
            timestamp_end: datetime = datetime.now()
            timestamp_start: datetime = timestamp_end - timedelta(
                seconds=self.performance_metrics.total_execution_time
            )
            self.performance_metrics.client_total_data_received = (
                self.profiler.get_client_data_received(timestamp_start, timestamp_end)
            )

    def look_for_done_statement(self) -> bool:
        """
        Look for the DONE statement in the output cells of the executed cell.
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
