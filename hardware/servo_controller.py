"""GPIO servo control for AstroLocator. Requires pigpio only when instantiated.

Pulse widths are electrical commands, NOT measured servo angles. Hardware
travel limits have to be established independently before widening bounds.
"""

import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AxisConfig:
    pin: int
    minimum: int
    maximum: int
    center: int = 1500
    name: str = "axis"

    def __post_init__(self):
        if not (500 <= self.minimum < self.center < self.maximum <= 2500):
            raise ValueError("Invalid pulse limits for {}".format(self.name))

    def validate(self, pulse):
        pulse = int(pulse)
        if not self.minimum <= pulse <= self.maximum:
            raise ValueError("{} pulse {} outside {}-{} us".format(
                self.name, pulse, self.minimum, self.maximum))
        return pulse


# VERIFIED test windows, not a claim of full mechanical clearance.
AZIMUTH = AxisConfig(21, 1100, 1900, 1500, "azimuth (HS-755HB)")
ALTITUDE = AxisConfig(14, 1000, 1975, 1500, "altitude (MG996R)")


class ServoController:
    """Manual command controller. Does NOT actuate anything on construction.

    The controller cannot read physical shaft position. A pulse ramp is not
    closed-loop motion control; initial moves may be larger than the ramp step.
    """

    def __init__(self, azimuth=AZIMUTH, altitude=ALTITUDE, pi=None):
        self.azimuth = azimuth
        self.altitude = altitude
        if azimuth.pin == altitude.pin:
            raise ValueError("Axis pins must be different")
        self._owns_pi = pi is None
        if pi is None:
            try:
                import pigpio
            except ImportError as exc:
                raise RuntimeError("Install python3-pigpio on the Raspberry Pi") from exc
            pi = pigpio.pi()
        if not pi.connected:
            raise RuntimeError("pigpiod unavailable: run 'sudo pigpiod' on the Pi")
        self.pi = pi
        self.last_azimuth = None
        self.last_altitude = None
        self._closed = False

    def write(self, axis, pulse):
        config = self._config(axis)
        value = config.validate(pulse)
        result = self.pi.set_servo_pulsewidth(config.pin, value)
        if result is not None and result < 0:
            raise RuntimeError("pigpio write failed on GPIO {}: {}".format(config.pin, result))
        if axis == "azimuth":
            self.last_azimuth = value
        else:
            self.last_altitude = value
        return value

    def _config(self, axis):
        if axis == "azimuth":
            return self.azimuth
        if axis == "altitude":
            return self.altitude
        raise ValueError("Unknown axis: {}".format(axis))

    def ramp(self, axis, target, step=10, delay=0.02):
        """Gradually vary commanded pulse; requires a known last command.

        For safety, a never-commanded axis is NOT ramped from an assumed
        starting position. Activate it deliberately with write() first.
        """
        config = self._config(axis)
        target = config.validate(target)
        if step <= 0 or delay < 0:
            raise ValueError("step must be positive and delay nonnegative")
        current = self.last_azimuth if axis == "azimuth" else self.last_altitude
        if current is None:
            raise RuntimeError("Axis not activated: establish a safe starting pulse first")
        while current != target:
            delta = min(step, abs(target - current))
            current += delta if target > current else -delta
            self.write(axis, current)
            time.sleep(delay)
        return current

    def stop(self):
        """Stop PWM signals; does not electrically disconnect servo power."""
        if self._closed:
            return
        try:
            self.pi.set_servo_pulsewidth(self.azimuth.pin, 0)
            self.pi.set_servo_pulsewidth(self.altitude.pin, 0)
        finally:
            if self._owns_pi:
                self.pi.stop()
            self.last_azimuth = None
            self.last_altitude = None
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
