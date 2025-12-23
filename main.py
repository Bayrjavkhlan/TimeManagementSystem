import os
from openai import OpenAI
os.environ["PYTHONIOENCODING"] = "utf-8"

import customtkinter as ctk
import cv2
import face_recognition
import numpy as np
import time
import datetime
from PIL import Image
import threading
import pyttsx3
from gtts import gTTS
import pygame
import tempfile
import shutil
import requests
import speech_recognition as sr
import RPi.GPIO as GPIO
import board
import adafruit_dht
from playsound import playsound
from PIL import Image as PILImage


# =============================================
# HARDWARE SETUP (DO NOT CHANGE)
# =============================================
LIGHT_PIN = 20   # GPIO 20 → Light relay
FAN_PIN   = 21   # GPIO 21 → Fan relay
BUZZER_PIN  = 18   # Buzzer → GPIO 18 (safe pin)
DHT_PIN   = board.D2  # DHT11 on GPIO 2

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LIGHT_PIN, GPIO.OUT)
GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

GPIO.output(LIGHT_PIN, GPIO.HIGH)  # OFF
GPIO.output(FAN_PIN, GPIO.HIGH)    # OFF
GPIO.output(BUZZER_PIN, GPIO.LOW)   # buzzer silent


dht_device = adafruit_dht.DHT11(DHT_PIN, use_pulseio=False)

# Auto fan control
TEMP_THRESHOLD = 25.0
manual_fan = False  # True = user pressed button → auto disabled

# Light auto control based on people count
active_workers = {}  # name → timestamp
light_auto_on = False

# Temperature display
temp_label = None



# =============================================
# PRE-START HARDWARE TEST – Microphone & Speaker Force Initialize
# =============================================
print("Апп эхлэхээс өмнө микрофон болон чанга яригчийг шалгаж, сэрээж байна...")

# 1. Спикер тест (espeak-ng ашиглаж дуу гаргана – Bluetooth спикер ч ажиллана)
def set_bluetooth_default_sink():
    try:
        # pactl-ээр Bluetooth sink олох
        result = os.popen("pactl list sinks short | grep bluez_output").read().strip()
        if result:
            lines = result.splitlines()
            # Эхний Bluetooth sink-ийг авна (ихэвчлэн нэг л байдаг)
            sink_name = lines[0].split()[1]
            os.system(f"pactl set-default-sink {sink_name}")
            print(f"Аудио default болголоо: {sink_name} ✓")
        else:
            print("Bluetooth спикер sink олдсонгүй ✗")
    except Exception as e:
        print(f"Default sink тохируулах алдаа: {e}")

# Апп эхлэхэд дуудна
set_bluetooth_default_sink()

def test_speaker():
    print("Bluetooth спикер албадан холбож байна (disconnect + reconnect)...")
    
    try:
        # 1. Одоо холбогдсон аудио төхөөрөмжийн MAC address олох
        result = os.popen("bluetoothctl devices Connected").read().strip()
        if not result:
            print("Холбогдсон Bluetooth төхөөрөмж олдсонгүй ✗")
            return False
        
        connected_macs = [line.split()[1] for line in result.splitlines() if line.strip()]
        
        speaker_mac = None
        for mac in connected_macs:
            info = os.popen(f"bluetoothctl info {mac}").read()
            if "Connected: yes" in info and ("Icon: audio" in info.lower() or "UUID: Audio" in info):
                speaker_mac = mac
                break
        
        if not speaker_mac:
            print("Аудио төхөөрөмж (спикер) олдсонгүй ✗")
            return False
        
        print(f"Олдсон спикер: {speaker_mac}")
        
        # 2. Disconnect хийнэ
        os.system(f"bluetoothctl disconnect {speaker_mac} > /dev/null 2>&1")
        time.sleep(2)  # Хүлээж өгнө
        
        # 3. Reconnect хийнэ
        os.system(f"bluetoothctl connect {speaker_mac} > /dev/null 2>&1")
        time.sleep(3)  # Холболтыг хүлээнэ
        
        # 4. Дуу тест хийнэ
        os.system('espeak-ng "Систем бэлэн боллоо" -v mn -s 120 -p 50 -a 50 2>/dev/null')
        print("Спикер амжилттай холбогдож, дуу гарлаа ✓")
        return True
        
    except Exception as e:
        print(f"Спикер холболт алдаа: {e} ✗")
        return False

# 2. Микрофон тест (speech_recognition ашиглаж богино хугацаанд сонсоно)
def test_microphone():
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("Микрофон шалгаж байна... 2 секунд хүлээнэ үү")
            r.adjust_for_ambient_noise(source, duration=1)
            audio = r.listen(source, timeout=2, phrase_time_limit=2)
        print("Микрофон ажиллаж байна ✓")
        return True
    except sr.WaitTimeoutError:
        print("Микрофон дуу сонссонгүй, гэхдээ төхөөрөмж нээгдсэн – ажиллаж магадгүй")
        return True
    except Exception as e:
        print(f"Микрофон алдаа: {e} ✗")
        return False

# 3. Камер тест (нэг frame авна)
def test_camera():
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if ret:
            print("Камер ажиллаж байна ✓")
            return True
        else:
            print("Камер зураг авч чадсангүй ✗")
            return False
    except:
        print("Камер нээгдсэнгүй ✗")
        return False

# Тестүүдийг ажиллуулна
test_speaker()
test_microphone()
test_camera()

print("Төхөөрөмжийн шалгалт дууслаа. GUI эхэлж байна...\n")
time.sleep(1)  # Хэрэглэгч мессежийг харах боломж өгнө


# =============================================
# Mongolian Font Fix (100% working)
# =============================================
try:
    ctk.CTkFont(family="Noto Sans CJK JP", size=36)
    MONGOL_FONT = ("Noto Sans CJK JP", 36, "bold")
except:
    MONGOL_FONT = ("Noto Sans CJK SC", 36, "bold")

_original_init = ctk.CTkLabel.__init__
def _force_font(self, *args, **kwargs):
    kwargs.setdefault("font", MONGOL_FONT)
    _original_init(self, *args, **kwargs)
ctk.CTkLabel.__init__ = _force_font

# =============================================
# Your original code starts here
# =============================================
# API_KEY = ""
GROQ_API_KEY = ""  # <-- Энд өөрийн key-г бич
# API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

def ask_google_ai(prompt):
    if not prompt.strip():
        return "Асуулт хоосон байна"
    
    client = OpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1"
    )
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Та Монгол хэлээр маш товч, ойлгомжтой хариулна уу."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
            timeout=30
        )
        
        answer = response.choices[0].message.content.strip()
        # Терминал дээр Монгол текст зөв хэвлэхийн тулд
        print(f"Groq хариу: {answer}")
        return answer if answer else "Хариу хоосон ирлээ"
        
    except Exception as e:
        # Алдааг аюулгүй хэвлэх
        print("Groq алдаа:", repr(e))  # repr() ашиглавал Монгол үсэгтэй ч гэсэн алдаа гарахгүй
        return "Уучлаарай, хариу авахад алдаа гарлаа"
os.makedirs("known_faces", exist_ok=True)
os.makedirs("worker_data", exist_ok=True)
os.makedirs("pending_photos", exist_ok=True)
# pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)

# TTS
tts_local = None
try:
    tts_local = pyttsx3.init()
except:
    pass

import threading

def speak(text: str):
    def _speak():
        try:
            if not text.strip():
                return
            safe_text = text.replace("'", "\\'")
            os.system(f"espeak-ng -v ru+f3 -s 100 -p 80 -a 50 '{safe_text}'")
            # Дуу дууссаны дараа буцааж саарал/улаан болгоно
            app.after(5000, lambda: speaker_label.configure(text_color="gray" if check_speaker() else "red"))
        except Exception as e:
            print("Дуу гаргах алдаа:", e)
            app.after(100, lambda: speaker_label.configure(text_color="red"))

    # Дуу эхлэхэд ногоон болгоно (зөвхөн холбогдсон бол)
    if check_speaker():
        speaker_label.configure(text_color="green")
    threading.Thread(target=_speak, daemon=True).start()
        
def beep(times=1, duration=0.08):
    def _beep():
        for _ in range(times):
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
            time.sleep(duration)
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            time.sleep(0.08)
            print("Beep working")
    # This line is the only method that never fails
    if 'app' in globals() and app is not None:
        app.after(0, _beep)
        print("Beep scheduled in GUI thread")
    else:
        # Fallback for before GUI exists
        print("Beep running in main thread")
        _beep()
# TEST BEEP — YOU MUST HEAR 3 BEEPS NOW
print("STARTING — 3 TEST BEEPS IN 1 SECOND!")
app = None  # placeholder — will be set later
print("STARTING — 3 TEST BEEPS NOW!")
beep(3)


# Load faces
def load_known_faces():
    encodings, names = [], []
    for file in os.listdir("known_faces"):
        path = os.path.join("known_faces", file)
        img = face_recognition.load_image_file(path)
        enc = face_recognition.face_encodings(img)
        if enc:
            encodings.append(enc[0])
            names.append(os.path.splitext(file)[0].replace("_", " "))
    return encodings, names

known_face_encodings, known_face_names = load_known_faces()

def log_time(name: str, action: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("time_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"{name},{action},{ts}\n")
    return ts

def process_voice_command(text: str):
    text = text.strip().lower()

    # Light ON
    if any(word in text for word in ["гэрэл ас", "гэрэл асаа", "гэрэл асаагаарай", "light on"]):
        if GPIO.input(LIGHT_PIN) == GPIO.HIGH:   # if it was off
            toggle_gerel()                       # turn it on
        speak("Гэрэл асаалаа")
        info_label.configure(text="Гэрэл: АСЛАА (Голос)")

    # Light OFF
    elif any(word in text for word in ["гэрэл унтар", "гэрэл унтраа", "гэрэл унтраагаарай", "light off"]):
        if GPIO.input(LIGHT_PIN) == GPIO.LOW:    # if it was on
            toggle_gerel()                       # turn it off
        speak("Гэрэл унтраалаа")
        info_label.configure(text="Гэрэл: УНТРАА (ГЭЭ (Голос)")

    # Fan ON
    elif any(word in text for word in ["сэнс ас", "сэнс асаа", "сэнс асаагаарай", "fan on"]):
        if GPIO.input(FAN_PIN) == GPIO.HIGH:     # if it was off
            toggle_sens1()                       # turn it on
        speak("Сэнс асаалаа")
        info_label.configure(text="Сэнс: АСЛАА (Голос)")

    # Fan OFF
    elif any(word in text for word in ["сэнс унтар", "сэнс унтраа", "сэнс унтраагаарай", "fan off"]):
        if GPIO.input(FAN_PIN) == GPIO.LOW:       # if it was on
            toggle_sens1()                       # turn it off
        speak("Сэнс унтраалаа")
        info_label.configure(text="Сэнс: УНТРАА (Голос)")

# =============================================
# GUI
# =============================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
app = ctk.CTk()
app.title("Цаг бүртгэлийн систем")
app.update_idletasks()
app.geometry(f"{app.winfo_screenwidth()}x{app.winfo_screenheight()}+0+0")
app.attributes("-fullscreen", True)
app.attributes("-topmost", True)
app.config(cursor="none")
app.focus_force()

app.bind("<Escape>", lambda e: app.attributes("-fullscreen", False))

bg_image = ctk.CTkImage(
    light_image=PILImage.open("background.jpg"),
    dark_image=PILImage.open("background.jpg"),
    size=(app.winfo_screenwidth(), app.winfo_screenheight())
)

bg_label = ctk.CTkLabel(app, image=bg_image, text="")
bg_label.place(x=0, y=0, relwidth=1, relheight=1)
bg_label.lower()

# Clock
date_label = ctk.CTkLabel(app, text="", font=("Noto Sans CJK JP", 24), text_color="#00DDFF")
date_label.pack(pady=(0))
time_label = ctk.CTkLabel(app, text="", font=("Noto Sans CJK JP", 32, "bold"), text_color="#2288ff")
time_label.pack(pady=(0))

# =============================================
# STATUS INDICATORS (Top Right Corner) - Full Connection + Active Check
# =============================================
status_frame = ctk.CTkFrame(app, fg_color="transparent")
status_frame.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=20)

mic_label = ctk.CTkLabel(status_frame, text="🎙️ ●", font=("Arial", 28), text_color="red")
mic_label.grid(row=0, column=0, padx=15)

speaker_label = ctk.CTkLabel(status_frame, text="🔊 ●", font=("Arial", 28), text_color="red")
speaker_label.grid(row=0, column=1, padx=15)

camera_label = ctk.CTkLabel(status_frame, text="📷 ●", font=("Arial", 28), text_color="red")
camera_label.grid(row=0, column=2, padx=15)

# Hover tooltip
mic_label.bind("<Enter>", lambda e: info_label.configure(text="Микрофон"))
mic_label.bind("<Leave>", lambda e: info_label.configure(text="Үйлдэл сонгоно уу"))
speaker_label.bind("<Enter>", lambda e: info_label.configure(text="Чанга яригч"))
speaker_label.bind("<Leave>", lambda e: info_label.configure(text="Үйлдэл сонгоно уу"))
camera_label.bind("<Enter>", lambda e: info_label.configure(text="Камер"))
camera_label.bind("<Leave>", lambda e: info_label.configure(text="Үйлдэл сонгоно уу"))

# Холболт шалгах функцууд (засвартай – илүү найдвартай)
def check_microphone():
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        return ret
    except:
        return False

def check_speaker():
    try:
        # bluetoothctl devices Connected командыг ашиглаж, холбогдсон төхөөрөмжүүдийг авна
        result = os.popen("bluetoothctl devices Connected").read().strip()
        
        if not result:
            return False  # Ямар ч төхөөрөмж холбогдоогүй
        
        # Холбогдсон төхөөрөмжүүдийн MAC address-уудыг авна
        connected_macs = [line.split()[1] for line in result.splitlines() if line.strip()]
        
        # Тус бүрийн info-г шалгаж, аудио төхөөрөмж эсэхийг харна
        for mac in connected_macs:
            info = os.popen(f"bluetoothctl info {mac}").read()
            if "Connected: yes" in info and ("Icon: audio" in info.lower() or "UUID: Audio" in info):
                return True
        
        return False
    except Exception as e:
        print("Bluetooth спикер шалгалт алдаа:", e)
        return False

def check_camera():
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        return ret
    except:
        return False

# Глобал төлөвүүд
mic_connected = False
speaker_connected = False
camera_connected = False
camera_active = False     # Одоо ашиглаж байгаа эсэх
ai_listening = False         # глобал төлөв
ai_thread = None             # thread хадгалах
ai_transcript = ""           # бүх яригдсан текст

# Индикатор шинэчлэх функц – зөв дуудагдана
def update_status_indicators():
    global mic_connected, speaker_connected, camera_connected, camera_active

    if not camera_active:
        current_connected = check_camera()
        if current_connected != camera_connected:
            camera_connected = current_connected
            color = "red" if not camera_connected else "gray"
            camera_label.configure(text_color=color)

    # Камер идэвхтэй бол яг ногоон хэвээр байлгана
    if camera_active and camera_connected:
        camera_label.configure(text_color="green")

    # Микрофон
    current_mic = check_microphone()
    if current_mic:
        mic_color = "green" if ai_listening else "gray"
    else:
        mic_color = "red"
    mic_label.configure(text_color=mic_color)
    mic_connected = current_mic

    # Чанга яригч
    current_speaker = check_speaker()
    if current_speaker:
        # speak() дотор ногоон болгоно
        speaker_color = "gray"  # default саарал (speak() дотор ногоон болгоно)
    else:
        speaker_color = "red"
    speaker_label.configure(text_color=speaker_color)
    speaker_connected = current_speaker


    # 3 секунд тутам дахин шалгана
    app.after(3000, update_status_indicators)

# Апп эхлэхэд шалгалт эхэлнэ
update_status_indicators()


def update_clock():
    now = datetime.datetime.now()
    date_label.configure(text=now.strftime("%A, %B %d, %Y"))
    time_label.configure(text=now.strftime("%H:%M:%S"))
    app.after(1000, update_clock)
update_clock()

info_label = ctk.CTkLabel(app, text="Үйлдэл сонгоно уу", font=("Noto Sans CJK JP", 24), text_color="#CCFFCC")
info_label.pack(pady=0)

# Temperature label
temp_label = ctk.CTkLabel(app, text="Температур: --°C", font=("Noto Sans CJK JP", 20), text_color="#FFAA00")
temp_label.pack(pady=0)

# =============================================
# DHT11 + Auto Fan + Auto Light
# =============================================
def read_temp():
    for _ in range(10):
        try:
            temp = dht_device.temperature
            hum = dht_device.humidity
            if temp is not None:
                return temp, hum
        except:
            time.sleep(0.5)
    return None, None

def update_temp_and_control():
    global manual_fan, light_auto_on
    temp, hum = read_temp()
    if temp is not None:
        
        
        temp_label.configure(text=f"Температур: {temp:.1f}°C | Чийгшил: {hum:.1f}%")

        # Auto Fan (only if not manually not overridden)
        if not manual_fan:
            if temp > TEMP_THRESHOLD and GPIO.input(FAN_PIN) == GPIO.HIGH:
                GPIO.output(FAN_PIN, GPIO.LOW)
                beep(2)   # ← ADD THIS
                sens1_btn.configure(text="Сэнс: АСЛАА (Авто)")
            elif temp <= TEMP_THRESHOLD and GPIO.input(FAN_PIN) == GPIO.LOW:
                GPIO.output(FAN_PIN, GPIO.HIGH)
                beep(1)   # ← ADD THIS
                sens1_btn.configure(text="Сэнс: УНТРАА (Авто)")

        # Auto Light - first person in = ON, last person out = OFF
        if active_workers and not light_auto_on:
            GPIO.output(LIGHT_PIN, GPIO.LOW)
            beep(1)   # ← short beep when person enters
            gerel_btn.configure(text="Гэрэл: АСЛАА (Авто)")
            light_auto_on = True
        elif not active_workers and light_auto_on:
            GPIO.output(LIGHT_PIN, GPIO.HIGH)
            beep(2)   # ← short beep when person enters
            gerel_btn.configure(text="Гэрэл: УНТРАА (Авто)")
            light_auto_on = False

    app.after(5000, update_temp_and_control)
    
    



# =============================================
# Buttons
# =============================================
# def toggle_sens1():
#     beep(2)          # 2 beeps when turning ON, 1 when OFF
    
#     global manual_fan
#     manual_fan = True
#     current = GPIO.input(FAN_PIN)
#     GPIO.output(FAN_PIN, not current)
#     # ←←← ADD THESE TWO LINES ↓↓↓
#     # ←←←
#     state = "АСЛАА" if not current else "УНТРАА"
#     sens1_btn.configure(text=f"Сэнс: {state} (Гараар)")
#     speak("Сэнс " + ("асаалаа" if not current else "унтраалаа"))

# def toggle_gerel():
#     beep(2)          # 1 beep when turning ON, 2 when OFF
    
#     current = GPIO.input(LIGHT_PIN)
#     GPIO.output(LIGHT_PIN, not current)
#     # ←←← ADD THESE TWO LINES ↓↓↓
#     # ←←←
#     state = "АСЛАА" if not current else "УНТРАА"
#     gerel_btn.configure(text=f"Гэрэл: {state} (Гараар)")
#     speak("Гэрэл " + ("асаалаа" if not current else "унтраалаа"))
    
def toggle_sens1():
    print("Fan toggle pressed")
    global manual_fan
    manual_fan = True
    was_on = GPIO.input(FAN_PIN) == GPIO.LOW
    GPIO.output(FAN_PIN, not GPIO.input(FAN_PIN))
    beep(2 if not was_on else 1)
    state = "АСЛАА" if not was_on else "УНТРАА"
    sens1_btn.configure(text=f"Сэнс: {state} (Гараар)")
    speak("Сэнс " + ("асаалаа" if not was_on else "унтраалаа"))

def toggle_gerel():
    print("Light toggle pressed")
    was_on = GPIO.input(LIGHT_PIN) == GPIO.LOW
    GPIO.output(LIGHT_PIN, not GPIO.input(LIGHT_PIN))
    beep(1 if not was_on else 2)
    state = "АСЛАА" if not was_on else "УНТРАА"
    gerel_btn.configure(text=f"Гэрэл: {state} (Гараар)")
    speak("Гэрэл " + ("асаалаа" if not was_on else "унтраалаа"))
# -------------------------------------------------
# 1. Add New Worker – AUTO FACE DETECT + CAPTURE
# -------------------------------------------------
pending_photo_path = None

def add_worker():
    global pending_photo_path
    global camera_active
    camera_active = True
    if camera_connected:
        camera_label.configure(text_color="green")
    info_label.configure(text="Камерлуу хараарай...")
    app.update()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        info_label.configure(text="Камер олдсонгүй!")
        return

    preview = ctk.CTkToplevel(app)
    preview.title("Шинэ ажилтан нэмэх")
    preview.attributes("-fullscreen", True)
    preview.configure(bg="black")
    preview.focus_force()
    preview.config(cursor="none")
    preview.bind("<Escape>", lambda e: preview.destroy())
    camera_active = False
    color = "gray" if camera_connected else "red"
    camera_label.configure(text_color=color)
    cam_label = ctk.CTkLabel(preview, text="")
    cam_label.pack()
    cam_label.pack(expand=True, fill="both")     # ← make video fill the whole screen

    captured = [None]
    captured_time = [0]

    def show():
        current_time = time.time()
        if captured[0] is not None:
            frame = captured[0].copy()  # Static photo
            # Redraw box on static
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb)
            for (top, right, bottom, left) in locations:
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, "Unknown", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        else:
            ret, frame = cap.read()
            if not ret:
                preview.after(30, show)
                return
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb)
            # Draw box
            for (top, right, bottom, left) in locations:
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, "Unknown", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            # Auto-capture if face detected and timeout passed
            if locations and current_time - captured_time[0] > 1:  # 1 sec debounce
                captured[0] = frame.copy()
                captured_time[0] = current_time
                info_label.configure(text="Царай танигдлаа! Дахин таниулах эсвэл Хадгалах?")
                speak("Зураг авлаа")

        img = ctk.CTkImage(light_image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                           dark_image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                           size=(640, 360))
        cam_label.configure(image=img)
        cam_label.image = img
        preview.after(30, show)

    show()

    btns = ctk.CTkFrame(preview)
    btns.pack(pady=8)
    ctk.CTkButton(btns, text="Дахин таниулах", command=lambda: reset_capture(captured, captured_time)).grid(row=0, column=0, padx=8)
    ctk.CTkButton(btns, text="Хадгалах", command=lambda: save_photo_and_form(captured[0], cap, preview)).grid(row=0, column=1, padx=8)

    def reset_capture(captured, captured_time):
        captured[0] = None
        captured_time[0] = 0
        info_label.configure(text="Камерлуу ахиад хараарай...")

    def save_photo_and_form(photo_frame, cap, preview_win):
        global pending_photo_path
        camera_label.configure(text_color="gray")
        cap.release()
        preview_win.destroy()

        if photo_frame is None:
            info_label.configure(text="Царай танихад алдаа гарлаа! Дахиад оролдоно уу.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pending_photo_path = f"pending_photos/photo_{timestamp}.jpg"
        cv2.imwrite(pending_photo_path, photo_frame)
        info_label.configure(text="Зураг хадгалагдлаа! Ажилтны мэдээлэлийг оруулна уу.")
        open_registration_form()

# -------------------------------------------------
# Registration Form
# -------------------------------------------------
# -------------------------------------------------
# Registration Form – FULLSCREEN + WORKING KEYBOARD
# -------------------------------------------------
# -------------------------------------------------
# ТӨГС БҮРТГЭЛИЙН ФОРМ – БҮРЭН ДЭЛГЭЦ, СКРОЛЛТОЙ, АЖИЛЛАДАГ ГАР
# -------------------------------------------------
# -------------------------------------------------
# ЭЦСИЙН ТӨГС БҮРТГЭЛИЙН ФОРМ – ЗӨВХӨН 1 ТОВЧ, ӨӨРИЙН ГАР
# -------------------------------------------------
# -------------------------------------------------
# ТӨГС БҮРТГЭЛИЙН ФОРМ – FLORENCE ГАР (тоо, үсэг, монгол, доод талдаа, алга болохгүй)
# -------------------------------------------------
# -------------------------------------------------
# ТӨГС БҮРТГЭЛИЙН ФОРМ – СИСТЕМИЙН ӨӨРИЙН ГАР (Chrome шиг)
# -------------------------------------------------
# -------------------------------------------------
# ТӨГС CUSTOM KEYBOARD + БҮРТГЭЛИЙН ФОРМ (2025 онд 100% ажиллана)
# -------------------------------------------------
current_entry = None

def show_custom_keyboard(entry_widget):
    global current_entry
    current_entry = entry_widget

    for widget in app.winfo_children():
        if isinstance(widget, ctk.CTkToplevel) and widget.title() == "Мундаг хосоогийн кэеборд":
            widget.destroy()

    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()

    kb_height = int(screen_h * 0.35)   # smaller keyboard
    kb_y = screen_h - kb_height        # fix to bottom

    kb = ctk.CTkToplevel(app)
    kb.title("Khosbayar's keyboard")
    kb.geometry(f"{screen_w}x{kb_height}+0+{kb_y}")
    kb.configure(fg_color="#1e1e2e")
    kb.resizable(False, False)

    keys = [
        ['1','2','3','4','5','6','7','8','9','0'],
        ['q','w','e','r','t','y','u','i','o','p'],
        ['a','s','d','f','g','h','j','k','l'],
        ['z','x','c','v','b','n','m',',','.'],
        ['Backspace','Space','Clear','Close']
    ]

    def press(k):
        if current_entry is None:
            return
        if k == "Backspace":
            current_entry.delete(0, 'end')
            current_entry.insert(0, current_entry.get()[:-1])
        elif k == "Space":
            current_entry.insert("end", " ")
        elif k == "Clear":
            current_entry.delete(0, "end")
        elif k == "Close":
            kb.destroy()
        else:
            current_entry.insert("end", k)

    for row in keys:
        row_frame = ctk.CTkFrame(kb, fg_color="#1e1e2e")
        row_frame.pack(pady=1)

        for key in row:
            if key == "Space":
                btn = ctk.CTkButton(row_frame, text="", width=350, height=45,
                                    fg_color="#444444", command=lambda: press(" "))
            elif key in ["Backspace", "Clear", "Close"]:
                color = "#cc0000" if key in ["Clear", "Close"] else "#0066ff"
                btn = ctk.CTkButton(row_frame, text=key, width=130, height=45,
                                    font=("Arial", 20, "bold"), fg_color=color,
                                    command=lambda k=key: press(k))
            else:
                btn = ctk.CTkButton(row_frame, text=key.upper(), width=60, height=45,
                                    font=("Arial", 24, "bold"), fg_color="#333333",
                                    command=lambda k=key: press(k))
            btn.pack(side="left", padx=3)
            
def open_registration_form():
    global pending_photo_path
    if not pending_photo_path or not os.path.exists(pending_photo_path):
        info_label.configure(text="Зураг олдсонгүй!")
        return

    form = ctk.CTkToplevel(app)
    form.title("")
    form.geometry(f"{app.winfo_screenwidth()}x{app.winfo_screenheight()}+0+0")
    form.configure(fg_color="#0d1117")
    form.resizable(False, False)

    # Centered main container – no left/right split anymore
    main_container = ctk.CTkFrame(form, fg_color="#0d1117")
    main_container.pack(fill="both", expand=True)

    # Title
    ctk.CTkLabel(main_container, text="ШИНЭ АЖИЛТАН БҮРТГЭХ",
                 font=("Noto Sans CJK JP", 32, "bold"),
                 text_color="#00ffaa").pack(pady=10)

    # Compact 2×2 grid centered
    grid = ctk.CTkFrame(main_container, fg_color="transparent")
    grid.pack(pady=5)

    entries = {}
    fields = ["Full Name", "Employee ID", "Department", "Position"]

    for i, field in enumerate(fields):
        row = i // 2
        col = i % 2

        ctk.CTkLabel(grid, text=field + ":",
                     font=("Noto Sans CJK JP", 20),
                     text_color="white").grid(
            row=row*2, column=col, padx=40, pady=(5, 0), sticky="w"
        )

        entry = ctk.CTkEntry(grid, width=350, height=55,
                             font=("Noto Sans CJK JP", 22),
                             fg_color="white", text_color="black",
                             corner_radius=10, border_width=2)
        entry.grid(row=row*2+1, column=col,
                   padx=40, pady=(0, 10), sticky="w")
        entry.bind("<Button-1>", lambda e, w=entry: show_custom_keyboard(w))

        entries[field] = entry

    # Save button centered
    def save():
        name = entries["Full Name"].get().strip()
        if not name:
            speak("Нэрээ бичнэ үү")
            return
        safe = name.replace(" ", "_")
        shutil.move(pending_photo_path, f"known_faces/{safe}.jpg")
        with open(f"worker_data/{safe}.txt", "w", encoding="utf-8") as f:
            for k, v in entries.items():
                f.write(f"{k}: {v.get().strip()}\n")

        global known_face_encodings, known_face_names
        known_face_encodings, known_face_names = load_known_faces()

        speak(f"{name} бүртгэгдлээ")
        info_label.configure(text=f"{name} ✓")
        form.destroy()

    ctk.CTkButton(main_container, text="БҮРТГЭХ", command=save,
                  width=400, height=70,
                  font=("Noto Sans CJK JP", 28, "bold"),
                  fg_color="#00aa33", hover_color="#008822").pack(pady=20)

    form.protocol("WM_DELETE_WINDOW", form.destroy)

# -------------------------------------------------
# 2. Show All Logs
# -------------------------------------------------
def show_all_logs():
    log_win = ctk.CTkToplevel(app)
    log_win.title("Ирцийн бүртгэл")
    log_win.geometry("780x580")
    txt = ctk.CTkTextbox(log_win, font=("Courier", 14))
    txt.pack(fill="both", expand=True, padx=12, pady=12)
    if os.path.exists("time_logs.txt"):
        with open("time_logs.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
        header = f"{'Name':<20} {'Action':<8} {'Timestamp':<20}\n"
        header += "-"*52 + "\n"
        txt.insert("end", header)
        for line in lines:
            parts = line.strip().split(",", 2)
            if len(parts) == 3:
                name, action, ts = parts
                txt.insert("end", f"{name:<20} {action:<8} {ts:<20}\n")
    else:
        txt.insert("end", "Бүртгэл хоосон байна.\n")

# -------------------------------------------------
# 3. Recognize Face – SHOW USERNAME + RETAKE/SAVE
# -------------------------------------------------
active_workers = {}

def recognize_once():
    global active_workers
    global camera_active
    camera_active = True
    if camera_connected:
        camera_label.configure(text_color="green")
    info_label.configure(text="Камерлуу хараарай...")
    app.update()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        info_label.configure(text="Камер олдсонгүй!")
        return

    preview = ctk.CTkToplevel(app)
    preview.title("Царай таних")
    preview.attributes("-fullscreen", True)        # FULLSCREEN
    preview.configure(bg="black")
    preview.focus_force()
    # Hide mouse cursor in camera mode (optional but nice)
    preview.config(cursor="none")

    # Optional: press Escape to close camera
    preview.bind("<Escape>", lambda e: preview.destroy())
    cam_label = ctk.CTkLabel(preview, text="")
    cam_label.pack()

    captured = [None]
    detected_name = [None]
    captured_time = [0]

    def show():
        current_time = time.time()
        if captured[0] is not None:
            frame = captured[0].copy()  # Static photo
            # Redraw box + name on static
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb)
            for (top, right, bottom, left) in locations:
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, detected_name[0] or "Unknown", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        else:
            ret, frame = cap.read()
            if not ret:
                preview.after(30, show)
                return
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb)
            encodings = face_recognition.face_encodings(rgb, locations)

            name = "Unknown"
            if encodings:
                matches = face_recognition.compare_faces(known_face_encodings, encodings[0], tolerance=0.55)
                if True in matches:
                    idx = matches.index(True)
                    name = known_face_names[idx]
                detected_name[0] = name

            # Draw box + name
            for (top, right, bottom, left) in locations:
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(frame, name, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            # Auto-capture if face detected and timeout passed
            if locations and current_time - captured_time[0] > 1:  # 1 sec debounce
                captured[0] = frame.copy()
                captured_time[0] = current_time
                info_label.configure(text=f"{name} танигдлаа! Бүртгэх эсвэл дахин авах?")
                speak("Зураг авлаа")

        img = ctk.CTkImage(light_image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                           dark_image=Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                           size=(640, 360))
        cam_label.configure(image=img)
        cam_label.image = img
        preview.after(30, show)

    show()

    btns = ctk.CTkFrame(preview)
    btns.pack(pady=8)
    ctk.CTkButton(btns, text="Дахин авах", command=lambda: reset_recognition(captured, captured_time)).grid(row=0, column=0, padx=8)
    ctk.CTkButton(btns, text="Бүртгэх", command=lambda: save_and_log(captured[0], detected_name[0], cap, preview)).grid(row=0, column=1, padx=8)

    def reset_recognition(captured, captured_time):
        captured[0] = None
        captured_time[0] = 0
        info_label.configure(text="Камерлуу хараарай...")

    def save_and_log(photo_frame, name, cap, preview_win):
        global active_workers
        cap.release()
        preview_win.destroy()

        if photo_frame is None:
            info_label.configure(text="Царай танигдсангүй! Дахин оролдох.")
            return

        if name == "Unknown":
            speak("Танихгүй хүн")
            info_label.configure(text="Unknown face")
            return

        if name not in active_workers:
            ts = log_time(name, "IN")
            active_workers[name] = ts
            beep(1)                                # ← 1 beep = welcome
            speak(f"{name} ирлээ")
            info_label.configure(text=f"{name} – IN at {ts.split()[1]}")
        else:
            active_workers.pop(name)
            out_ts = log_time(name, "OUT")
            beep(2)                                # ← 2 beeps = goodbye
            speak(f"{name} явлаа")
            info_label.configure(text=f"{name} – OUT at {out_ts.split()[1]}")
        global camera_active
        camera_active = False
        color = "gray" if camera_connected else "red"
        camera_label.configure(text_color=color)
        app.after(2000, lambda: info_label.configure(text="Үйлдэл сонгоно уу"))

# -------------------------------------------------
# 4. Sens1 & Gerel Toggle Buttons
# -------------------------------------------------
sens1_state = False
gerel_state = False

# ---------- Fan ----------
# ---------- Fan (Сэнс) ----------
# def toggle_sens1():
#     global manual_fan  # This disables auto control when pressed
#     manual_fan = True
    
#     current = GPIO.input(FAN_PIN)
#     GPIO.output(FAN_PIN, not current)
    
#     state = "АСЛАА" if not current else "УНТРАА"
#     sens1_btn.configure(text=f"Сэнс: {state} (Гараар)")
#     speak("Сэнс нэг " + ("асаалаа" if not current else "унтраалаа"))

# # ---------- Light (Гэрэл) ----------
# def toggle_gerel():
#     current = GPIO.input(LIGHT_PIN)
#     GPIO.output(LIGHT_PIN, not current)
#     state = "АСЛАА" if not current else "УНТРАА"
#     gerel_btn.configure(text=f"Гэрэл: {state} (Гараар)")
#     speak("Гэрэл " + ("асаалаа" if not current else "унтраалаа"))
# -------------------------------------------------
# Gemini Assistant Button Functionality
# -------------------------------------------------
# ==================== AI ТОВЧ – ТАСРАЛТГҮЙ СОНСООД ДАРАА НЬ ИЛГЭЭХ ====================


def toggle_ai():
    global ai_listening, ai_thread, ai_transcript

    if not ai_listening:                               # —— ЭХЛҮҮЛЭХ ——
        ai_listening = True
        ai_transcript = ""
        ai_btn.configure(text="AI ЗОГС", fg_color="#FF3333", hover_color="#CC0000")
        info_label.configure(text="Сонсож байна... ярьж эхэлнэ үү")
        speak("Сонсож байна")

        # Тусдаа thread дээр тасралтгүй сонсоно
        ai_thread = threading.Thread(target=continuous_listen, daemon=True)
        ai_thread.start()

    else: # —— ЗОГСООХ + ИЛГЭЭХ ——
        ai_listening = False
        ai_btn.configure(text="AI ажиллуулах", fg_color="#AA00FF", hover_color="#8800CC")
        # Энд юу ч бичих шаардлагагүй – continuous_listen дотор бүгд зохицуулагдана

def continuous_listen():
    """Товч дарах хүртэл тасралтгүй сонсоод текстийг нэгтгэнэ"""
    global ai_transcript
    r = sr.Recognizer()
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True

    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=1.0)
        print("[AI] Сонсоож эхэллээ...")

        ai_transcript = ""

        while ai_listening:
            try:
                audio = r.listen(source, timeout=1.0, phrase_time_limit=15)
                text = r.recognize_google(audio, language="mn-MN")
                ai_transcript += text + " "

                # Бодит цагт хэрэглэгчийн ярьж байгаа текстийг info_label дээр харуулна
                app.after(0, lambda t=ai_transcript.strip(): info_label.configure(
                    text=f"Таны хэлсэн: {t[-80:]}" if len(t) > 80 else f"Таны хэлсэн: {t}"
                ))

            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except Exception as e:
                print("Сонсох алдаа:", e)
                continue

    # —— Яриа дууслаа (товч дарагдлаа) ——
    if ai_transcript.strip():
        user_text = ai_transcript.strip()

        # Эцсийн хэрэглэгчийн текстийг харуулах
        app.after(0, lambda: info_label.configure(
            text=f"Таны хэлсэн: {user_text[-90:]}" if len(user_text) > 90 else f"Таны хэлсэн: {user_text}"
        ))

        # Гэрэл/Сэнс команд шалгах
        if any(keyword in user_text.lower() for keyword in ["гэрэл", "сэнс", "light", "fan"]):
            process_voice_command(user_text)
            app.after(3000, lambda: info_label.configure(text="Үйлдэл сонгоно уу"))
            return

        # Gemini рүү илгээх
        app.after(0, lambda: info_label.configure(text="GROK бодож байна..."))

        response = ask_google_ai(user_text)

        # 2 секундын дараа Gemini хариуг харуулаад уншина
        def show_response():
            if response and len(response) > 0 and "хэтэрлээ" not in response and "алдаа" not in response.lower():
                display_text = response[:100] + "..." if len(response) > 100 else response
                info_label.configure(text=f"Хариу: {display_text}")
                speak(response)  # Одоо background-д ажиллана → label шууд солигдоно
            else:
                display_text = response[:100] + "..." if response and len(response) > 100 else (response or "Хариу ирсэнгүй")
                info_label.configure(text=f"Анхааруулга: {display_text}")
                speak(response or "Уучлаарай, алдаа гарлаа")

            # Дуу дуусахыг хүлээхгүй – 8 секунд хүлээгээд буцаана (дууны урттай тааруул)
            app.after(8000, lambda: info_label.configure(text="Үйлдэл сонгоно уу"))
            
            
        app.after(2000, show_response)  # Яг 2 секундын дараа

    else:
        app.after(0, lambda: info_label.configure(text="Юу ч сонссонгүй"))
        speak("Юу ч сонссонгүй")
        app.after(3000, lambda: info_label.configure(text="Үйлдэл сонгоно уу"))
        
        
# -------------------------------------------------
# Buttons Layout
# -------------------------------------------------
# Эндээс доош бүх товчнуудыг том болгоно
# =============================================
# Your existing code continues below (unchanged)
# =============================================
# ... [all your add_worker, registration, recognize_once, etc. functions here] ...

# Buttons at the bottom
# -------------------------------------------------
# Buttons Layout
# -------------------------------------------------
btn_frame = ctk.CTkFrame(app)
btn_frame.pack(pady=40)

BIG_BUTTON = {
    "width": 380,
    "height": 80,
    "font": ("Noto Sans CJK JP", 24, "bold"),
    "corner_radius": 20
}

ctk.CTkButton(btn_frame, text="Ажилтан нэмэх", command=add_worker, **BIG_BUTTON, fg_color="#00AA33").grid(row=0, column=0, padx=30, pady=15)
ctk.CTkButton(btn_frame, text="Ирцийн бүртгэл", command=show_all_logs, **BIG_BUTTON, fg_color="#FF8800").grid(row=0, column=1, padx=30, pady=15)
ctk.CTkButton(btn_frame, text="Нүүр таних", command=recognize_once, **BIG_BUTTON, fg_color="#0066FF").grid(row=1, column=0, padx=30, pady=15)

# These buttons must exist BEFORE update_temp_and_control() is called!
sens1_btn = ctk.CTkButton(btn_frame, text="Сэнс: УНТРАА", command=toggle_sens1, **BIG_BUTTON, fg_color="#888888")
sens1_btn.grid(row=1, column=1, padx=30, pady=15)

gerel_btn = ctk.CTkButton(btn_frame, text="Гэрэл: УНТРАА", command=toggle_gerel, **BIG_BUTTON, fg_color="#888888")
gerel_btn.grid(row=2, column=0, padx=30, pady=15)

ai_btn = ctk.CTkButton(btn_frame, text="AI ажиллуулах", command=toggle_ai, **BIG_BUTTON, fg_color="#AA00FF")
ai_btn.grid(row=2, column=1, padx=30, pady=15)

# NOW IT'S SAFE — buttons exist!
update_temp_and_control()

app.mainloop()

# Cleanup on exit
GPIO.cleanup()