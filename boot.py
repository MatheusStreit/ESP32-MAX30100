# boot.py -- run on boot-up
import network
import time

SSID = "BUDD_VISITANTES"
PASSWORD = "budd3m3y3r@1951"

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando ao Wi-Fi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
            print(".", end="")
    print("\nWi-Fi conectado:", wlan.ifconfig())
