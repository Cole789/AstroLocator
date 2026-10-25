"""Pure pointing geometry. Zero GPIO side effects, including when unreachable."""
from dataclasses import dataclass
import math

from hardware.servo_controller import AZIMUTH, ALTITUDE

CARDINALS = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}


def angle_delta(target, center):
    return ((target - center + 180.0) % 360.0) - 180.0


def suggest_direction(azimuth):
    return min(CARDINALS, key=lambda d: abs(angle_delta(azimuth, CARDINALS[d])))


@dataclass(frozen=True)
class Alignment:
    cardinal: str
    az_us_per_degree: float
    az_sign: int
    altitude_zero_pulse: int
    altitude_us_per_degree: float

    def __post_init__(self):
        if self.cardinal not in CARDINALS:
            raise ValueError("Cardinal must be N, E, S, or W")
        if self.az_sign not in (-1, 1):
            raise ValueError("az_sign must be +1 or -1")
        if not math.isfinite(self.az_us_per_degree) or self.az_us_per_degree <= 0:
            raise ValueError("Azimuth scale must be positive and finite")
        if not math.isfinite(self.altitude_us_per_degree) or self.altitude_us_per_degree == 0:
            raise ValueError("Altitude scale must be nonzero and finite")
        if not ALTITUDE.minimum <= self.altitude_zero_pulse <= ALTITUDE.maximum:
            raise ValueError("Altitude horizon pulse outside tested range")


@dataclass(frozen=True)
class PointingPlan:
    reachable: bool
    reason: str
    azimuth_pulse: int = None
    altitude_pulse: int = None


def plan_pointing(azimuth, altitude, alignment):
    """All-or-nothing bounds check: never partially approve an axis."""
    if not all(math.isfinite(n) for n in (azimuth, altitude)):
        return PointingPlan(False, "Invalid coordinates")
    if not 0 <= azimuth < 360 or not -90 <= altitude <= 90:
        return PointingPlan(False, "Coordinates outside physical angular domain")
    if altitude < 0:
        return PointingPlan(False, "Target is below the horizon")
    delta = angle_delta(azimuth, CARDINALS[alignment.cardinal])
    az_value = 1500 + alignment.az_sign * delta * alignment.az_us_per_degree
    alt_value = alignment.altitude_zero_pulse + altitude * alignment.altitude_us_per_degree
    # Check unrounded first: otherwise round() could hide a tiny out-of-range value.
    if not AZIMUTH.minimum <= az_value <= AZIMUTH.maximum:
        return PointingPlan(False, "Azimuth requires {:.1f} us outside {}-{} us".format(
            az_value, AZIMUTH.minimum, AZIMUTH.maximum))
    if not ALTITUDE.minimum <= alt_value <= ALTITUDE.maximum:
        return PointingPlan(False, "Altitude requires {:.1f} us outside {}-{} us".format(
            alt_value, ALTITUDE.minimum, ALTITUDE.maximum))
    return PointingPlan(True, "Reachable within configured test windows", round(az_value), round(alt_value))
