import contextlib
import io
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from skyfield.api import load

import AstroLocator as cli
from coordinates import TARGETS, calculate_position, load_ephemeris, validate_coordinate


class CoordinateValidationTests(unittest.TestCase):
    def test_inclusive_boundaries_and_decimal_strings(self):
        for name, limit in (("latitude", 90), ("longitude", 180)):
            for value in (-limit, 0, limit, " 12.345 "):
                with self.subTest(name=name, value=value):
                    self.assertEqual(validate_coordinate(value, name), float(value))

    def test_invalid_coordinates(self):
        # reject values outside the limits as well as missing or nonfinite numbers
        for name, limit in (("latitude", 90), ("longitude", 180)):
            for value in (-limit - 0.001, limit + 0.001, "", "north", None, "nan", "inf", "-inf"):
                with self.subTest(name=name, value=value):
                    with self.assertRaisesRegex(ValueError, "finite number"):
                        validate_coordinate(value, name)

    def test_prompt_retries(self):
        # enter two bad values before a valid one to check that the prompt keeps trying
        with patch("builtins.input", side_effect=["nan", "91", "51.4779"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.prompt_coordinate("latitude"), 51.4779)
        self.assertEqual(output.getvalue().count("finite number"), 2)

    def test_cli_rejects_invalid_coordinate_before_loading(self):
        with patch.object(cli, "load_ephemeris") as loader, \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as caught:
            cli.main(["--latitude", "nan", "--longitude", "0"])
        self.assertEqual(caught.exception.code, 2)
        loader.assert_not_called()


class CalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ephemeris = load_ephemeris()
        cls.ts = load.timescale(builtin=True)
        # use the same time on every run so the expected positions do not drift
        cls.instant = cls.ts.utc(2024, 1, 1, 0, 0, 0)

    @classmethod
    def tearDownClass(cls):
        cls.ephemeris.close()

    def test_all_targets_have_finite_physical_ranges(self):
        # cover both hemispheres and the poles
        for target in TARGETS:
            for latitude, longitude in ((51.4779, -0.0015), (-33.8688, 151.2093),
                                        (90, 180), (-90, -180)):
                with self.subTest(target=target, location=(latitude, longitude)):
                    altitude, azimuth = calculate_position(
                        self.ephemeris, self.instant, latitude, longitude, target)
                    self.assertTrue(math.isfinite(altitude) and math.isfinite(azimuth))
                    self.assertTrue(-90 <= altitude <= 90)
                    self.assertTrue(0 <= azimuth < 360)

    def test_fixed_time_regression(self):
        # these saved values come from skyfield and de421, not an independent source
        # they catch changes in our results but cannot prove skyfield is accurate
        expected = {
            "Moon": (28.174847, 107.107384),
            "Mercury": (-55.536189, 31.507178),
            "Venus": (-45.132296, 58.018426),
            "Mars": (-60.701353, 25.029804),
            "Jupiter": (24.155080, 259.071074),
            "Saturn": (-30.308276, 290.654066),
            "Uranus": (36.101061, 250.985909),
            "Neptune": (-11.217315, 279.254714),
        }
        for target, (expected_altitude, expected_azimuth) in expected.items():
            with self.subTest(target=target):
                altitude, azimuth = calculate_position(
                    self.ephemeris, self.instant, 51.4779, -0.0015, target)
                self.assertAlmostEqual(altitude, expected_altitude, delta=0.001)
                self.assertAlmostEqual(azimuth, expected_azimuth, delta=0.001)

    def test_time_location_and_target_affect_result(self):
        baseline = calculate_position(self.ephemeris, self.instant, 0, 0, "Moon")
        # change one input at a time to catch inputs that are accidentally ignored
        for instant, latitude, longitude, target in (
            (self.ts.utc(2024, 1, 1, 6), 0, 0, "Moon"),
            (self.instant, 45, 0, "Moon"),
            (self.instant, 0, 90, "Moon"),
            (self.instant, 0, 0, "Mars"),
        ):
            result = calculate_position(self.ephemeris, instant, latitude, longitude, target)
            self.assertGreater(max(abs(a - b) for a, b in zip(baseline, result)), 1)

    def test_invalid_calculation_inputs(self):
        for latitude, longitude, target in ((91, 0, "Moon"), (0, 181, "Moon"),
                                            (0, 0, "Pluto")):
            with self.assertRaises(ValueError):
                calculate_position(self.ephemeris, self.instant, latitude, longitude, target)

    def test_out_of_range_time(self):
        with self.assertRaises(ValueError):
            calculate_position(self.ephemeris, self.ts.utc(2200, 1, 1), 0, 0, "Moon")


class LoadingTests(unittest.TestCase):
    def test_default_load_from_another_working_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                ephemeris = load_ephemeris()
                ephemeris.close()
            finally:
                # restore the working directory even if loading fails
                os.chdir(original)

    def test_missing_and_corrupt_files_have_actionable_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.bsp"
            with self.assertRaisesRegex(ValueError, "Restore the bundled de421.bsp"):
                load_ephemeris(path)
            path.write_bytes(b"not a kernel")
            with self.assertRaisesRegex(ValueError, "Cannot load ephemeris"):
                load_ephemeris(path)

    def test_import_has_no_console_or_loading_side_effects(self):
        # use a fresh process so an earlier import cannot hide startup behavior
        root = Path(cli.__file__).parent
        result = subprocess.run(
            [sys.executable, "-c", "import AstroLocator"], cwd=root,
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


class ConsoleTests(unittest.TestCase):
    def test_target_selection_and_wraparound(self):
        self.assertEqual(cli.select_target("p", "Moon"), "Neptune")
        self.assertEqual(cli.select_target("n", "Neptune"), "Moon")
        self.assertEqual(cli.select_target("", "Mars"), "Mars")
        for target in TARGETS:
            self.assertEqual(cli.select_target(f" {target.upper()} ", "Moon"), target)
        with self.assertRaises(ValueError):
            cli.select_target("not a target", "Moon")

    def test_selection_calculates_before_next_prompt_without_extra_redraws(self):
        instant = load.timescale(builtin=True).utc(2024, 1, 1)
        timescale = Mock()
        # freeze the clock and feed commands without needing a real terminal
        timescale.now.return_value = instant
        commands = iter(["mars", "n", "", "bad", "q"])
        selected = []
        output = io.StringIO()

        def calculate(ephemeris, time, latitude, longitude, target):
            selected.append(target)
            self.assertIs(time, instant)
            # give each calculation a different altitude so stale output is easy to spot
            return len(selected), 123.0

        def read(prompt):
            # the latest result must be printed before asking for another command
            self.assertIn(f"{selected[-1]} | Altitude: {len(selected):.2f}", output.getvalue())
            return next(commands)

        with patch.object(cli, "calculate_position", side_effect=calculate), \
                patch("builtins.input", side_effect=read), contextlib.redirect_stdout(output):
            cli.run_console(Mock(), timescale, 51, -1)
        self.assertEqual(selected, ["Moon", "Mars", "Jupiter", "Jupiter"])
        # an invalid command should not trigger another calculation or redraw
        self.assertEqual(output.getvalue().count("UTC |"), 4)
        self.assertIn("Latitude / Longitude: 51.0000, -1.0000", output.getvalue())

    def test_interrupt_and_eof_close_ephemeris(self):
        # simulate both exit signals and check that the open file is closed
        for exception in (KeyboardInterrupt, EOFError):
            ephemeris = Mock()
            with patch.object(cli, "load_ephemeris", return_value=ephemeris), \
                    patch.object(cli, "run_console", side_effect=exception), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["--latitude", "0", "--longitude", "0"]), 0)
            ephemeris.close.assert_called_once()

    def test_quit_and_interrupt_at_coordinate_prompt(self):
        for value in ("q", KeyboardInterrupt, EOFError):
            with patch("builtins.input", side_effect=[value]), \
                    patch.object(cli, "load_ephemeris") as loader, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main([]), 0)
            loader.assert_not_called()

    def test_load_error_returns_failure(self):
        with patch.object(cli, "load_ephemeris", side_effect=ValueError("missing kernel")), \
                contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(cli.main(["--latitude", "0", "--longitude", "0"]), 1)
        self.assertIn("missing kernel", output.getvalue())


if __name__ == "__main__":
    unittest.main()
