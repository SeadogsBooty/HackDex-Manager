import tempfile
import unittest

from desktop_storage import (
    describe_windows_location,
    validate_library_location,
)


class DesktopStorageTests(
    unittest.TestCase
):

    def test_local_drive_syntax(self):
        result = (
            validate_library_location(
                r"C:\ROMs",
                probe=False,
            )
        )

        self.assertTrue(
            result["available"]
        )

        self.assertEqual(
            result["kind"],
            "mapped_or_local_drive",
        )

    def test_mapped_drive_syntax(self):
        result = (
            validate_library_location(
                r"Z:\Pokemon Hacks",
                probe=False,
            )
        )

        self.assertTrue(
            result["available"]
        )

        self.assertEqual(
            result["kind"],
            "mapped_or_local_drive",
        )

    def test_unc_syntax(self):
        result = (
            validate_library_location(
                r"\\NAS\Games\ROMs",
                probe=False,
            )
        )

        self.assertTrue(
            result["available"]
        )

        self.assertEqual(
            result["kind"],
            "unc",
        )

    def test_unc_description(self):
        result = (
            describe_windows_location(
                r"\\SERVER\PokemonHacks"
            )
        )

        self.assertEqual(
            result["label"],
            "Network share",
        )

        self.assertTrue(
            result["is_unc"]
        )

    def test_relative_rejected(self):
        result = (
            validate_library_location(
                "ROMs",
                probe=False,
            )
        )

        self.assertFalse(
            result["available"]
        )

        self.assertFalse(
            result["valid_syntax"]
        )

    def test_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = (
                validate_library_location(
                    temp_dir,
                    probe=True,
                )
            )

            self.assertTrue(
                result["available"]
            )

            self.assertTrue(
                result["readable"]
            )


if __name__ == "__main__":
    unittest.main()
