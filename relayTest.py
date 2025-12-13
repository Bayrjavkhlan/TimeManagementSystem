cd ~/Documents/piJack
cat > relayTest.py << 'EOF'
import RPi.GPIO as GPIO
import time
import board
import adafruit_dht
import threading

# === PINS ===
LIGHT_PIN  = 20
FAN_PIN    = 21
BUZZER_PIN = 18        # GPIO 18 is perfect and safe
DHT_PIN    = board.D2

# === SETUP ===
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LIGHT_PIN, GPIO.OUT)
GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# VERY IMPORTANT: keep buzzer LOW by default (active buzzers scream on HIGH!)
GPIO.output(LIGHT_PIN, GPIO.HIGH)   # relay OFF
GPIO.output(FAN_PIN, GPIO.HIGH)     # relay OFF
GPIO.output(BUZZER_PIN, GPIO.LOW)   # buzzer silent

dht_device = adafruit_dht.DHT11(DHT_PIN, use_pulseio=False)
TEMP_THRESHOLD = 20.0
manual_fan_control = False

# === CORRECT SHORT BEEP (works with active buzzers) ===
def beep(times=1, duration=0.08):
    for _ in range(times):
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(duration)
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        time.sleep(0.08)   # small pause between beeps

# === DHT11 READ ===
def read_dht():
    for _ in range(8):
        try:
            temp = dht_device.temperature
            hum = dht_device.humidity
            if temp is not None:
                return temp, hum
        except:
            time.sleep(0.5)
    return None, None

# === AUTO FAN ===
def auto_fan_control():
    while True:
        if manual_fan_control:
            time.sleep(5)
            continue
        temp, _ = read_dht()
        if temp is None:
            time.sleep(5)
            continue
        if temp > TEMP_THRESHOLD and GPIO.input(FAN_PIN) == GPIO.HIGH:
            GPIO.output(FAN_PIN, GPIO.LOW)
            beep(2)   # two short beeps
            print(f"\nAUTO FAN ON ({temp:.1f}°C)")
        elif temp <= TEMP_THRESHOLD and GPIO.input(FAN_PIN) == GPIO.LOW:
            GPIO.output(FAN_PIN, GPIO.HIGH)
            beep(1)   # one short beep
            print(f"\nAUTO FAN OFF ({temp:.1f}°C)")
        time.sleep(5)

threading.Thread(target=auto_fan_control, daemon=True).start()

print("System ready — buzzer on GPIO18 (active buzzer mode)")
print("f = toggle fan | l = toggle light | t = temp | q = quit\n")

try:
    while True:
        cmd = input("→ ").strip().lower()
        if cmd == "f":
            manual_fan_control = True
            current = GPIO.input(FAN_PIN)
            GPIO.output(FAN_PIN, not current)
            beep(2)
            state = "ON" if not current else "OFF"
            print(f"Manual Fan → {state}")
        elif cmd == "l":
            current = GPIO.input(LIGHT_PIN)
            GPIO.output(LIGHT_PIN, not current)
            beep(1)
            state = "ON" if not current else "OFF"
            print(f"Light → {state}")
        elif cmd == "t":
            t, h = read_dht()
            if t:
                print(f"Temp: {t:.1f}°C  Hum: {h:.1f}%")
        elif cmd == "q":
            break
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
    print("\nCleaned up — goodbye!")
EOF