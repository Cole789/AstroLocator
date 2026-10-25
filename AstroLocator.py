"""Line-oriented AstroLocator console: celestial positions and SAFE pointing preview."""
import argparse
import sys

from skyfield.api import load
from coordinates import TARGETS, calculate_position, load_ephemeris, validate_coordinate
from hardware.pointing import preview_target


def coordinate_argument(name):
    def parse(value):
        try:
            return validate_coordinate(value, name)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc
    return parse


def select_target(command, current):
    command = command.strip().lower()
    names = list(TARGETS)
    if not command:
        return current
    if command in ("n", "p"):
        step = 1 if command == "n" else -1
        return names[(names.index(current) + step) % len(names)]
    for name in names:
        if command == name.lower():
            return name
    raise ValueError("Unknown command. Enter a target name, n, p, Enter, or q.")


def prompt_coordinate(name):
    while True:
        value = input("Observer {} in decimal degrees (q to quit): ".format(name)).strip()
        if value.lower() in ("q", "quit"):
            return None
        try:
            return validate_coordinate(value, name)
        except ValueError as exc:
            print(exc)


def run_console(ephemeris, timescale, latitude, longitude, home_azimuth=None):
    print("AstroLocator | Latitude / Longitude: {:.4f}, {:.4f} degrees".format(latitude, longitude))
    print("Targets: " + ", ".join(TARGETS))
    print("Enter: refresh | n/p: next/previous | target name: select | q: quit")
    print("Pointing preview only: NO GPIO MOVEMENT; LASER OFF")
    target = "Moon"
    while True:
        instant = timescale.now()
        altitude, azimuth = calculate_position(ephemeris, instant, latitude, longitude, target)
        print("{} | {} | Altitude: {:.2f} deg | Azimuth: {:.2f} deg".format(
            instant.utc_strftime('%Y-%m-%d %H:%M:%S UTC'), target, altitude, azimuth))
        status, offset = preview_target(altitude, azimuth, home_azimuth=home_azimuth)
        print("Pointing preview: {}{}".format(status,
              " | Azimuth offset: {:+.2f} deg".format(offset) if offset is not None else ""))
        while True:
            command = input("> ").strip()
            if command.lower() in ("q", "quit"):
                return
            try:
                target = select_target(command, target)
                break
            except ValueError as exc:
                print(exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calculate celestial altitude/azimuth without driving motors.")
    parser.add_argument("--latitude", type=coordinate_argument("latitude"),
                        help="Decimal degrees, -90 to 90; north positive")
    parser.add_argument("--longitude", type=coordinate_argument("longitude"),
                        help="Decimal degrees, -180 to 180; east positive")
    parser.add_argument("--ephemeris", help="Path to a local DE421 BSP file")
    parser.add_argument("--home-azimuth", type=float,
                        help="Approximate true bearing (0..360 degrees) of base at 1500 us; preview only")
    args = parser.parse_args(argv)
    if args.home_azimuth is not None and not 0 <= args.home_azimuth < 360:
        parser.error("--home-azimuth must be in [0, 360)")
    ephemeris = None
    try:
        latitude = args.latitude
        longitude = args.longitude
        if latitude is None:
            latitude = prompt_coordinate("latitude")
        if latitude is None:
            return 0
        if longitude is None:
            longitude = prompt_coordinate("longitude")
        if longitude is None:
            return 0
        ephemeris = load_ephemeris(args.ephemeris)
        run_console(ephemeris, load.timescale(builtin=True), latitude, longitude, args.home_azimuth)
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
    except (OSError, ValueError) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        if ephemeris is not None:
            ephemeris.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
