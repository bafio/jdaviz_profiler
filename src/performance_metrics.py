import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, ClassVar

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


@dataclass
class PerformanceMetrics:
    """Class representing performance metrics."""

    total_execution_time: float = 0
    client_average_cpu_usage: float = 0
    client_average_memory_usage: float = 0
    client_total_data_received: float = 0
    client_average_cpu_usage_list: list[float] = field(default_factory=list, repr=False)
    client_average_memory_usage_list: list[float] = field(
        default_factory=list, repr=False
    )

    EXCLUDE_KEYS: ClassVar[tuple[str, ...]] = (
        "client_average_cpu_usage_list",
        "client_average_memory_usage_list",
    )

    @staticmethod
    def dict_factory(data: list[tuple[str, Any]]) -> OrderedDict[str, Any]:
        """
        Custom dict factory to round float values to 2 decimal places and
        exclude certain keys.
        """
        return OrderedDict(
            {
                k: round(v, 2) if isinstance(v, float) else v
                for (k, v) in data
                if k not in PerformanceMetrics.EXCLUDE_KEYS
            }
        )

    def compute_metrics(self) -> None:
        """Compute the average CPU and memory usage from the recorded lists."""
        if self.client_average_cpu_usage_list:
            self.client_average_cpu_usage = sum(
                self.client_average_cpu_usage_list
            ) / len(self.client_average_cpu_usage_list)
        if self.client_average_memory_usage_list:
            self.client_average_memory_usage = sum(
                self.client_average_memory_usage_list
            ) / len(self.client_average_memory_usage_list)

    def __str__(self) -> str:
        return (
            f"Total Execution Time: {self.total_execution_time:.2f} seconds. "
            f"Average CPU usage: {self.client_average_cpu_usage:.2f}%. "
            f"Average Memory usage: {self.client_average_memory_usage:.2f}%. "
            f"Total Data received: {self.client_total_data_received:.2f} MB."
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
