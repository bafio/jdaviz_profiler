import logging

import yaml

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


def load_dict_from_yaml_file(file_path: str) -> dict:
    """
    Load a dictionary of key-value pairs from a YAML file.
    Parameters
    ----------
    file_path : str
        Path to the YAML file.
    Returns
    -------
    dict
        Dictionary containing the key-value pairs.
    Raises
    ------
    FileNotFoundError
        If the YAML file does not exist.
    ValueError
        If the YAML file is empty or improperly formatted.
    """
    with open(file_path, "r") as f:
        data = yaml.full_load(f)
    if not data:
        msg = f"No data found in {file_path}"
        logger.error(msg)
        raise ValueError(msg)
    return data
