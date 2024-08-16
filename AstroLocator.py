import keyboard
from skyfield.api import load, Topos
from colorama import init, Fore, Back, Style
import time  # Import time for time-related functions

# Initialize Colorama
init()

# DATA

# Load ephemeris data for objects
ts = load.timescale()
eph = load('de421.bsp')
earth = eph['earth']
moon = eph['moon']
mercury = eph['mercury']
venus = eph['venus']
mars = eph['mars']
jupiter = eph['jupiter barycenter']
saturn = eph['saturn barycenter']
uranus = eph['uranus barycenter']
neptune = eph['neptune barycenter']

# Define observer's location
userLat = 51.4779
userLong = -0.0015
observer = earth + Topos(latitude_degrees=userLat, longitude_degrees=userLong)

# UI Elements
objects = ["Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]
bodies = {
    "Moon": moon,
    "Mercury": mercury,
    "Venus": venus,
    "Mars": mars,
    "Jupiter": jupiter,
    "Saturn": saturn,
    "Uranus": uranus,
    "Neptune": neptune
}
currentIndex = 0
statusMessage = ""
screenWidth = 110

# Time tracking
last_seconds = -1  # Initialize with an invalid value to ensure the first update

def drawUI():
    # Clear screen
    print("\033c", end="")

    # Get current time
    t = ts.now()
    current_seconds = t.utc_strftime('%S')

    # Header Lines
    print("------------------[ Long / Lat ]---------------------|---------------------[ UTC Time ]--------------------")
    print("                 " + f"{userLat:.4f}, {userLong:.4f} {t.utc_strftime('%H:%M:%S'):>50}")
    print("--------------------------------------------[ Selected Object ]--------------------------------------------")
    print("")

    # Display objects and highlight the selected one
    # Center the object list
    object_line = "   ".join(objects)
    padding = (screenWidth - len(object_line)) // 2
    highlighted_line = " " * padding

    for i, obj in enumerate(objects):
        if i == currentIndex:
            highlighted_line += Back.WHITE + Fore.BLACK + obj + Style.RESET_ALL + "   "
        else:
            highlighted_line += obj + "   "
    
    print(highlighted_line)

    # Footer line with status
    print("")
    print("------------------------------------------------[ Status ]-------------------------------------------------")
    if statusMessage:
        print(">" + f"{statusMessage}".center(screenWidth))
    else:
        print(" ".center(screenWidth))

def calculatePositionOfObject():
    global statusMessage
    t = ts.now()  # Refresh the time
    selected_object = objects[currentIndex]
    statusMessage = f"Calculating position of {selected_object}"
    drawUI()
    
    # Get the Skyfield body for the selected object
    body = bodies[selected_object]
    
    # Get the position of Selected Object
    astrometric = observer.at(t).observe(body)
    alt, az, _ = astrometric.apparent().altaz()
    
    # Update status message with altitude and azimuth
    statusMessage = (f"{selected_object} altitude: {alt.degrees:.2f} degrees | "
                     f"{selected_object} azimuth: {az.degrees:.2f} degrees")
    drawUI()

# Initial draw
drawUI()

# Main loop
while True:
    t = ts.now()
    current_seconds = t.utc_strftime('%S')

    # Update the UI only if the second has changed
    if current_seconds != last_seconds:
        drawUI()
        if objects[currentIndex]:
            calculatePositionOfObject()
        last_seconds = current_seconds

    if keyboard.is_pressed('right'):
        currentIndex = (currentIndex + 1) % len(objects)
        drawUI()
        while keyboard.is_pressed('right'): pass  # Wait until the key is released
    
    if keyboard.is_pressed('left'):
        currentIndex = (currentIndex - 1) % len(objects)
        drawUI()
        while keyboard.is_pressed('left'): pass  # Wait until the key is released
    
    if keyboard.is_pressed('enter'):
        calculatePositionOfObject()
        while keyboard.is_pressed('enter'): pass  # Wait until the key is released