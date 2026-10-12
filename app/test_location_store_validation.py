import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import location_store


class LocationValidationTests(unittest.TestCase):

    def test_missing_location_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            missing = Path(root) / "does-not-exist"

            with self.assertRaises(ValueError) as context:
                location_store.validate_location_availability(
                    str(missing),
                    require_write=True,
                )

            self.assertIn(
                "does not exist",
                str(context.exception),
            )

    def test_file_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            file_path = Path(root) / "not-a-directory"

            file_path.write_text(
                "test",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError) as context:
                location_store.validate_location_availability(
                    str(file_path),
                    require_write=True,
                )

            self.assertIn(
                "not a folder",
                str(context.exception),
            )

    def test_ready_directory_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            result = (
                location_store
                .validate_location_availability(
                    root,
                    require_write=True,
                )
            )

            self.assertEqual(
                result,
                root,
            )

    def test_unwritable_hack_location_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            real_access = location_store.os.access

            def fake_access(path, mode):
                if mode & os.W_OK:
                    return False

                return real_access(
                    path,
                    mode,
                )

            with patch.object(
                location_store.os,
                "access",
                side_effect=fake_access,
            ):
                with self.assertRaises(ValueError) as context:
                    location_store.validate_location_availability(
                        root,
                        require_write=True,
                    )

            self.assertIn(
                "write access",
                str(context.exception),
            )


if __name__ == "__main__":
    unittest.main()
