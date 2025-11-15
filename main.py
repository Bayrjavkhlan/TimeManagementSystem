import customtkinter as ctk
import cv2
import face_recognition
import numpy as np
import os
import time
import datetime
from PIL import Image, ImageTk
import threading
import pyttsx3   # <-- text-to-speech

# -------------------------------------------------
# Folders
# -------------------------------------------------
os.makedirs("known_faces", exist_ok=True)
os.makedirs("worker_data", exist_ok=True)

# -------------------------------------------------
# Voice engine (Mongolian works if the voice is installed)
# -------------------------------------------------
tts = pyttsx3.init()
# Try to set Mongolian voice – fallback to default
voices = tts.getProperty('voices')
for v in voices:
    if 'mongolian' in v.name.lower() or 'mn' in v.id.lower():
        tts.setProperty('voice', v.id)
        break

def speak(text: str):
    # Run in a thread so the GUI never freezes
    def _run():
        tts.say(text)
        tts.runAndWait()
    threading.Thread(target=_run, daemon=True).start()

# -------------------------------------------------
# Load known faces (encodings + names)
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
# Helper: write worker info file
# -------------------------------------------------
def save_worker_info(name: str, info: dict, photo_path: str):
    txt_path = os.path.join("worker_data", f"{name.replace(' ', '_')}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for k, v in info.items():
            f.write(f"{k}: {v}\n")
    # also save the photo
    cv2.imwrite(photo_path, cv2.imread("temp_worker.jpg"))
    os.remove("temp_worker.jpg")

# -------------------------------------------------
# GUI – main window
# -------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("Time Management System")
app.geometry("520x380")

# ---- Clock -------------------------------------------------
date_label = ctk.CTkLabel(app, text="", font=("Arial", 20, "bold"))
date_label.pack(pady=(10, 0))
time_label = ctk.CTkLabel(app, text="", font=("Arial", 42, "bold"))
time_label.pack(pady=(0, 10))

def update_clock():
    now = datetime.datetime.now()
    date_label.configure(text=now.strftime("%A, %B %d, %Y"))
    time_label.configure(text=now.strftime("%H:%M:%S"))
    app.after(1000, update_clock)
update_clock()

# ---- Info label --------------------------------------------
info_label = ctk.CTkLabel(app, text="Select an action below", font=("Arial", 16))
info_label.pack(pady=10)

# -------------------------------------------------
# 1. Add new worker (camera → form)
# -------------------------------------------------
def add_worker():
    info_label.configure(text="Opening camera…")
    app.update()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        info_label.configure(text="Camera not found!")
        return

    # ---- preview window ---------------------------------
    preview = ctk.CTkToplevel(app)
    preview.title("Capture Photo")
    preview.geometry("680x520")
    cam_label = ctk.CTkLabel(preview, text="")
    cam_label.pack()

    captured = [None]          # mutable container

    def show():
        ret, frame = cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = ctk.CTkImage(light_image=Image.fromarray(rgb),
                               dark_image=Image.fromarray(rgb),
                               size=(640, 360))
            cam_label.configure(image=img)
            cam_label.image = img
        preview.after(30, show)
    show()

    # ---- capture ---------------------------------------
    def take():
        ret, frame = cap.read()
        if ret:
            cv2.imwrite("temp_worker.jpg", frame)
            captured[0] = frame
            info_label.configure(text="Photo taken – you can retake or save")
    take()

    btns = ctk.CTkFrame(preview)
    btns.pack(pady=8)
    ctk.CTkButton(btns, text="Retake", command=take).grid(row=0, column=0, padx=8)
    ctk.CTkButton(btns, text="Save", command=lambda: save_and_form(captured[0], cap, preview)).grid(row=0, column=1, padx=8)

# -------------------------------------------------
def save_and_form(photo_frame, cap, preview_win):
    cap.release()
    preview_win.destroy()
    open_registration_form(photo_frame)

def open_registration_form(photo_frame):
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
        name = entries["Full Name"].get().strip()
        if not name:
            info_label.configure(text="Name required!")
            return
        name_key = name.replace(" ", "_")
        photo_path = f"known_faces/{name_key}.jpg"
        info = {k: v.get().strip() for k, v in entries.items()}
        save_worker_info(name, info, photo_path)

        global known_face_encodings, known_face_names
        known_face_encodings, known_face_names = load_known_faces()

        speak(f"{name} registered")
        info_label.configure(text=f"{name} registered!")
        form.destroy()

    ctk.CTkButton(form, text="Register", command=save).pack(pady=15)

# -------------------------------------------------
# 2. Show all logs
# -------------------------------------------------
def show_all_logs():
    log_win = ctk.CTkToplevel(app)
    log_win.title("Time Logs")
    log_win.geometry("720x540")

    txt = ctk.CTkTextbox(log_win, font=("Courier", 14))
    txt.pack(fill="both", expand=True, padx=12, pady=12)

    if os.path.exists("time_logs.txt"):
        with open("time_logs.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
        # pretty table
        header = f"{'Name':<20} {'Action':<8} {'Timestamp':<20}\n"
        header += "-"*50 + "\n"
        txt.insert("end", header)
        for line in lines:
            name, action, ts = line.strip().split(",", 2)
            txt.insert("end", f"{name:<20} {action:<8} {ts:<20}\n")
    else:
        txt.insert("end", "No logs yet.\n")

# -------------------------------------------------
# 3. Recognition loop (continuous)
# -------------------------------------------------
recognition_running = False
recognition_thread = None

# keep track of who is currently "IN"
active_workers = {}   # name -> last IN timestamp

def log_time(name: str, action: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("time_logs.txt", "a", encoding="utf-8") as f:
        f.write(f"{name},{action},{ts}\n")
    return ts

def recognition_loop():
    global recognition_running
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        info_label.configure(text="Camera error!")
        return

    info_label.configure(text="Recognition active – look at the camera")
    while recognition_running:
        ret, frame = cap.read()
        if not ret:
            continue
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        locations = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, locations)

        for enc in encodings:
            matches = face_recognition.compare_faces(known_face_encodings, enc, tolerance=0.55)
            name = "Unknown"
            if True in matches:
                idx = matches.index(True)
                name = known_face_names[idx]

            # ---------- known worker ----------
            if name != "Unknown":
                if name not in active_workers:                # first appearance → IN
                    ts = log_time(name, "IN")
                    active_workers[name] = ts
                    speak(f"Welcome {name}")
                    info_label.configure(text=f"{name} – IN at {ts.split()[1]}")
                else:                                         # already IN → OUT
                    in_ts = active_workers.pop(name)
                    out_ts = log_time(name, "OUT")
                    speak(f"Goodbye {name}")
                    info_label.configure(text=f"{name} – OUT at {out_ts.split()[1]}")
                # short pause so the same face isn’t processed many times
                time.sleep(2.5)

            # ---------- unknown → register ----------
            else:
                # stop camera, ask user to fill form
                recognition_running = False
                cap.release()
                info_label.configure(text="Unknown face – please register")
                speak("Unknown person, please register")
                # take a photo automatically for the form
                cv2.imwrite("temp_worker.jpg", frame)
                app.after(500, lambda: open_registration_form(frame))
                return

        # tiny delay
        time.sleep(0.05)

    cap.release()
    info_label.configure(text="Recognition stopped")

def start_recognition():
    global recognition_running, recognition_thread
    if recognition_running:
        return
    recognition_running = True
    recognition_thread = threading.Thread(target=recognition_loop, daemon=True)
    recognition_thread.start()

def stop_recognition():
    global recognition_running
    recognition_running = False
    info_label.configure(text="Select an action below")

def sens1_action():
    info_label.configure(text="Sens1 button pressed")
    
def sens2_action():
    info_label.configure(text="Sens2 button pressed")
    
def gerel1_action():
    info_label.configure(text="Gerel1 button pressed")

# -------------------------------------------------
# Buttons
# -------------------------------------------------
btn_frame = ctk.CTkFrame(app)
btn_frame.pack(pady=12)

ctk.CTkButton(btn_frame, text="Add New Worker", width=180, command=add_worker).grid(row=0, column=0, padx=8, pady=4)
ctk.CTkButton(btn_frame, text="Show All Logs", width=180, command=show_all_logs).grid(row=0, column=1, padx=8, pady=4)
ctk.CTkButton(btn_frame, text="Start Recognition", width=180, command=start_recognition).grid(row=1, column=0, padx=8, pady=4)
ctk.CTkButton(btn_frame, text="Stop Recognition", width=180, command=stop_recognition).grid(row=1, column=1, padx=8, pady=4)
ctk.CTkButton(btn_frame, text="Sens1", width=180, command=stop_recognition).grid(row=1, column=1, padx=8, pady=4)
ctk.CTkButton(btn_frame, text="Sens2", width=180, command=stop_recognition).grid(row=1, column=1, padx=8, pady=4)
ctk.CTkButton(btn_frame, text="Gerel1", width=180, command=stop_recognition).grid(row=1, column=1, padx=8, pady=4)


# -------------------------------------------------
app.mainloop()