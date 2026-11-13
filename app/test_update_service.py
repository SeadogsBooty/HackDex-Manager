import json
import os
import tempfile
import unittest

import update_service


class UpdateServiceTests(unittest.TestCase):

    def tearDown(self):
        update_service.clear_update_cache()

    def test_default_remote_manifest_url(self):
        old_url = os.environ.pop(
            "HACKDEX_UPDATE_MANIFEST_URL",
            None,
        )

        try:
            self.assertEqual(
                update_service._remote_manifest_url(),
                (
                    "https://raw.githubusercontent.com/"
                    "SeadogsBooty/HackDex-Manager/"
                    "main/update-manifest.json"
                ),
            )

        finally:
            if old_url is not None:
                os.environ[
                    "HACKDEX_UPDATE_MANIFEST_URL"
                ] = old_url


    def test_empty_remote_override_disables_default(self):
        old_url = os.environ.get(
            "HACKDEX_UPDATE_MANIFEST_URL"
        )

        try:
            os.environ[
                "HACKDEX_UPDATE_MANIFEST_URL"
            ] = ""

            self.assertEqual(
                update_service._remote_manifest_url(),
                "",
            )

        finally:
            if old_url is None:
                os.environ.pop(
                    "HACKDEX_UPDATE_MANIFEST_URL",
                    None,
                )
            else:
                os.environ[
                    "HACKDEX_UPDATE_MANIFEST_URL"
                ] = old_url


    def test_version_comparison(self):
        self.assertTrue(
            update_service.is_newer_version(
                "1.1.2",
                "1.1.1",
            )
        )

        self.assertFalse(
            update_service.is_newer_version(
                "1.1.1",
                "1.1.1",
            )
        )

        self.assertFalse(
            update_service.is_newer_version(
                "1.1.0",
                "1.1.1",
            )
        )


        self.assertFalse(
            update_service.is_newer_version(
                "1.1.2-test",
                "1.1.2",
            )
        )

    def test_local_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(
                temp,
                "update-manifest.json",
            )

            with open(
                path,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    {
                        "version": "1.1.4",
                        "release_notes": "Test release",
                        "docker": {
                            "image": "example/hackdex:1.1.4",
                        },
                    },
                    handle,
                )

            old_file = os.environ.get(
                "HACKDEX_UPDATE_MANIFEST_FILE"
            )
            old_url = os.environ.get(
                "HACKDEX_UPDATE_MANIFEST_URL"
            )
            old_desktop = os.environ.get(
                "HACKDEX_DESKTOP"
            )

            try:
                os.environ[
                    "HACKDEX_UPDATE_MANIFEST_FILE"
                ] = path
                os.environ[
                    "HACKDEX_UPDATE_MANIFEST_URL"
                ] = ""
                os.environ[
                    "HACKDEX_DESKTOP"
                ] = "0"

                update_service.clear_update_cache()

                status = (
                    update_service.get_update_status(
                        force=True
                    )
                )

                self.assertTrue(
                    status["configured"]
                )
                self.assertTrue(
                    status["update_available"]
                )
                self.assertEqual(
                    status["latest_version"],
                    "1.1.4",
                )
                self.assertEqual(
                    status["platform"],
                    "docker",
                )

            finally:
                for key, value in (
                    (
                        "HACKDEX_UPDATE_MANIFEST_FILE",
                        old_file,
                    ),
                    (
                        "HACKDEX_UPDATE_MANIFEST_URL",
                        old_url,
                    ),
                    (
                        "HACKDEX_DESKTOP",
                        old_desktop,
                    ),
                ):
                    if value is None:
                        os.environ.pop(
                            key,
                            None,
                        )
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
