import customtkinter as ctk
import cv2
import face_recognition
import numpy as np
import os
import time
import datetime
from PIL import Image

# --- Setup app ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("Time Management System")
app.geometry("480x320")

# --- Date and Time Labels ---
date_label = ctk.CTkLabel(app, text="", font=("Arial", 20, "bold"))
date_label.pack(pady=(5, 0))

time_label = ctk.CTkLabel(app, text="", font=("Arial", 36, "bold"))
time_label.pack(pady=(0, 5))

def update_clock():
    now = datetime.datetime.now()
    date_label.configure(text=now.strftime("%A, %B %d, %Y"))
    time_label.configure(text=now.strftime("%H:%M:%S"))
    app.after(1000, update_clock)

update_clock()

# --- Info Label ---
info_label = ctk.CTkLabel(app, text="Select an action below", font=("Arial", 16))
info_label.pack(pady=10)

# Create folder if not exists
os.makedirs("known_faces", exist_ok=True)
os.makedirs("worker_data", exist_ok=True)

# --- Load Known Faces ---
def load_known_faces():
    encodings, names = [], []
    for file in os.listdir("known_faces"):
        path = os.path.join("known_faces", file)
        image = face_recognition.load_image_file(path)
        encoding = face_recognition.face_encodings(image)
        if encoding:
            encodings.append(encoding[0])
            names.append(os.path.splitext(file)[0])
    return encodings, names

known_face_encodings, known_face_names = load_known_faces()

# --- Capture and Register New Worker ---
def add_worker():
    info_label.configure(text="📸 Opening camera...")
    app.update()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        info_label.configure(text="❌ Camera not found.")
        return

    preview_window = ctk.CTkToplevel(app)
    preview_window.title("Capture Worker Photo")
    preview_window.geometry("640x480")

    # Label to show camera frames
    preview_label = ctk.CTkLabel(preview_window, text="")
    preview_label.pack()

    captured_frame = [None]  # mutable reference

    def show_frame():
        ret, frame = cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = ctk.CTkImage(light_image=Image.fromarray(rgb), dark_image=Image.fromarray(rgb), size=(640, 360))
            preview_label.configure(image=img)
            preview_label.image = img
        preview_window.after(30, show_frame)

    show_frame()

    def capture_photo():
        ret, frame = cap.read()
        if not ret:
            info_label.configure(text="❌ Failed to capture photo.")
            return
        captured_frame[0] = frame
        cv2.imwrite("temp_worker.jpg", frame)
        info_label.configure(text="✅ Photo captured. You can retake or save.")

    def retake_photo():
        capture_photo()

    def save_photo():
        cap.release()
        preview_window.destroy()
        open_worker_form(captured_frame[0])

    # Buttons
    capture_photo()
    btn_frame = ctk.CTkFrame(preview_window)
    btn_frame.pack(pady=10)
    retake_btn = ctk.CTkButton(btn_frame, text="🔁 Retake", command=retake_photo)
    retake_btn.grid(row=0, column=0, padx=10)
    save_btn = ctk.CTkButton(btn_frame, text="💾 Save", command=save_photo)
    save_btn.grid(row=0, column=1, padx=10)

def open_worker_form(captured_frame):
    form = ctk.CTkToplevel(app)
    form.title("Worker Information")
    form.geometry("320x320")

    ctk.CTkLabel(form, text="Enter Worker Information", font=("Arial", 16, "bold")).pack(pady=10)

    entries = {}
    fields = ["Full Name", "Employee ID", "Department", "Position"]
    for field in fields:
        label = ctk.CTkLabel(form, text=field)
        label.pack()
        entry = ctk.CTkEntry(form)
        entry.pack(pady=3)
        entries[field] = entry

    def save_worker_info():
        name = entries["Full Name"].get().strip().replace(" ", "_")
        if not name:
            info_label.configure(text="⚠️ Name is required.")
            return
        photo_path = f"known_faces/{name}.jpg"
        cv2.imwrite(photo_path, captured_frame)

        info_path = os.path.join("worker_data", f"{name}.txt")
        with open(info_path, "w") as f:
            for k, v in entries.items():
                f.write(f"{k}: {v.get()}\n")

        info_label.configure(text=f"✅ {name} registered successfully!")
        form.destroy()
        global known_face_encodings, known_face_names
        known_face_encodings, known_face_names = load_known_faces()

    save_btn = ctk.CTkButton(form, text="Save Worker", command=save_worker_info)
    save_btn.pack(pady=15)

# --- Recognize Worker and Log Time ---
def recognize_and_log():
    info_label.configure(text="🔍 Scanning... please look at the camera")
    app.update()

    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        info_label.configure(text="❌ Camera error.")
        return

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_locations = face_recognition.face_locations(rgb_frame)
    face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.5)
        name = "Unknown"

        if True in matches:
            match_index = matches.index(True)
            name = known_face_names[match_index]

        with open("time_logs.txt", "a") as f:
            f.write(f"{name},{time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        info_label.configure(text=f"✅ {name} logged at {time.strftime('%H:%M:%S')}")
        app.after(3000, lambda: info_label.configure(text="Select an action below"))
        return

    info_label.configure(text="❌ Face not recognized")

# --- Buttons ---
add_button = ctk.CTkButton(app, text="➕ Add New Worker", command=add_worker)
add_button.pack(pady=10)

log_button = ctk.CTkButton(app, text="📸 Log Time", command=recognize_and_log)
log_button.pack(pady=10)

app.mainloop()
