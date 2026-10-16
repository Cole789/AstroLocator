"""Skyfield calculations, independent of console input and output"""

import math
from pathlib import Path

from skyfield.api import load_file, wgs84

TARGETS = {
    "Moon": "moon",
    "Mercury": "mercury",
    "Venus": "venus",
    "Mars": "mars",
    "Jupiter": "jupiter barycenter",
    "Saturn": "saturn barycenter",
    "Uranus": "uranus barycenter",
    "Neptune": "neptune barycenter",
}

DEFAULT_EPHEMERIS = Path(__file__).resolve().with_name("de421.bsp")

# Checks that a coordinate is a finite number within its allowed range
def validate_coordinate(value, name):
    limits = {"latitude": 90, "longitude": 180}
    limit = limits[name]
    message = f"{name.capitalize()} must be a finite number between {-limit} and {limit}."

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or not -limit <= number <= limit:
        raise ValueError(message)

    return number

# Opens a local ephemeris file without attempting a network download
def load_ephemeris(path=None):
    path = Path(path).expanduser().resolve() if path is not None else DEFAULT_EPHEMERIS
    ephemeris = None

    try:
        ephemeris = load_file(str(path))
        for body in ("earth", *TARGETS.values()):
            ephemeris[body]
        return ephemeris
    except (OSError, ValueError, KeyError) as exc:
        if ephemeris is not None:
            ephemeris.close()
        raise ValueError(
            f"Cannot load ephemeris '{path}': {exc}. "
            "Restore the bundled de421.bsp or supply --ephemeris PATH to a valid DE421 file."
        ) from exc


def calculate_position(ephemeris, instant, latitude, longitude, target):
    """Return apparent altitude and azimuth in degrees, without refraction accounted for

    `instant` is a scalar Skyfield Time. The observer is at sea level on WGS84.
    Azimuth runs clockwise from true north; negative altitude is below horizon.
    """
    latitude = validate_coordinate(latitude, "latitude")
    longitude = validate_coordinate(longitude, "longitude")
    if target not in TARGETS:
        raise ValueError(f"Unknown target: {target}")
    observer = ephemeris["earth"] + wgs84.latlon(latitude, longitude)
    apparent = observer.at(instant).observe(ephemeris[TARGETS[target]]).apparent()
    altitude, azimuth, _ = apparent.altaz()
    return altitude.degrees, azimuth.degrees
