"""
Copyright (c) 2024 Denis Rozhnovskiy <pytelemonbot@mail.ru>

This file is part of the PyOutlineAPI project.

PyOutlineAPI is a Python package for interacting with the Outline VPN Server.

Licensed under the MIT License. See the LICENSE file for more details.

"""
import io
import logging
import unittest
from logging import StreamHandler

from pyoutlineapi import logger


class TestLoggerSetup(unittest.TestCase):
    def setUp(self):
        """Setup for test cases."""
        self.logger_name = 'test_logger'
        self.logger = logger.setup_logger(self.logger_name)
        self.log_stream = io.StringIO()
        # Redirect log output to the StringIO object
        handler = StreamHandler(self.log_stream)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        """Teardown for test cases."""
        self.logger.handlers.clear()

    def test_logger_name(self):
        """Test if the logger has the correct name."""
        self.assertEqual(self.logger.name, self.logger_name)

    def test_logger_level(self):
        """Test if the logger's level is set to DEBUG."""
        self.assertEqual(self.logger.level, logging.DEBUG)

    def test_logging_format(self):
        """Test if the logging format is correct."""
        self.logger.info('Test message')
        log_contents = self.log_stream.getvalue()
        self.assertIn('Test message', log_contents)
        self.assertIn('INFO', log_contents)
        self.assertIn(self.logger_name, log_contents)
        self.assertIn(' - ', log_contents)
        self.assertIn('-', log_contents)  # Ensure the format contains '-'

    def test_logger_output(self):
        """Test if the log message is correctly output."""
        self.logger.info('Test log output')
        log_contents = self.log_stream.getvalue()
        self.assertIn('Test log output', log_contents)


if __name__ == '__main__':
    unittest.main()
