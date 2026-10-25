"""Pure astronomy-to-axis preview, with no GPIO writes.

Actual motor pointing requires alignment references, rotation direction,
measured travel and a verified home position. NEVER use this as a command
source before those calibrations are available.
"""

def angular_difference(target_degrees, reference_degrees):
    """Signed shortest angular difference in [-180, 180) degrees."""
    return ((target_degrees - reference_degrees + 180) % 360) - 180


def preview_target(altitude, azimuth, home_azimuth=None, azimuth_half_span=45):
    """Calculate visibility/rough accessible sector, not motor commands."""
    if not 0 <= azimuth < 360:
        raise ValueError("Azimuth must be within [0, 360)")
    if not -90 <= altitude <= 90:
        raise ValueError("Altitude must be within [-90, 90]")
    if altitude < 0:
        return "BELOW HORIZON", None
    if home_azimuth is None:
        return "ALIGNMENT REQUIRED", None
    offset = angular_difference(azimuth, home_azimuth)
    if abs(offset) > azimuth_half_span:
        return "OUTSIDE TESTED AZIMUTH SECTOR", offset
    return "AZIMUTH SECTOR CANDIDATE - NOT CALIBRATED", offset
