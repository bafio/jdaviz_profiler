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
from tqdm import tqdm

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
        logger.info(f"Executing cell {self.index}")

        # Initialize variables to track the progress of the cell execution
        done_found: bool = False
        start_time: float = elapsed_time()
        kernel_pid: int = self.profiler.get_current_kernel_pid()

        # Click on the cell
        self.cell.click()
        # Execute the cell
        self.cell.send_keys(Keys.SHIFT, Keys.ENTER)

        # Set initial execution status to IN_PROGRESS
        self.performance_metrics.execution_status = CellExecutionStatus.IN_PROGRESS

        # Set up the progress bar for cell execution
        progress_bar = tqdm(
            total=self.max_wait_time,
            desc=f"Cell {self.index} Timeout Progress",
            leave=False,
            position=0,
        )

        # Used to skip the first metrics capture
        first_iter: bool | None = True
        continue_loop: bool = True
        while continue_loop:
            # Mark the beginning of a loop iteration (for progress bar updates)
            loop_iteration_start: float = elapsed_time()
            # Capture metrics after the first iteration
            first_iter = not first_iter and self.capture_metrics(start_time)

            continue_loop = continue_loop and not self.time_is_expired(start_time)

            continue_loop = continue_loop and not self.kernel_has_restarted(kernel_pid)

            # Wait a bit before checking again
            continue_loop and explicit_wait(self.WAIT_TIME_BEFORE_OUTPUT_CHECK)
            # Update progress bar
            continue_loop and progress_bar.update(
                round(elapsed_time(loop_iteration_start))
            )
            # Reset the loop iteration start (for further progress bar updates)
            loop_iteration_start = elapsed_time()

            # Check if the DONE statement is present in the cell result,
            # only if not yet encountered
            if continue_loop and not (
                done_found := done_found or self.done_statement_is_present()
            ):
                logger.debug(f"Cell {self.index} DONE statement not found yet...")
                continue

            continue_loop = continue_loop and self.need_to_wait_for_viz()

            continue_loop = continue_loop and not self.viz_is_stable()

            # Update progress bar
            continue_loop and progress_bar.update(
                round(elapsed_time(loop_iteration_start))
            )

        # Finalize progress bar
        steps: int = 10
        step: float = (progress_bar.total - progress_bar.n) / steps
        for _ in range(steps):
            explicit_wait(0.05)
            progress_bar.update(step)
        progress_bar.close()

        # Capture metrics one last time after loop exit
        self.capture_metrics(start_time)

        # Compute performance metrics
        self.performance_metrics.compute_metrics()

        # Log the performance metrics
        logger.info(str(self.performance_metrics))

    def time_is_expired(self, t: float) -> bool:
        if (_elapsed_time := elapsed_time(t)) > self.max_wait_time:
            self.performance_metrics.execution_status = CellExecutionStatus.TIMED_OUT
            logger.warning(
                f"Cell {self.index} execution stopped after {_elapsed_time} seconds"
            )
            return True
        return False

    def kernel_has_restarted(self, kernel_pid: int) -> bool:
        if kernel_pid != self.profiler.get_current_kernel_pid():
            self.performance_metrics.execution_status = CellExecutionStatus.FAILED
            logger.warning(
                f"Cell {self.index} execution has been interrupted due to a "
                "kernel restart."
            )
            return True
        return False

    def need_to_wait_for_viz(self) -> bool:
        if self.wait_for_viz:
            logger.debug(f"Cell {self.index} is tagged as to wait for viz changes.")
            return True
        logger.debug(
            f"Cell {self.index} is not tagged as to wait for viz changes, moving on..."
        )
        self.performance_metrics.execution_status = CellExecutionStatus.COMPLETED
        return False

    def viz_is_stable(self) -> bool:
        if self.profiler.viz_element:
            # If we have the viz element, check if it's stable
            logger.debug("We already have the viz element, checking if it's stable...")
            viz_is_stable: bool = self.profiler.viz_element.is_stable(self.index)
            if viz_is_stable:
                logger.debug(f"Cell {self.index} viz element is stable, moving on...")
                self.performance_metrics.execution_status = (
                    CellExecutionStatus.COMPLETED
                )
                return True
            return False
        # Look for the viz element in the page
        logger.debug("Looking for the viz element in the page...")
        self.profiler.detect_viz_element()
        return False

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
        logger.debug(f"Cell {self.index} metrics captured")

    def done_statement_is_present(self) -> bool:
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
