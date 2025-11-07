import csv
import os.path as os_path
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, field, make_dataclass
from statistics import mean
from typing import Any, ClassVar

from src.utils import CellExecutionStatus

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


class Metrics(BaseMetrics):
    """Class to add metrics computation and string representation."""

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
                if k not in Metrics.EXCLUDE_KEYS
            }
        )

    def save_metrics_to_csv(
        self, notebook_filename: str, nb_params_dict: dict[str, Any], csv_file_path: str
    ) -> None:
        """
        Save the profiling metrics to a CSV file.
        """
        # Set the first column as the notebook filename
        first_col: dict[str, str] = {"notebook_filename": notebook_filename}
        # Append notebook parameters with '_param' suffix
        _nb_params_dict: dict[str, Any] = {
            f"{key}_param": value for key, value in nb_params_dict.items()
        }
        # Append performance metrics with '_metric' suffix
        metrics_dict: dict[str, Any] = {
            f"{key}_metric": value
            for key, value in asdict(
                self,
                dict_factory=self.dict_factory,
            ).items()
        }
        # Combine all into a single OrderedDict for CSV writing
        data: list[OrderedDict[str, Any]] = [
            OrderedDict(
                **first_col,
                **self.get_extra_values(),
                **_nb_params_dict,
                **metrics_dict,
            )
        ]
        # Determine if we need to write the header
        writeheader: bool = os_path.getsize(csv_file_path) <= 0
        # Write metrics to CSV file
        with open(csv_file_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
            writeheader and writer.writeheader()
            writer.writerows(data)

    def get_extra_values(self) -> dict[str, Any]:
        return {}

    def compute(self) -> None:
        """Compute the statistics on cpu and memory from the recorded lists."""
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


class CellMetrics(Metrics):
    """Class representing cell performance metrics."""

    cell_index: int = 0
    execution_status: CellExecutionStatus = CellExecutionStatus.PENDING

    def get_extra_values(self) -> dict[str, Any]:
        return {
            "cell_index": self.cell_index,
            "execution_status": self.execution_status,
        }

    def __str__(self) -> str:
        return (
            f"Cell {self.cell_index}: "
            f"Execution: {self.execution_status} "
            f"{super().__str__()}"
        )


class NotebookMetrics(Metrics):
    """Class representing notebook performance metrics."""

    total_cells: int = 0
    executed_cells: int = 0
    profiled_cells: int = 0

    def get_extra_values(self) -> dict[str, Any]:
        return {
            "total_cells": self.total_cells,
            "executed_cells": self.executed_cells,
            "profiled_cells": self.profiled_cells,
        }

    def __str__(self) -> str:
        return (
            f"Notebook with {self.total_cells} cells, "
            f"of which {self.executed_cells} were correctly executed and "
            f"{self.profiled_cells} were profiled. "
            f"{super().__str__()}"
        )
