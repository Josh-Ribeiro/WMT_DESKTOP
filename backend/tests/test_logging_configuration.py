from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.core.logging_config import configure_logging


class LoggingConfigurationTests(unittest.TestCase):
    def test_creates_rotating_backend_log_without_duplicate_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            matching_handlers: list[logging.Handler] = []
            try:
                with patch.dict("os.environ", {"WMT_LOG_DIR": temp_dir}):
                    first_path = configure_logging()
                    second_path = configure_logging()

                    self.assertEqual(Path(temp_dir) / "backend.log", first_path)
                    self.assertEqual(first_path, second_path)
                    matching_handlers = [
                        handler
                        for handler in logging.getLogger().handlers
                        if getattr(handler, "baseFilename", None)
                        and Path(handler.baseFilename) == first_path
                    ]
                    self.assertEqual(1, len(matching_handlers))
            finally:
                for handler in matching_handlers:
                    logging.getLogger().removeHandler(handler)
                    handler.close()


if __name__ == "__main__":
    unittest.main()
