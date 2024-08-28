"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutlineAPI project.

PyOutlineAPI is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""

import logging


def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with a specified name.

    Args:
        name (str): The name of the logger.

    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Set the base logging level

    # Create a console handler with a specific format
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)  # Set the level for the console handler
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(ch)

    return logger
