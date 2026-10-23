# Network settings for the robot.
#
# MODE = "ap"  -> the Pico W makes its own Wi-Fi network. Connect your phone or
#                 laptop to AP_SSID and open http://192.168.4.1
#                 Works anywhere, no router needed (best at a competition).
# MODE = "sta" -> the Pico W joins an existing WPA2-Personal network (home
#                 router, phone hotspot). The IP it gets is printed in Thonny's
#                 Shell. Campus networks like eduroam (WPA2-Enterprise) will
#                 NOT work. If joining fails, it falls back to AP mode.

MODE = "ap"

# Used when MODE = "ap". Password must be at least 8 characters.
AP_SSID = "PicoBot-01"
AP_PASSWORD = "drivebot123"

# Used when MODE = "sta".
SSID = "SSID"
PASSWORD = "PASSWORD"

PORT = 80
