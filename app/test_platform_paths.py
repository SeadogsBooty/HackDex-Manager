import os
import unittest
from unittest.mock import patch

import platform_paths


class PlatformPathTests(
    unittest.TestCase
):

    def test_unc_path(self):
        value = (
            r"\\NAS\Games\ROMs"
        )

        self.assertTrue(
            platform_paths.is_unc_path(
                value
            )
        )

        self.assertEqual(
            platform_paths.classify_library_path(
                value
            ),
            "unc",
        )

    def test_mapped_drive_path(self):
        value = r"Z:\ROMs"

        self.assertTrue(
            platform_paths.is_windows_drive_path(
                value
            )
        )

        self.assertEqual(
            platform_paths.classify_library_path(
                value
            ),
            "mapped_or_local_drive",
        )

    def test_local_drive_path(self):
        value = (
            r"C:\Users\Test\ROMs"
        )

        self.assertEqual(
            platform_paths.classify_library_path(
                value
            ),
            "mapped_or_local_drive",
        )

    def test_posix_path(self):
        self.assertEqual(
            platform_paths.classify_library_path(
                "/roms"
            ),
            "posix",
        )

    def test_relative_path_rejected(self):
        valid, message = (
            platform_paths.validate_library_path_syntax(
                "ROMs"
            )
        )

        self.assertFalse(valid)

        self.assertIn(
            "absolute",
            message.lower(),
        )

    def test_unc_path_accepted(self):
        valid, kind = (
            platform_paths.validate_library_path_syntax(
                r"\\SERVER\Share\Pokemon Hacks"
            )
        )

        self.assertTrue(valid)

        self.assertEqual(
            kind,
            "unc",
        )

    def test_windows_desktop_data_path(self):
        root = (
            r"C:\Users\Test\HackDex-Manager"
        )

        env = {
            "HACKDEX_DESKTOP": "1",
            "HACKDEX_DATA_ROOT": root,
        }

        with patch.dict(
            os.environ,
            env,
            clear=False,
        ):
            result = (
                platform_paths.data_dir()
            )

        self.assertEqual(
            str(result),
            str(
                platform_paths.Path(root)
                / "Data"
            ),
        )

    def test_docker_data_default(self):
        with patch.dict(
            os.environ,
            {
                "HACKDEX_DESKTOP": "0",
            },
            clear=False,
        ):
            if os.name != "nt":
                self.assertEqual(
                    str(
                        platform_paths.data_dir()
                    ),
                    "/data",
                )


if __name__ == "__main__":
    unittest.main()
