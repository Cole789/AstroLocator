"""Line-oriented console interface for AstroLocator"""

import argparse
import sys

from skyfield.api import load
from coordinates import TARGETS, calculate_position, load_ephemeris, validate_coordinate

# Creates a command-line parser that checks whether a coordinate is valid
def coordinate_argument(name):
    def parse(value):
        try:
            return validate_coordinate(value, name)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc
    return parse

# Resolves a refresh, navigation command, or case-insensitive target name
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

# Asks for a valid coordinate and lets the user quit if needed
def prompt_coordinate(name):
    while True:
        value = input(f"Observer {name} in decimal degrees (q to quit): ").strip()
        if value.lower() in ("q", "quit"):
            return None
        try:
            return validate_coordinate(value, name)
        except ValueError as exc:
            print(exc)

# Runs the interactive console for viewing target positions
def run_console(ephemeris, timescale, latitude, longitude):
    print("AstroLocator | Latitude / Longitude: " f"{latitude:.4f}, {longitude:.4f} degrees")
    print("Targets: " + ", ".join(TARGETS))
    print("Enter: refresh | n/p: next/previous | target name: select | q: quit")
    target = "Moon" # Default target
    while True:
        instant = timescale.now()
        altitude, azimuth = calculate_position(
            ephemeris, instant, latitude, longitude, target
        )
        print(f"{instant.utc_strftime('%Y-%m-%d %H:%M:%S UTC')} | {target} | " f"Altitude: {altitude:.2f} deg | Azimuth: {azimuth:.2f} deg")
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
    parser = argparse.ArgumentParser(description="Calculate Moon and planet altitude/azimuth.")
    parser.add_argument("--latitude", type=coordinate_argument("latitude"), help="Decimal degrees, -90 to 90; north is positive")
    parser.add_argument("--longitude", type=coordinate_argument("longitude"), help="Decimal degrees, -180 to 180; east is positive")
    parser.add_argument("--ephemeris", help="Path to a local DE421 BSP file")
    args = parser.parse_args(argv)
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
        run_console(ephemeris, load.timescale(builtin=True), latitude, longitude)
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if ephemeris is not None:
            ephemeris.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
