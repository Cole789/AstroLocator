
"""AstroLocator — calibrated celestial targeting console."""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skyfield.api import load
from coordinates import (
    TARGETS,
    calculate_position,
    load_ephemeris,
    validate_coordinate,
)
from hardware.targeting import (
    Alignment,
    CARDINALS,
    plan_pointing,
    suggest_direction,
)
from hardware.servo_controller import ServoController

# ---- Display colors ----

USE_COLOR = sys.stdout.isatty()

GREEN = "\033[92m" if USE_COLOR else ""
RED = "\033[91m" if USE_COLOR else ""
YELLOW = "\033[93m" if USE_COLOR else ""
WHITE = "\033[97m" if USE_COLOR else ""
RESET = "\033[0m" if USE_COLOR else ""


def status(message, color=GREEN):
    print(color + message + RESET)


def prompt(message):
    return input(WHITE + message + RESET).strip()


# ---- Default calibration ----
# These are estimated measurements, not verified angles.

DEFAULT_CARDINAL = "E"
DEFAULT_AZ_SPAN = 45.0
DEFAULT_AZ_SIGN = 1

DEFAULT_ALT_ZERO = 1300
DEFAULT_ALT_ANGLE = 45.0
DEFAULT_ALT_PULSE = 1500

DEFAULT_AZ_US_PER_DEGREE = 400.0 / DEFAULT_AZ_SPAN
DEFAULT_ALT_US_PER_DEGREE = (
    (DEFAULT_ALT_PULSE - DEFAULT_ALT_ZERO)
    / DEFAULT_ALT_ANGLE
)


def default_alignment():
    return Alignment(
        DEFAULT_CARDINAL,
        DEFAULT_AZ_US_PER_DEGREE,
        DEFAULT_AZ_SIGN,
        DEFAULT_ALT_ZERO,
        DEFAULT_ALT_US_PER_DEGREE,
    )


def ask_number(label, default=None):
    while True:
        suffix = " [{}]".format(default) if default is not None else ""
        raw = prompt(label + suffix + ": ")

        if not raw and default is not None:
            return float(default)

        try:
            value = float(raw)
            if math.isfinite(value):
                return value
        except ValueError:
            pass

        status("INVALID | Enter a finite number.", RED)


def configure_alignment(current):
    print()
    status("CALIBRATION", YELLOW)
    print("Press Enter to keep each existing value.")

    while True:
        direction = prompt(
            "Center direction N/E/S/W [{}]: ".format(
                current.cardinal
            )
        ).upper() or current.cardinal

        if direction in CARDINALS:
            break

        status("INVALID | Use N, E, S or W.", RED)

    current_span = 400.0 / current.az_us_per_degree

    while True:
        az_span = ask_number(
            "Azimuth travel 1500-1900 us (degrees)",
            round(current_span, 2),
        )
        if 0 < az_span <= 180:
            break
        status("INVALID | Angle must be 0-180.", RED)

    default_sign = "y" if current.az_sign == 1 else "n"

    while True:
        sign = prompt(
            "Increasing azimuth pulse turns east? y/n [{}]: ".format(
                default_sign
            )
        ).lower() or default_sign

        if sign in ("y", "n"):
            break
        status("INVALID | Answer y or n.", RED)

    while True:
        alt_zero = round(
            ask_number(
                "Horizontal altitude pulse (us)",
                current.altitude_zero_pulse,
            )
        )
        if 1000 <= alt_zero <= 1975:
            break
        status("INVALID | Outside 1000-1975 us.", RED)

    while True:
        alt_angle = ask_number(
            "Second altitude angle (degrees)",
            DEFAULT_ALT_ANGLE,
        )
        if -90 <= alt_angle <= 90 and alt_angle != 0:
            break
        status("INVALID | Use a nonzero angle in -90..90.", RED)

    while True:
        alt_pulse = ask_number(
            "Pulse at second altitude angle (us)",
            DEFAULT_ALT_PULSE,
        )
        if 1000 <= alt_pulse <= 1975 and alt_pulse != alt_zero:
            break
        status("INVALID | Pulse must be in range and differ from zero reference.", RED)

    alignment = Alignment(
        direction,
        400.0 / az_span,
        1 if sign == "y" else -1,
        alt_zero,
        (alt_pulse - alt_zero) / alt_angle,
    )

    status("OK | Calibration updated.")
    return alignment


def ask_location():
    while True:
        try:
            latitude = validate_coordinate(
                ask_number("Latitude"),
                "latitude",
            )
            longitude = validate_coordinate(
                ask_number("Longitude"),
                "longitude",
            )
            return latitude, longitude
        except ValueError as exc:
            status("INVALID | {}".format(exc), RED)


def deactivate(servos):
    servos.pi.set_servo_pulsewidth(servos.azimuth.pin, 0)
    servos.pi.set_servo_pulsewidth(servos.altitude.pin, 0)
    servos.last_azimuth = None
    servos.last_altitude = None


def run_targeting(latitude, longitude, ephemeris):
    alignment = default_alignment()
    ts = load.timescale(builtin=True)

    print()
    print(WHITE + "ASTROLOCATOR" + RESET)
    status("READY | Astronomy engine loaded.")
    status("LASER EMITTER MUST REMAIN DISABLED.", RED)
    status(
        "ALIGNMENT | Set 1500 us azimuth toward TRUE East.",
        YELLOW,
    )

    print(
        "Location: {:.4f}, {:.4f}".format(
            latitude, longitude
        )
    )
    print("Calibration: E | +45 deg / 400 us | Alt 0 deg = 1300 us")
    print()

    print(
        WHITE
        + "Targets: " + ", ".join(TARGETS)
        + RESET
    )
    print(
        WHITE
        + "Commands: align | location | status | q"
        + RESET
    )

    with ServoController() as servos:
        while True:
            print()
            command = prompt("astro> ")

            if not command:
                continue

            lowered = command.lower()

            if lowered in ("q", "quit", "exit"):
                break

            if lowered == "status":
                status("READY | GPIO controller connected.")
                print(
                    "Alignment: {} ({} deg true)".format(
                        alignment.cardinal,
                        CARDINALS[alignment.cardinal],
                    )
                )
                print(
                    "Location: {:.4f}, {:.4f}".format(
                        latitude, longitude
                    )
                )
                print("Azimuth: 1100-1900 us")
                print("Altitude: 1000-1975 us")
                continue

            if lowered == "location":
                latitude, longitude = ask_location()
                status("OK | Location updated.")
                continue

            if lowered == "align":
                deactivate(servos)
                status(
                    "PWM OFF | Physically realign before continuing.",
                    YELLOW,
                )
                alignment = configure_alignment(alignment)
                status(
                    "ALIGN | Set azimuth center toward true {}.".format(
                        alignment.cardinal
                    ),
                    YELLOW,
                )
                continue

            target = next(
                (
                    name for name in TARGETS
                    if name.lower() == lowered
                ),
                None,
            )

            if target is None:
                status("INVALID | Unknown command or target.", RED)
                continue

            status("CALCULATING | {}".format(target), YELLOW)

            instant = ts.now()

            altitude, azimuth = calculate_position(
                ephemeris,
                instant,
                latitude,
                longitude,
                target,
            )

            print(
                "{} | Alt {:.2f} deg | Az {:.2f} deg".format(
                    target, altitude, azimuth
                )
            )

            desired = suggest_direction(azimuth)
            plan = plan_pointing(
                azimuth,
                altitude,
                alignment,
            )

            if not plan.reachable:
                status(
                    "REJECTED | {}".format(plan.reason),
                    RED,
                )
                print(
                    "Suggested alignment: {} ({} deg true)".format(
                        desired,
                        CARDINALS[desired],
                    )
                )
                continue

            status("IN RANGE | Both axes reachable.")

            print(
                "AZ {} us | ALT {} us".format(
                    plan.azimuth_pulse,
                    plan.altitude_pulse,
                )
            )

            approval = prompt(
                "Move servos? [MOVE/cancel]: "
            )

            if approval != "MOVE":
                status("CANCELED | No motion commanded.", YELLOW)
                continue

            status("CALCULATING | Refreshing position...", YELLOW)

            new_alt, new_az = calculate_position(
                ephemeris,
                ts.now(),
                latitude,
                longitude,
                target,
            )

            updated = plan_pointing(
                new_az,
                new_alt,
                alignment,
            )

            if not updated.reachable:
                status("REJECTED | Updated target out of range.", RED)
                continue

            if (
                servos.last_azimuth is None
                or servos.last_altitude is None
            ):
                status(
                    "WARNING | Initial center movement may be abrupt.",
                    YELLOW,
                )

                center_ok = prompt(
                    "Centers clear and laser disabled? [CENTER/cancel]: "
                )

                if center_ok != "CENTER":
                    status("CANCELED | No motion commanded.", YELLOW)
                    continue

                servos.write("azimuth", 1500)
                servos.write("altitude", 1500)

            status("MOVING | Sending servo commands...", YELLOW)

            try:
                servos.ramp(
                    "azimuth",
                    updated.azimuth_pulse,
                )
                servos.ramp(
                    "altitude",
                    updated.altitude_pulse,
                )
                status("OK | Servo commands completed.")
            except Exception:
                deactivate(servos)
                raise


def main():
    ephemeris = None

    try:
        print(WHITE + "ASTROLOCATOR SETUP" + RESET)
        latitude, longitude = ask_location()

        status("LOADING | Ephemeris...", YELLOW)
        ephemeris = load_ephemeris()

        run_targeting(
            latitude,
            longitude,
            ephemeris,
        )

    except (KeyboardInterrupt, EOFError):
        print()
        status("EXITED", YELLOW)

    except (ValueError, RuntimeError, OSError) as exc:
        status("ERROR | {}".format(exc), RED)
        return 1

    finally:
        if ephemeris is not None:
            ephemeris.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
