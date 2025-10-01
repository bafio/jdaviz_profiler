import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


def load_dict_from_json_file(file_path: str) -> dict:
    """
    Load a dictionary of key-value pairs from a JSON file.
    Parameters
    ----------
    file_path : str
        Path to the JSON file.
    Returns
    -------
    dict
        Dictionary containing the key-value pairs.
    Raises
    ------
    FileNotFoundError
        If the JSON file does not exist.
    ValueError
        If the JSON file is empty or improperly formatted.
    """
    with open(file_path, "r") as f:
        data = json.loads(f.read())
    if not data:
        msg = f"No data found in {file_path}"
        logger.error(msg)
        raise ValueError(msg)
    return data
