from collections import OrderedDict
from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import Any, ClassVar


@dataclass
class Metrics:
    """Class representing performance metrics."""

    total_execution_time: float = 0
    client_total_data_received: float = 0
    client_average_cpu_usage: float = 0
    client_average_memory_usage: float = 0
    client_average_cpu_usage_list: list[float] = field(default_factory=list, repr=False)
    client_average_memory_usage_list: list[float] = field(
        default_factory=list, repr=False
    )
    kernel_average_cpu_usage: float = 0
    kernel_average_memory_usage: float = 0
    kernel_average_cpu_usage_list: list[float] = field(default_factory=list, repr=False)
    kernel_average_memory_usage_list: list[float] = field(
        default_factory=list, repr=False
    )

    # Define combinations of sources and metrics
    # like (client,cpu), (kernel,memory), etc.
    SOURCE_METRIC_COMBO: ClassVar[tuple[str, ...]] = tuple(
        (s, m)
        for s in (
            "client",
            "kernel",
        )
        for m in (
            "cpu",
            "memory",
        )
    )

    # Keys to exclude from the custom dict factory
    # these are the lists used to compute averages
    EXCLUDE_KEYS: ClassVar[tuple[str, ...]] = tuple(
        f"{source}_average_{metric}_usage_list"
        for source, metric in SOURCE_METRIC_COMBO
    )

    @staticmethod
    def dict_factory(data: list[tuple[str, Any]]) -> OrderedDict[str, Any]:
        """
        Custom dict factory to round float values to 2 decimal places and
        exclude certain keys.
        Parameters:
            data (list[tuple[str, Any]]): List of key-value pairs.
        Returns:
            OrderedDict[str, Any]: Processed ordered dictionary.
        """
        return OrderedDict(
            {
                k: round(v, 2) if isinstance(v, float) else v
                for (k, v) in data
                if k not in Metrics.EXCLUDE_KEYS
            }
        )

    def compute(self) -> None:
        """Compute the average cpu and memory usage from the recorded lists."""
        for s, m in self.SOURCE_METRIC_COMBO:
            if values := getattr(self, f"{s}_average_{m}_usage_list"):
                setattr(self, f"{s}_average_{m}_usage", sum(values) / len(values))

    def __str__(self) -> str:
        str_list = [
            f"total execution time: {self.total_execution_time:.2f} seconds.",
            f"client total data received: {self.client_total_data_received:.2f} MB.",
        ] + [
            f"{s} average {m} usage: {getattr(self, f'{s}_average_{m}_usage'):.2f}%."
            for s, m in self.SOURCE_METRIC_COMBO
        ]
        return " ".join(str_list)


@unique
class CellExecutionStatus(StrEnum):
    """
    Represents the various possible statuses of a notebook cell execution process.
    """

    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    TIMED_OUT = "Timed Out"

    @property
    def is_not_final(self) -> bool:
        """Returns True if the status is not a final state, False otherwise."""
        return self in {CellExecutionStatus.PENDING, CellExecutionStatus.IN_PROGRESS}

    @property
    def is_final(self) -> bool:
        """Returns True if the status is a final state, False otherwise."""
        return not self.is_not_final


@dataclass
class CellMetrics(Metrics):
    """Class representing cell performance metrics."""

    cell_index: int = 0
    execution_status: CellExecutionStatus = CellExecutionStatus.PENDING

    def __str__(self) -> str:
        return (
            f"Cell {self.cell_index}: "
            f"Execution: {self.execution_status} "
            f"{super().__str__()}"
        )


@dataclass
class NotebookMetrics(Metrics):
    """Class representing notebook performance metrics."""

    total_cells: int = 0
    executed_cells: int = 0
    profiled_cells: int = 0

    def __str__(self) -> str:
        return (
            f"Notebook with {self.total_cells} cells, "
            f"of which {self.executed_cells} were correctly executed and "
            f"{self.profiled_cells} were profiled."
            f"{super().__str__()}"
        )
