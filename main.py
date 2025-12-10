import customtkinter as ctk
import cv2
import face_recognition
import numpy as np
import os
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

# -------------------------------------------------
# Load .env file for API key
# -------------------------------------------------
API_KEY = ""
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# -------------------------------------------------
# Gemini API function
# -------------------------------------------------
def ask_google_ai(prompt):
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": API_KEY
    }
    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    try:
        response = requests.post(API_URL, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        candidates = result.get("candidates", [])
        if not candidates:
            return f"No candidates in response: {result}"
        # New API: content is a dict with 'parts' list
        content_dict = candidates[0].get("content", {})
        parts = content_dict.get("parts", [])
        if not parts:
            return f"No parts in content: {content_dict}"
        # Join all text parts
        answer = "".join([p.get("text", "") for p in parts])
        return answer
    except requests.exceptions.RequestException as e:
        return f"HTTP error: {e}"
    except ValueError:
        return f"Failed to parse JSON: {response.text}"
    except Exception as e:
        return f"Unexpected error: {e}"

# -------------------------------------------------
# Folders
# -------------------------------------------------
os.makedirs("known_faces", exist_ok=True)
os.makedirs("worker_data", exist_ok=True)
os.makedirs("pending_photos", exist_ok=True)

# -------------------------------------------------
# pygame init
# -------------------------------------------------
pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)

# -------------------------------------------------
# TTS
# -------------------------------------------------
tts_local = None
try:
    tts_local = pyttsx3.init()
except:
    tts_local = None

def speak(text: str, lang: str = "mn"):
    def _play_gtts():
        try:
            t = gTTS(text=text, lang=lang, slow=False)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            t.save(tmp.name)
            pygame.mixer.music.load(tmp.name)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            os.unlink(tmp.name)
        except Exception:
            _play_espeak()

    def _play_espeak():
        if tts_local:
            def _run():
                try:
                    tts_local.say(text)
                    tts_local.runAndWait()
                except:
                    pass
            threading.Thread(target=_run, daemon=True).start()
        else:
            print(f"[VOICE] {text}")

    threading.Thread(target=_play_gtts, daemon=True).start()

# -------------------------------------------------
# Load known faces
# -------------------------------------------------
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

# -------------------------------------------------
# Helper: log time
# -------------------------------------------------
def log_time(name: str, action: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("time_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"{name},{action},{ts}\n")
    return ts

# -------------------------------------------------
# GUI – main window
# -------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
app = ctk.CTk()
app.title("Time Management System")
app.geometry("560x460")

# Clock
date_label = ctk.CTkLabel(app, text="", font=("Arial", 20, "bold"))
date_label.pack(pady=(15, 0))
time_label = ctk.CTkLabel(app, text="", font=("Arial", 42, "bold"))
time_label.pack(pady=(0, 10))

def update_clock():
    now = datetime.datetime.now()
    date_label.configure(text=now.strftime("%A, %B %d, %Y"))
    time_label.configure(text=now.strftime("%H:%M:%S"))
    app.after(1000, update_clock)
update_clock()

info_label = ctk.CTkLabel(app, text="Select an action below", font=("Arial", 16))
info_label.pack(pady=10)

# -------------------------------------------------
# 1. Add New Worker – AUTO FACE DETECT + CAPTURE
# -------------------------------------------------
pending_photo_path = None

def add_worker():
    global pending_photo_path
    info_label.configure(text="Look at camera to capture face...")
    app.update()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        info_label.configure(text="Camera not found!")
        return

    preview = ctk.CTkToplevel(app)
    preview.title("Add New Worker")
    preview.geometry("680x520")
    cam_label = ctk.CTkLabel(preview, text="")
    cam_label.pack()

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
                info_label.configure(text="Face captured! Retake or Save?")
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
    ctk.CTkButton(btns, text="Retake", command=lambda: reset_capture(captured, captured_time)).grid(row=0, column=0, padx=8)
    ctk.CTkButton(btns, text="Save Photo", command=lambda: save_photo_and_form(captured[0], cap, preview)).grid(row=0, column=1, padx=8)

    def reset_capture(captured, captured_time):
        captured[0] = None
        captured_time[0] = 0
        info_label.configure(text="Look at camera again...")

    def save_photo_and_form(photo_frame, cap, preview_win):
        global pending_photo_path
        cap.release()
        preview_win.destroy()

        if photo_frame is None:
            info_label.configure(text="No photo captured! Try again.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        pending_photo_path = f"pending_photos/photo_{timestamp}.jpg"
        cv2.imwrite(pending_photo_path, photo_frame)
        info_label.configure(text="Photo saved! Fill the form.")
        open_registration_form()

# -------------------------------------------------
# Registration Form
# -------------------------------------------------
def open_registration_form():
    global pending_photo_path
    if not pending_photo_path or not os.path.exists(pending_photo_path):
        info_label.configure(text="No photo found!")
        return

    form = ctk.CTkToplevel(app)
    form.title("Worker Registration")
    form.geometry("360x420")
    ctk.CTkLabel(form, text="Worker Information", font=("Arial", 18, "bold")).pack(pady=12)

    fields = ["Full Name", "Employee ID", "Department", "Position"]
    entries = {}
    for f in fields:
        ctk.CTkLabel(form, text=f).pack()
        e = ctk.CTkEntry(form, width=260)
        e.pack(pady=4)
        entries[f] = e

    def save():
        global pending_photo_path
        name = entries["Full Name"].get().strip()
        if not name:
            info_label.configure(text="Name required!")
            return
        name_key = name.replace(" ", "_")
        final_path = f"known_faces/{name_key}.jpg"

        try:
            shutil.move(pending_photo_path, final_path)
        except Exception as e:
            info_label.configure(text=f"Save failed: {e}")
            return

        info = {k: v.get().strip() for k, v in entries.items()}
        txt_path = os.path.join("worker_data", f"{name_key}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            for k, v in info.items():
                f.write(f"{k}: {v}\n")

        global known_face_encodings, known_face_names
        known_face_encodings, known_face_names = load_known_faces()
        speak(f"{name} бүртгэгдлээ")
        info_label.configure(text=f"{name} registered!")
        form.destroy()
        pending_photo_path = None

    def on_close():
        global pending_photo_path
        if pending_photo_path and os.path.exists(pending_photo_path):
            os.remove(pending_photo_path)
        pending_photo_path = None
        form.destroy()

    form.protocol("WM_DELETE_WINDOW", on_close)
    ctk.CTkButton(form, text="Register", command=save).pack(pady=15)

# -------------------------------------------------
# 2. Show All Logs
# -------------------------------------------------
def show_all_logs():
    log_win = ctk.CTkToplevel(app)
    log_win.title("Time Logs")
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
        txt.insert("end", "No logs yet.\n")

# -------------------------------------------------
# 3. Recognize Face – SHOW USERNAME + RETAKE/SAVE
# -------------------------------------------------
active_workers = {}

def recognize_once():
    global active_workers
    info_label.configure(text="Look at camera...")
    app.update()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        info_label.configure(text="Camera error!")
        return

    preview = ctk.CTkToplevel(app)
    preview.title("Recognize Face")
    preview.geometry("680x520")
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
                info_label.configure(text=f"{name} detected! Save or Retake?")
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
    ctk.CTkButton(btns, text="Retake", command=lambda: reset_recognition(captured, captured_time)).grid(row=0, column=0, padx=8)
    ctk.CTkButton(btns, text="Save & Log", command=lambda: save_and_log(captured[0], detected_name[0], cap, preview)).grid(row=0, column=1, padx=8)

    def reset_recognition(captured, captured_time):
        captured[0] = None
        captured_time[0] = 0
        info_label.configure(text="Look at camera again...")

    def save_and_log(photo_frame, name, cap, preview_win):
        global active_workers
        cap.release()
        preview_win.destroy()

        if photo_frame is None:
            info_label.configure(text="No photo captured! Try again.")
            return

        if name == "Unknown":
            speak("Танихгүй хүн")
            info_label.configure(text="Unknown face")
            return

        if name not in active_workers:
            ts = log_time(name, "IN")
            active_workers[name] = ts
            speak(f"{name} ирлээ")
            info_label.configure(text=f"{name} – IN at {ts.split()[1]}")
        else:
            in_ts = active_workers.pop(name)
            out_ts = log_time(name, "OUT")
            speak(f"{name} явлаа")
            info_label.configure(text=f"{name} – OUT at {out_ts.split()[1]}")

        app.after(2000, lambda: info_label.configure(text="Select an action below"))

# -------------------------------------------------
# 4. Sens1 & Gerel Toggle Buttons
# -------------------------------------------------
sens1_state = False
gerel_state = False

def toggle_sens1():
    global sens1_state
    sens1_state = not sens1_state
    state = "ON" if sens1_state else "OFF"
    sens1_btn.configure(text=f"Sens1: {state}")
    speak(f"Сенс1 {state.lower()}")

def toggle_gerel():
    global gerel_state
    gerel_state = not gerel_state
    state = "ON" if gerel_state else "OFF"
    gerel_btn.configure(text=f"Gerel: {state}")
    speak(f"Гэрэл {state.lower()}")

# -------------------------------------------------
# Gemini Assistant Button Functionality
# -------------------------------------------------
def gemini_assistant():
    info_label.configure(text="Сонсож байна... 6 секунд ярь!")
    speak("Ярь")

    r = sr.Recognizer()
    r.energy_threshold = 300          # Микрофоны мэдрэмжийг бууруулах
    r.dynamic_energy_threshold = True

    with sr.Microphone() as source:
        print("Микрофон идэвхжлээ, ярьж эхэл...")
        r.adjust_for_ambient_noise(source, duration=0.8)  # Орчны дууг тохируулах
        try:
            audio = r.listen(source, timeout=8, phrase_time_limit=10)
            info_label.configure(text="Google руу илгээж байна...")
            text = r.recognize_google(audio, language="mn-MN")
            print(f"Хэрэглэгч: {text}")
            info_label.configure(text=f"Та: {text}")

            response = ask_google_ai(text)
            print(f"Gemini: {response}")
            speak(response if response else "Хариу ирсэнгүй")
            info_label.configure(text="Хариу дуугарлаа!")

        except sr.WaitTimeoutError:
            info_label.configure(text="Яриагүй эсвэл дууг сонссонгүй")
            speak("Яриагүй байна")
        except sr.UnknownValueError:
            info_label.configure(text="Дууг ойлгосонгүй")
            speak("Ойлгосонгүй")
        except Exception as e:
            info_label.configure(text="Алдаа гарлаа")
            print("Gemini алдаа:", e)

    app.after(4000, lambda: info_label.configure(text="Select an action below"))
# -------------------------------------------------
# Buttons Layout
# -------------------------------------------------
btn_frame = ctk.CTkFrame(app)
btn_frame.pack(pady=12)

ctk.CTkButton(btn_frame, text="Add New Worker", width=180, command=add_worker).grid(row=0, column=0, padx=8, pady=4)
ctk.CTkButton(btn_frame, text="Show All Logs", width=180, command=show_all_logs).grid(row=0, column=1, padx=8, pady=4)

ctk.CTkButton(btn_frame, text="Recognize Face", width=180, command=recognize_once).grid(row=1, column=0, padx=8, pady=4)
sens1_btn = ctk.CTkButton(btn_frame, text="Sens1: OFF", width=180, command=toggle_sens1)
sens1_btn.grid(row=1, column=1, padx=8, pady=4)

gerel_btn = ctk.CTkButton(btn_frame, text="Gerel: OFF", width=180, command=toggle_gerel)
gerel_btn.grid(row=2, column=0, padx=8, pady=4)

ctk.CTkButton(btn_frame, text="Gemini Assistant", width=180, command=gemini_assistant).grid(row=2, column=1, padx=8, pady=4)

# -------------------------------------------------
app.mainloop()