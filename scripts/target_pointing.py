"""Interactive console planetary pointing, with emitter disabled externally.

No PWM commands are sent until a complete, in-range plan is approved.
Physical alignment must be measured; no reliable automatic homing is possible
with these standard positional servos alone.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skyfield.api import load
from coordinates import TARGETS, calculate_position, load_ephemeris, validate_coordinate
from hardware.targeting import (Alignment, CARDINALS, plan_pointing,
                                suggest_direction)
from hardware.servo_controller import ServoController, AZIMUTH, ALTITUDE


def ask_float(label, default=None):
    suffix = " [{}]".format(default) if default is not None else ""
    while True:
        raw = input(label + suffix + ": ").strip()
        try:
            value = float(raw or default)
            import math
            if math.isfinite(value):
                return value
        except (ValueError, TypeError):
            pass
        print("Enter a finite number.")


def configure_alignment():
    print("\nAlignment uses TRUE cardinal directions (not magnetic headings).")
    print("With power/control disengaged, manually orient the base so its")
    print("1500 us azimuth CENTER points exactly N, E, S or W.")
    while True:
        direction = input("Aligned cardinal direction [N/E/S/W]: ").strip().upper()
        if direction in CARDINALS:
            break
    print("Provide MEASURED calibration data; no default is assumed for altitude.")
    az_span = ask_float("Measured positive angle (degrees) from 1500 to 1900 us")
    if not 0 < az_span <= 180:
        raise ValueError("Invalid measured azimuth angular span")
    sign = input("Does increasing azimuth pulse turn EAST? [y/n]: ").strip().lower()
    if sign not in ("y", "n"):
        raise ValueError("Answer y or n")
    alt_zero = round(ask_float("Measured pulse pointing the upper axis HORIZONTALLY (0 deg)"))
    alt_angle = ask_float("A second measured altitude angle (degrees; not 0)")
    alt_pulse = ask_float("Pulse that produces that measured altitude angle")
    if not -90 <= alt_angle <= 90 or alt_angle == 0:
        raise ValueError("Second altitude angle must be nonzero within -90..90")
    if not ALTITUDE.minimum <= alt_pulse <= ALTITUDE.maximum:
        raise ValueError("Second altitude pulse outside configured limits")
    return Alignment(direction, 400.0 / az_span, 1 if sign == "y" else -1,
                     alt_zero, (alt_pulse - alt_zero) / alt_angle)


def run_targeting(latitude, longitude, ephemeris):
    ts = load.timescale(builtin=True)
    print("\nLASER EMITTER MUST BE ELECTRICALLY DISABLED.")
    print("Unverified centering, calibration or mechanical load can cause mispointing.")
    alignment = configure_alignment()
    print("Align 1500 us azimuth at TRUE {} ({} degrees).".format(
        alignment.cardinal, CARDINALS[alignment.cardinal]))
    print("Controller does not remember shaft position; initial motion can be abrupt.")
    with ServoController() as servos:
        while True:
            print("\nTargets: " + ", ".join(TARGETS))
            name = input("Target name, 'align' to recalibrate, or 'q': ").strip()
            if name.lower() in ("q", "quit"):
                break
            if name.lower() == "align":
                alignment = configure_alignment()
                # stop controlling axes between physical re-alignments
                servos.pi.set_servo_pulsewidth(AZIMUTH.pin, 0)
                servos.pi.set_servo_pulsewidth(ALTITUDE.pin, 0)
                servos.last_azimuth = None
                servos.last_altitude = None
                continue
            target = next((t for t in TARGETS if t.lower() == name.lower()), None)
            if target is None:
                print("Unknown target.")
                continue
            instant = ts.now()
            alt, az = calculate_position(ephemeris, instant, latitude, longitude, target)
            desired = suggest_direction(az)
            print("{} at {} UTC | altitude {:.2f} deg | azimuth {:.2f} deg".format(
                target, instant.utc_strftime('%Y-%m-%d %H:%M:%S'), alt, az))
            print("Suggested base alignment for best coverage: {} (true heading {} deg)".format(
                desired, CARDINALS[desired]))
            print("Current alignment: {}. To change it, type 'align' at next prompt.".format(
                alignment.cardinal))
            plan = plan_pointing(az, alt, alignment)
            if not plan.reachable:
                print("REJECTED - {}. Neither servo was commanded.".format(plan.reason))
                continue
            print("VALID COMMAND: azimuth {} us / altitude {} us".format(
                plan.azimuth_pulse, plan.altitude_pulse))
            if input("LASER OFF, mechanism clear, servo centers safe; move axes? [type MOVE]: ").strip() != "MOVE":
                print("Canceled. Neither servo was commanded.")
                continue
            # Recompute immediately before motion to guard against changing sky positions.
            new_alt, new_az = calculate_position(ephemeris, ts.now(), latitude, longitude, target)
            updated = plan_pointing(new_az, new_alt, alignment)
            if not updated.reachable:
                print("REJECTED after recalculation; neither axis moved.")
                continue
            # Explicitly initialize at previously checked electrical center.
            # This is NOT an absolute-position measurement, nor an interlock.
            if servos.last_azimuth is None or servos.last_altitude is None:
                print("Initializing to 1500 us may move the mechanism unexpectedly.")
                if input("Confirm both 1500 us centers are physically safe [type CENTER]: ").strip() != "CENTER":
                    print("Canceled.")
                    continue
                servos.write("azimuth", 1500)
                servos.write("altitude", 1500)
            try:
                servos.ramp("azimuth", updated.azimuth_pulse)
                servos.ramp("altitude", updated.altitude_pulse)
                print("Commands sent. This does not verify actual pointing or laser safety.")
            except Exception:
                servos.stop()
                raise


def main():
    eph = None
    try:
        latitude = validate_coordinate(ask_float("Observer latitude (decimal degrees)"), "latitude")
        longitude = validate_coordinate(ask_float("Observer longitude (decimal degrees)"), "longitude")
        eph = load_ephemeris()
        run_targeting(latitude, longitude, eph)
    except (KeyboardInterrupt, EOFError):
        print("\nExited.")
    except (ValueError, RuntimeError, OSError) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        if eph is not None:
            eph.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
