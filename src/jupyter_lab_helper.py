import json
import logging
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.exceptions import RequestException

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


@dataclass(eq=False)
class JupyterLabHelper:
    """Helper class to interact with JupyterLab."""

    url: str
    token: str
    kernel_name: str
    nb_input_path: str
    headers: dict[str, str] = field(init=False)
    notebook_url: str = field(init=False)

    def __post_init__(self) -> None:
        self.headers = {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
        }
        self.notebook_url = (
            f"{self.url}/lab/tree/{self.nb_input_path.split('/')[-1]}/"
            f"?token={self.token}"
        )

    async def clear_jupyterlab_sessions(self) -> None:
        """
        Clear all active sessions (notebooks, consoles, terminals) in the
        JupyterLab instance.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Get a list of all running sessions
            sessions_url: str = f"{self.url}/api/sessions"
            response: requests.Response = requests.get(
                sessions_url, headers=self.headers
            )
            response.raise_for_status()
            sessions: list[dict[str, Any]] = response.json()

            if not sessions:
                logger.info("No active sessions found.")
                return

            logger.info(f"Found {len(sessions)} active sessions. Shutting them down...")

            # Shut down each session
            for session in sessions:
                session_id: str = session["id"]
                shutdown_url: str = f"{self.url}/api/sessions/{session_id}"
                shutdown_response: requests.Response = requests.delete(
                    shutdown_url, headers=self.headers
                )
                shutdown_response.raise_for_status()

                # Print a status message based on the session type
                if "kernel" in session and session["kernel"]:
                    logger.info(
                        "Shut down notebook/console session: "
                        f"{session['path']} (ID: {session_id})"
                    )
                elif "terminal" in session:
                    logger.info(
                        f"Shut down terminal session: {session['name']} "
                        f"(ID: {session_id})"
                    )
                else:
                    logger.info(f"Shut down unknown session type (ID: {session_id})")

        except RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    async def restart_kernel(self) -> None:
        """
        Restart the kernel for a given kernel name.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Get the list of all kernels
            kernels_url: str = f"{self.url}/api/kernels"
            response: requests.Response = requests.get(
                kernels_url, headers=self.headers
            )
            response.raise_for_status()
            kernels: list[dict[str, Any]] = response.json()

            # Find the kernel ID for the given kernel name
            kernel_id: str | None = None
            for kernel in kernels:
                if kernel["name"] == self.kernel_name:
                    kernel_id = kernel["id"]
                    break

            if not kernel_id:
                logger.warning(
                    f"No active kernel found for kernel name: {self.kernel_name}."
                )
                return

            # Restart the kernel
            restart_url: str = f"{self.url}/api/kernels/{kernel_id}/restart"
            restart_response: requests.Response = requests.post(
                restart_url, headers=self.headers
            )
            restart_response.raise_for_status()

            logger.info(f"Kernel {self.kernel_name} restarted successfully.")

        except RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    async def upload_notebook(self) -> None:
        """
        Upload the notebook to the JupyterLab instance.
        Raises
        ------
        FileNotFoundError
            If the notebook file does not exist.
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Extract filename from path
            notebook_path: str = self.nb_input_path.split("/")[-1]
            upload_url: str = f"{self.url}/api/contents/{notebook_path}"
            logger.info(f"Uploading notebook to {upload_url}")

            with open(self.nb_input_path, "r", encoding="utf-8") as nb_file:
                notebook_content: dict[str, Any] = json.load(nb_file)

            payload: dict[str, Any] = {
                "content": notebook_content,
                "type": "notebook",
                "format": "json",
            }

            response: requests.Response = requests.put(
                upload_url, headers=self.headers, json=payload
            )
            response.raise_for_status()

            logger.info(f"Notebook uploaded successfully to {upload_url}")

        except FileNotFoundError as e:
            logger.exception(f"Notebook file not found: {notebook_path}")
            raise e
        except RequestException as e:
            logger.exception(f"Error uploading notebook: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    async def delete_notebook(self) -> None:
        """
        Delete the notebook from the JupyterLab instance.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Extract filename from path
            notebook_path: str = self.nb_input_path.split("/")[-1]
            delete_url: str = f"{self.url}/api/contents/{notebook_path}"
            logger.info(f"Deleting notebook at {delete_url}")

            response: requests.Response = requests.delete(
                delete_url, headers=self.headers
            )
            response.raise_for_status()

            logger.info(f"Notebook deleted successfully from {delete_url}")

        except RequestException as e:
            logger.exception(f"Error deleting notebook: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e
