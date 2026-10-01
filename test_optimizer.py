import unittest
import json
import threading
from pathlib import Path
from unittest.mock import patch

from optimizer import optimize
from server import (
    Authentication,
    CONFIG_DIR,
    load_default_vikings,
    configuration_path,
    resolve_size_limits,
    save_configuration,
    assigned_preference,
    validate_configuration,
    validate_request,
)


class OptimizerTests(unittest.TestCase):
    def test_respects_preferences_when_already_balanced(self):
        result = optimize([[0, 1, 2], [1, 0, 2], [2, 0, 1]], 3)
        self.assertEqual(result.assignment, (0, 1, 2))
        self.assertEqual(result.score, 9)

    def test_balances_competing_preferences(self):
        result = optimize([[0, 1, 2]] * 5, 3)
        sizes = [result.assignment.count(guild) for guild in range(3)]
        self.assertEqual(max(sizes) - min(sizes), 1)
        self.assertEqual(result.score, 11)
        self.assertGreater(result.optimal_solution_count, 1)

    def test_rejects_incomplete_ranking(self):
        with self.assertRaises(ValueError):
            optimize([[0, 1, 1]], 3)

    def test_equal_can_begin_at_first_position(self):
        result = optimize([[None, None, None]], 3)
        self.assertEqual(result.score, 3)
        self.assertEqual(result.optimal_solution_count, 3)

    def test_equal_can_begin_after_explicit_preferences(self):
        result = optimize([[0, None, None]], 3)
        self.assertEqual(result.assignment, (0,))
        self.assertEqual(result.score, 3)

    def test_equal_can_appear_before_an_explicit_last_choice(self):
        result = optimize([[None, None, None, None, None, 5]], 6)
        self.assertNotEqual(result.assignment, (5,))
        self.assertEqual(result.score, 6)
        self.assertEqual(result.optimal_solution_count, 5)

    def test_equal_can_appear_between_explicit_choices(self):
        result = optimize([[0, 1, 2, None, None, 4]], 6)
        self.assertEqual(result.assignment, (0,))
        self.assertEqual(result.score, 6)

    def test_equal_guilds_share_the_best_equal_rank(self):
        result = optimize([[None, None, 2]] * 3, 3)
        self.assertEqual(result.score, 7)

    def test_respects_individual_size_limits(self):
        result = optimize([[0, 1, 2]] * 4, 3, [2, 1, 1], [2, 1, 1])
        self.assertEqual([result.assignment.count(guild) for guild in range(3)], [2, 1, 1])


class RequestValidationTests(unittest.TestCase):
    def make_request(self, name):
        return {
            "guilds": ["A", "B", "C", "D", "E", "F"],
            "vikings": [
                {"name": name if index == 0 else f"Extra{index}", "ranking": [0, 1, 2, 3, 4, 5]}
                for index in range(18)
            ],
        }

    def test_accepts_letters_umlauts_and_digits(self):
        _, names, _, _, _ = validate_request(self.make_request("ÄgirÖrn2"))
        self.assertEqual(names[0], "ÄgirÖrn2")

    def test_accepts_spaces_points_and_underscores(self):
        for name in ("Name MitLeerzeichen", "Name_Unterstrich", "Name.2"):
            with self.subTest(name=name):
                _, names, _, _, _ = validate_request(self.make_request(name))
                self.assertEqual(names[0], name)

    def test_rejects_unsupported_punctuation(self):
        for name in ("Erik-2", "Erik!", "Erik/2"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_request(self.make_request(name))

    def test_rejects_more_than_fifty_characters(self):
        with self.assertRaises(ValueError):
            validate_request(self.make_request("A" * 51))

    def test_rejects_unsafe_guild_names(self):
        for guild_name in ("Gilde Nord", "Gilde-1", "<script>", "A" * 51):
            data = self.make_request("Erik")
            data["guilds"][0] = guild_name
            with self.subTest(guild_name=guild_name), self.assertRaises(ValueError):
                validate_request(data)

    def test_accepts_safe_guild_names(self):
        data = self.make_request("Erik")
        data["guilds"] = ["Holzfäller2", "Jäger", "Köche", "Bauern", "Schmelzer", "Steinmetze"]
        guilds, _, _, _, _ = validate_request(data)
        self.assertEqual(guilds, ["Holzfäller2", "Jäger", "Köche", "Bauern", "Schmelzer", "Steinmetze"])

    def test_requires_exactly_six_guilds(self):
        for guild_count in (5, 7):
            data = self.make_request("Erik")
            data["guilds"] = [f"Gilde{index}" for index in range(guild_count)]
            data["vikings"][0]["ranking"] = list(range(guild_count))
            with self.subTest(guild_count=guild_count), self.assertRaises(ValueError):
                validate_request(data)

    def test_validates_stored_configuration(self):
        data = self.make_request("Ägir2")
        data["version"] = 1
        data["vikings"][0]["seedDigit"] = 7
        result = validate_configuration(data)
        self.assertNotIn("seedDigit", result["vikings"][0])

    def test_accepts_equal_tail(self):
        data = self.make_request("Erik")
        data["vikings"][0]["ranking"] = [0, 1, 2, 3, None, None]
        _, _, rankings, _, _ = validate_request(data)
        self.assertEqual(rankings[0], [0, 1, 2, 3, None, None])

    def test_replaces_single_equal_with_only_missing_guild(self):
        data = self.make_request("Erik")
        data["vikings"][0]["ranking"] = [0, 1, 2, 3, None, 5]
        _, _, rankings, _, _ = validate_request(data)
        self.assertEqual(rankings[0], [0, 1, 2, 3, 4, 5])

    def test_accepts_entry_after_equal(self):
        data = self.make_request("Erik")
        data["vikings"][0]["ranking"] = [0, None, None, 3, 4, 5]
        _, _, rankings, _, _ = validate_request(data)
        self.assertEqual(rankings[0], [0, None, None, 3, 4, 5])

    def test_reports_rank_of_equal_block(self):
        self.assertEqual(assigned_preference([0, None, None, 3], 2), (2, True))
        self.assertEqual(assigned_preference([0, None, None, 3], 3), (4, False))

    def test_resolves_fixed_and_automatic_guild_sizes(self):
        minimum, maximum = resolve_size_limits(18, [2, 2, 2, 5, 4, 3], [3, 3, 3, 6, 5, 4])
        self.assertEqual(minimum, [2, 2, 2, 5, 4, 3])
        self.assertEqual(maximum, [3, 3, 3, 6, 5, 4])

    def test_accepts_custom_minimum_and_maximum_per_guild(self):
        data = self.make_request("Erik")
        data["guildMinimumSizes"] = [2, 2, 2, 4, 4, 4]
        data["guildMaximumSizes"] = [4, 4, 4, 7, 6, 5]
        _, _, _, minimum, maximum = validate_request(data)
        self.assertEqual(minimum, data["guildMinimumSizes"])
        self.assertEqual(maximum, data["guildMaximumSizes"])

    def test_rejects_guild_sizes_outside_two_to_eight(self):
        for value in (1, 9):
            data = self.make_request("Erik")
            data["guildMinimumSizes"] = [value, 2, 2, 5, 4, 3]
            data["guildMaximumSizes"] = [8, 3, 3, 6, 5, 4]
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_request(data)

    def test_rejects_impossible_fixed_guild_sizes(self):
        data = self.make_request("Erik")
        data["guildSizes"] = [1, 1, 1, 1, 1, 1]
        with self.assertRaises(ValueError):
            validate_request(data)

    def test_accepts_twenty_vikings_but_rejects_twenty_one(self):
        data = self.make_request("Erik0")
        data["vikings"] = [
            {"name": f"Erik{index}", "ranking": [0, 1, 2, 3, 4, 5]}
            for index in range(20)
        ]
        validate_request(data)
        data["vikings"].append({"name": "Erik20", "ranking": [0, 1, 2, 3, 4, 5]})
        with self.assertRaises(ValueError):
            validate_request(data)

    def test_configuration_path_stays_in_storage_directory(self):
        self.assertEqual(configuration_path("Fest.2026").parent, CONFIG_DIR.resolve())
        for name in ("../fremd", "mit leerzeichen", "name/teil"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                configuration_path(name)


class AuthenticationTests(unittest.TestCase):
    def test_login_creates_reusable_session(self):
        auth = Authentication("ein-sehr-langes-passwort")
        result = auth.login("127.0.0.1", "ein-sehr-langes-passwort")
        self.assertIsNotNone(result)
        token, session = result
        self.assertIs(auth.session(token), session)
        auth.logout(token)
        self.assertIsNone(auth.session(token))

    def test_wrong_password_is_rejected(self):
        auth = Authentication("ein-sehr-langes-passwort")
        self.assertIsNone(auth.login("127.0.0.1", "falsch"))

    def test_repeated_failures_do_not_lock_out_shared_proxy_address(self):
        auth = Authentication("ein-sehr-langes-passwort")
        for _ in range(6):
            self.assertIsNone(auth.login("127.0.0.1", "falsch"))
        self.assertIsNotNone(auth.login("127.0.0.1", "ein-sehr-langes-passwort"))


class DefaultVikingTests(unittest.TestCase):
    def test_missing_local_file_uses_generic_names(self):
        missing = Path(__file__).resolve().parent / "nicht_vorhandene_standardnamen.json"
        with patch("server.DEFAULT_VIKINGS_FILE", missing):
            self.assertEqual(load_default_vikings(), [f"Wikinger{index}" for index in range(1, 19)])

    def test_non_utf8_local_file_uses_generic_names(self):
        invalid = Path(__file__).resolve().parent / "ungueltige_standardnamen.json"
        try:
            invalid.write_bytes(b"\xff\xfe")
            with patch("server.DEFAULT_VIKINGS_FILE", invalid):
                self.assertEqual(load_default_vikings(), [f"Wikinger{index}" for index in range(1, 19)])
        finally:
            invalid.unlink(missing_ok=True)


class ConfigurationStorageTests(unittest.TestCase):
    def test_parallel_saves_leave_one_complete_json_file(self):
        target = configuration_path("UnittestParallel")
        errors = []
        barrier = threading.Barrier(4)

        def save(index):
            try:
                barrier.wait()
                save_configuration(target, {
                    "version": 1,
                    "guilds": [f"A{index}", "B", "C", "D", "E", "F"],
                    "vikings": [{"name": f"Erik{index}", "ranking": [0, 1, 2, 3, 4, 5]}],
                })
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=save, args=(index,)) for index in range(4)]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            stored = json.loads(target.read_text(encoding="utf-8"))
            self.assertIn(stored["vikings"][0]["name"], {f"Erik{index}" for index in range(4)})
            self.assertEqual(list(CONFIG_DIR.glob(f".{target.name}.*.tmp")), [])
        finally:
            target.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
