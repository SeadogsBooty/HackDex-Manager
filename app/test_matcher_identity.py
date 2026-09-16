import unittest
from types import SimpleNamespace

from matcher import (
    score_candidate,
    title_score,
)


def rom(title, platform):
    return SimpleNamespace(
        parsed_title=title,
        filename=title,
        platform=platform,
    )


def hack(
    title,
    platform,
    slug=None,
):
    return SimpleNamespace(
        title=title,
        platform=platform,
        slug=(
            slug
            or title.lower().replace(
                " ",
                "-",
            )
        ),
    )


class IdentityMatcherTests(
    unittest.TestCase
):

    def test_pokemon_prefix_is_metadata(self):
        self.assertEqual(
            title_score(
                "Pokémon Crystal Inheritance",
                "Crystal Inheritance",
            ),
            100.0,
        )

    def test_fire_red_spelling_is_canonical(self):
        self.assertEqual(
            title_score(
                "Pokemon Fire Red Enhanced",
                "Pokémon - Fire Red Enhanced",
            ),
            100.0,
        )

    def test_ashgray_spelling_is_canonical(self):
        self.assertEqual(
            title_score(
                "Pokémon AshGray - Newerest Edition",
                "Ash Gray - Newerest edition",
            ),
            100.0,
        )

    def test_rowe_spelling_is_canonical(self):
        self.assertEqual(
            title_score(
                "Pokémon R.O.W.E.",
                "Pokemon ROWE",
            ),
            100.0,
        )

    def test_ampersand_and_word_are_equivalent(self):
        self.assertEqual(
            title_score(
                "Pokemon FireRed & LeafGreen++",
                "Pokémon FireRed and LeafGreen++",
            ),
            100.0,
        )

    def test_plus_variants_are_not_collapsed(self):
        score = title_score(
            "Pokemon FireRed & LeafGreen++",
            "Pokémon FireRed & LeafGreen+ (FRLG+)",
        )

        self.assertLess(
            score,
            70.0,
        )

    def test_no_plus_is_not_plus(self):
        score = score_candidate(
            rom(
                "Pokémon FireRed & LeafGreen",
                "GBA",
            ),
            hack(
                "Pokémon FireRed & LeafGreen+ (FRLG+)",
                "GBA",
                "pokemon-firered-leafgreen-frlg",
            ),
        )

        self.assertLess(
            score,
            70.0,
        )

    def test_crystal_clear_is_not_crystal_legacy(self):
        score = score_candidate(
            rom(
                "Pokémon Crystal Clear",
                "GBC",
            ),
            hack(
                "Pokémon Crystal Legacy",
                "GBC",
                "pokemon-crystal-legacy",
            ),
        )

        self.assertLess(
            score,
            70.0,
        )

    def test_kalos_crystal_is_not_core_crystal(self):
        score = score_candidate(
            rom(
                "Pokémon Kalos Crystal",
                "GBC",
            ),
            hack(
                "Pokemon Core Crystal",
                "GBC",
                "pokemon-core-crystal",
            ),
        )

        self.assertLess(
            score,
            70.0,
        )

    def test_sors_2_is_not_sors(self):
        score = score_candidate(
            rom(
                "Pokémon Sors 2",
                "GBA",
            ),
            hack(
                "Pokémon Sors (English)",
                "GBA",
                "pokemon-sors",
            ),
        )

        self.assertLess(
            score,
            70.0,
        )

    def test_sors_language_requires_review(self):
        score = score_candidate(
            rom(
                "Pokémon Sors",
                "GBA",
            ),
            hack(
                "Pokémon Sors (English)",
                "GBA",
                "pokemon-sors",
            ),
        )

        self.assertGreaterEqual(
            score,
            70.0,
        )

        self.assertLess(
            score,
            95.0,
        )

    def test_saiph_language_requires_review(self):
        score = score_candidate(
            rom(
                "Pokémon Saiph 2",
                "GBA",
            ),
            hack(
                "Pokémon Saiph 2 (English)",
                "GBA",
                "pokemon-saiph-2-english",
            ),
        )

        self.assertGreaterEqual(
            score,
            70.0,
        )

        self.assertLess(
            score,
            95.0,
        )

    def test_blazed_glazed_is_not_glazed(self):
        score = score_candidate(
            rom(
                "Pokémon Blazed Glazed",
                "GBA",
            ),
            hack(
                "Glazed",
                "GBA",
                "pokemon-glazed",
            ),
        )

        self.assertLess(
            score,
            70.0,
        )

    def test_snakewood_is_not_resurrected(self):
        score = score_candidate(
            rom(
                "Pokémon Snakewood",
                "GBA",
            ),
            hack(
                "Pokémon Snakewood: Resurrected",
                "GBA",
                "pokemon-snakewood-resurrected",
            ),
        )

        self.assertLess(
            score,
            70.0,
        )

    def test_regrown_legacy_requires_review(self):
        score = score_candidate(
            rom(
                "Pokémon LeafGreen Regrown Legacy",
                "GBA",
            ),
            hack(
                "Pokemon Leafgreen Regrown",
                "GBA",
                "pokemon-leafgreen-regrown",
            ),
        )

        self.assertGreaterEqual(
            score,
            70.0,
        )

        self.assertLess(
            score,
            95.0,
        )

    def test_aesthetic_red_long_title_is_review_only(self):
        score = score_candidate(
            rom(
                "Pokémon Aesthetic Red",
                "GBA",
            ),
            hack(
                (
                    "Pokémon Aesthetic Red - "
                    "A Visual and Musical Overhaul of Fire Red"
                ),
                "GBA",
                (
                    "pokemon-aesthetic-red-a-visual-and-"
                    "musical-overhaul-of-fire-red"
                ),
            ),
        )

        self.assertGreaterEqual(
            score,
            70.0,
        )

        self.assertLess(
            score,
            95.0,
        )

    def test_complete_annotation_is_metadata(self):
        self.assertEqual(
            title_score(
                "Pokémon Crystal Awakening",
                "Pokémon Crystal Awakening (COMPLETE)",
            ),
            100.0,
        )

    def test_family_conflict_is_rejected(self):
        self.assertLess(
            title_score(
                "Pokémon Sour Crystal",
                "Pokémon Sour Emerald",
            ),
            70.0,
        )

    def test_platform_conflict_is_zero(self):
        self.assertEqual(
            score_candidate(
                rom(
                    "Pokémon Crystal Legacy",
                    "GBC",
                ),
                hack(
                    "Pokémon Crystal Legacy",
                    "GBA",
                    "pokemon-crystal-legacy",
                ),
            ),
            0.0,
        )


    def test_rowe_mega_update_is_review_only(self):
        score = score_candidate(
            rom(
                "Pokémon R.O.W.E.",
                "GBA",
            ),
            hack(
                "Pokémon R.O.W.E. - The Mega Update",
                "GBA",
                "pokemon-rowe",
            ),
        )

        self.assertEqual(
            score,
            94.0,
        )

        self.assertLess(
            score,
            95.0,
        )


if __name__ == "__main__":
    unittest.main()
