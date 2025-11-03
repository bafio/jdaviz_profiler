from collections import OrderedDict
from collections.abc import Callable
from dataclasses import field, make_dataclass
from enum import StrEnum, unique
from statistics import mean
from typing import Any, ClassVar

STATS_MAP: dict[str, Callable] = {
    "min": min,
    "mean": mean,
    "max": max,
}

SOURCE_METRIC_COMBO: tuple[tuple[str, str], ...] = tuple(
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

SOURCE_METRIC_STAT_COMBO: tuple[tuple[str, str, str], ...] = tuple(
    (so, st, m) for so, m in SOURCE_METRIC_COMBO for st in STATS_MAP.keys()
)

BASE_METRICS_FIELDS: tuple[tuple[str, type, object], ...] = tuple(
    (
        ("total_execution_time", float, field(default=0)),
        ("client_total_data_received", float, field(default=0)),
        *(
            (f"{s}_{m}_list", list[float], field(default_factory=list, repr=False))
            for s, m in SOURCE_METRIC_COMBO
        ),
        *(
            ("_".join(so_m_st), float, field(default=0))
            for so_m_st in SOURCE_METRIC_STAT_COMBO
        ),
    )
)

# Create the BaseMetrics dataclass dynamically
BaseMetrics: type = make_dataclass("BaseMetrics", BASE_METRICS_FIELDS)


class MetricsMixin:
    """Mixin Class to add metrics computation and string representation."""

    # Keys to exclude from the custom dict factory
    # these are the lists used to compute averages
    EXCLUDE_KEYS: ClassVar[tuple[str, ...]] = tuple(
        f"{source}_{metric}_list" for source, metric in SOURCE_METRIC_COMBO
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
                if k not in MetricsMixin.EXCLUDE_KEYS
            }
        )

    def compute(self) -> None:
        """Compute the average cpu and memory usage from the recorded lists."""
        for so, st, m in SOURCE_METRIC_STAT_COMBO:
            if values := getattr(self, f"{so}_{m}_list"):
                setattr(self, f"{so}_{st}_{m}", STATS_MAP[st](values))

    def __str__(self) -> str:
        str_list: list[str] = [
            (
                f"total execution time: {getattr(self, 'total_execution_time'):.2f} "
                "seconds."
            ),
            (
                "client total data received: "
                f"{getattr(self, 'client_total_data_received'):.2f} MB."
            ),
        ] + [
            f"{so} {st} {m} usage: {getattr(self, f'{so}_{st}_{m}'):.2f}%."
            for so, st, m in SOURCE_METRIC_STAT_COMBO
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


class CellMetrics(BaseMetrics, MetricsMixin):
    """Class representing cell performance metrics."""

    cell_index: int = 0
    execution_status: CellExecutionStatus = CellExecutionStatus.PENDING

    def __str__(self) -> str:
        return (
            f"Cell {self.cell_index}: "
            f"Execution: {self.execution_status} "
            f"{super().__str__()}"
        )


class NotebookMetrics(BaseMetrics, MetricsMixin):
    """Class representing notebook performance metrics."""

    total_cells: int = 0
    executed_cells: int = 0
    profiled_cells: int = 0

    def __str__(self) -> str:
        return (
            f"Notebook with {self.total_cells} cells, "
            f"of which {self.executed_cells} were correctly executed and "
            f"{self.profiled_cells} were profiled. "
            f"{super().__str__()}"
        )
