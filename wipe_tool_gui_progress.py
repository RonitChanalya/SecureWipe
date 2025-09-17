# wipe_tool_gui_progress.py
import tkinter as tk
from tkinter import messagebox, simpledialog
import psutil
import os, shutil, time
import certificate_generator   # import the fixed module

# ---------- Color Helpers ----------
def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return '#%02x%02x%02x' % rgb

def interpolate_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

# ---------- Themes ----------
dark_theme = {
    "bg": "#1e1e2f",
    "fg": "#f5f5f5",
    "subtext": "#c9c9c9",
    "button_quick": "#00c3ff",
    "button_quick_hover": "#00a5d9",
    "button_full": "#ff3b30",
    "button_full_hover": "#d92e26",
    "button_exit": "#44475a",
    "button_exit_hover": "#555a6b",
    "progress_bg": "#44475a",
    "progress_fill": "#00c3ff"
}

light_theme = {
    "bg": "#f5f5f5",
    "fg": "#1e1e2f",
    "subtext": "#44475a",
    "button_quick": "#007BFF",
    "button_quick_hover": "#0056b3",
    "button_full": "#dc3545",
    "button_full_hover": "#b52a36",
    "button_exit": "#6c757d",
    "button_exit_hover": "#5a6268",
    "progress_bg": "#dcdcdc",
    "progress_fill": "#007BFF"
}

current_theme = dark_theme  # Start dark by default

# ---------- Hover effect ----------
def add_hover_effect(widget, base_color, hover_color):
    def on_enter(e):
        widget['bg'] = hover_color
    def on_leave(e):
        widget['bg'] = base_color
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

# ---------- SAFE WIPE FUNCTION with Progress ----------
def wipe_demo_folder(selected_drive):
    demo_folder = os.path.join(selected_drive, "DemoWipe")

    if not os.path.exists(demo_folder):
        messagebox.showwarning("Folder Missing",
                               f"No 'DemoWipe' folder found on {selected_drive}\n"
                               "Please create one and put some files in it.")
        return

    confirm = messagebox.askyesno("Confirm Wipe",
                                  f"This will DELETE the entire folder:\n{demo_folder}\nProceed?")
    if not confirm:
        return

    # Gather all files to delete first
    files_to_delete = []
    for root_dir, dirs, files in os.walk(demo_folder):
        for f in files:
            files_to_delete.append(os.path.join(root_dir, f))
    total_items = len(files_to_delete)

    # Progress window
    progress_win = tk.Toplevel(root)
    progress_win.title("Wiping...")
    progress_win.geometry("420x120")
    progress_win.configure(bg=current_theme["bg"])
    tk.Label(progress_win, text=f"Wiping {selected_drive} DemoWipe...",
             bg=current_theme["bg"], fg=current_theme["fg"],
             font=("Segoe UI", 14)).pack(pady=8)
    progress_bar = tk.Frame(progress_win, bg=current_theme["progress_bg"], height=20)
    progress_bar.pack(fill="x", padx=20, pady=8)
    bar_fill = tk.Frame(progress_bar, bg=current_theme["progress_fill"], height=20, width=0)
    bar_fill.pack(side="left", fill="y")

    def update_progress(done):
        percent = (done / total_items) * 100 if total_items > 0 else 100
        width = int((percent/100) * 360)
        bar_fill.config(width=width)
        progress_win.update_idletasks()

    deleted_files = []
    try:
        done = 0
        for f in files_to_delete:
            try:
                os.remove(f)
                deleted_files.append(f)
            except Exception:
                # if delete fails, continue; will be reported in certificate if needed
                pass
            done += 1
            update_progress(done)

        # Remove remaining empty directories including DemoWipe
        shutil.rmtree(demo_folder, ignore_errors=True)
        progress_win.destroy()
        messagebox.showinfo("Wipe Complete",
                            f"The folder {demo_folder} and all its contents have been deleted.")

        # Generate certificate after wipe
        try:
            # Pass selected_drive and deleted_files to certificate generator
            pdf_path, json_path = certificate_generator.generate_certificate(selected_drive, deleted_files)
            messagebox.showinfo("Certificate Generated",
                                f"Certificate saved:\n{pdf_path}\n{json_path}")
        except Exception as e:
            messagebox.showerror("Certificate Error", f"Could not generate certificate:\n{e}")

    except Exception as e:
        progress_win.destroy()
        messagebox.showerror("Error", f"Could not wipe folder: {e}")

# ---------- Quick Wipe ----------
def quick_wipe():
    drives_window = tk.Toplevel(root)
    drives_window.title("Quick Wipe - Select Drives")
    drives_window.geometry("520x420")
    drives_window.configure(bg=current_theme["bg"])

    # ---------- Force window on top ----------
    drives_window.attributes('-topmost', True)
    drives_window.update()
    drives_window.attributes('-topmost', False)

    tk.Label(drives_window, text="Select drives to wipe:", font=("Segoe UI", 16),
             bg=current_theme["bg"], fg=current_theme["fg"]).pack(pady=12)

    # Detect drives
    partitions = psutil.disk_partitions(all=False)
    drives_info = []
    check_vars = []

    for p in partitions:
        try:
            usage = psutil.disk_usage(p.mountpoint)
            used_gb = usage.used // (1024**3)
            total_gb = usage.total // (1024**3)
            percent = usage.percent
        except PermissionError:
            used_gb = total_gb = percent = 0

        drives_info.append((p.device, used_gb, total_gb, percent))

    for d, used, total, percent in drives_info:
        var = tk.BooleanVar()
        frame_drive = tk.Frame(drives_window, bg=current_theme["bg"])
        frame_drive.pack(fill="x", padx=30, pady=6)

        cb = tk.Checkbutton(frame_drive,
                            text=f"{d}  {used}GB used / {total}GB total",
                            variable=var, font=("Segoe UI", 14),
                            bg=current_theme["bg"], fg=current_theme["subtext"],
                            selectcolor=current_theme["progress_bg"],
                            activebackground=current_theme["bg"])
        cb.pack(anchor="w")

        # Add bar
        bar_frame = tk.Frame(frame_drive, bg=current_theme["progress_bg"], height=10)
        bar_frame.pack(fill="x", padx=40, pady=3)
        bar_fill = tk.Frame(bar_frame, bg=current_theme["progress_fill"], height=10,
                            width=int(percent * 3))  # scale for width
        bar_fill.pack(side="left", fill="y")

        check_vars.append((d, var))

    def run_wipe():
        selected = [d for d, v in check_vars if v.get()]
        if not selected:
            messagebox.showwarning("No drive selected", "Please select at least one drive.")
        else:
            drives_window.destroy()
            for drive in selected:
                wipe_demo_folder(drive)

    btn = tk.Button(drives_window, text="Wipe Selected Drives", font=("Segoe UI", 14, "bold"),
                    bg=current_theme["button_quick"], fg="white",
                    activebackground=current_theme["button_quick_hover"], width=22,
                    height=2, relief="flat", command=run_wipe,
                    bd=0, highlightthickness=0)
    btn.pack(pady=14)
    add_hover_effect(btn, current_theme["button_quick"], current_theme["button_quick_hover"])

# ---------- Full Wipe ----------
def full_wipe():
    confirm = simpledialog.askstring("Full Wipe", "Type WIPE ALL to confirm complete wipe:")
    if confirm and confirm.strip().upper() == "WIPE ALL":
        messagebox.showwarning("Full Wipe (Mock)", "All drives wiped (mock).")
    else:
        messagebox.showerror("Incorrect", "You must type 'WIPE ALL' to proceed.")

# ---------- Theme Transition ----------
def smooth_transition(old_theme, new_theme, steps=20, delay=15):
    old_bg = hex_to_rgb(old_theme["bg"])
    new_bg = hex_to_rgb(new_theme["bg"])
    old_fg = hex_to_rgb(old_theme["fg"])
    new_fg = hex_to_rgb(new_theme["fg"])
    old_sub = hex_to_rgb(old_theme["subtext"])
    new_sub = hex_to_rgb(new_theme["subtext"])

    def step(i=0):
        t = i / steps
        bg = rgb_to_hex(interpolate_color(old_bg, new_bg, t))
        fg = rgb_to_hex(interpolate_color(old_fg, new_fg, t))
        sub = rgb_to_hex(interpolate_color(old_sub, new_sub, t))

        root.configure(bg=bg)
        heading.config(bg=bg, fg=fg)
        subheading.config(bg=bg, fg=sub)
        frame.config(bg=bg)

        if i < steps:
            root.after(delay, step, i+1)
        else:
            apply_theme()
    step()

def toggle_theme():
    global current_theme
    old_theme = current_theme
    current_theme = light_theme if current_theme == dark_theme else dark_theme
    smooth_transition(old_theme, current_theme)

def apply_theme():
    quick_btn.config(bg=current_theme["button_quick"], activebackground=current_theme["button_quick_hover"])
    full_btn.config(bg=current_theme["button_full"], activebackground=current_theme["button_full_hover"])
    exit_btn.config(bg=current_theme["button_exit"], activebackground=current_theme["button_exit_hover"])
    toggle_btn.config(bg=current_theme["button_exit"], activebackground=current_theme["button_exit_hover"])
    add_hover_effect(quick_btn, current_theme["button_quick"], current_theme["button_quick_hover"])
    add_hover_effect(full_btn, current_theme["button_full"], current_theme["button_full_hover"])
    add_hover_effect(exit_btn, current_theme["button_exit"], current_theme["button_exit_hover"])
    add_hover_effect(toggle_btn, current_theme["button_exit"], current_theme["button_exit_hover"])

# ---------- GUI ----------
root = tk.Tk()
root.title("Drive Wipe Utility")
root.attributes('-fullscreen', True)
root.configure(bg=current_theme["bg"])

heading = tk.Label(root, text="Drive Wipe Utility", font=("Segoe UI", 40, "bold"),
                   bg=current_theme["bg"], fg=current_theme["fg"])
heading.pack(pady=40)

subheading = tk.Label(root, text="Choose your wipe option below.\nQuick Wipe removes DemoWipe folder from selected drives.\nFull Wipe nukes the entire system (mock).",
                      font=("Segoe UI", 18), bg=current_theme["bg"],
                      fg=current_theme["subtext"], justify="center")
subheading.pack(pady=10)

frame = tk.Frame(root, bg=current_theme["bg"])
frame.pack(pady=100)

quick_btn = tk.Button(frame, text="Quick Wipe", font=("Segoe UI", 20, "bold"),
                      bg=current_theme["button_quick"], fg="white",
                      activebackground=current_theme["button_quick_hover"],
                      relief="flat", width=15, height=2, command=quick_wipe,
                      bd=0, highlightthickness=0)
quick_btn.grid(row=0, column=0, padx=40)
add_hover_effect(quick_btn, current_theme["button_quick"], current_theme["button_quick_hover"])

full_btn = tk.Button(frame, text="Full Wipe", font=("Segoe UI", 20, "bold"),
                     bg=current_theme["button_full"], fg="white",
                     activebackground=current_theme["button_full_hover"],
                     relief="flat", width=15, height=2, command=full_wipe,
                     bd=0, highlightthickness=0)
full_btn.grid(row=0, column=1, padx=40)
add_hover_effect(full_btn, current_theme["button_full"], current_theme["button_full_hover"])

exit_btn = tk.Button(root, text="Exit", font=("Segoe UI", 14),
                     bg=current_theme["button_exit"], fg="white",
                     activebackground=current_theme["button_exit_hover"],
                     relief="flat", command=root.destroy,
                     bd=0, highlightthickness=0)
exit_btn.pack(side="bottom", pady=30)
add_hover_effect(exit_btn, current_theme["button_exit"], current_theme["button_exit_hover"])

toggle_btn = tk.Button(root, text="Toggle Dark/Light", font=("Segoe UI", 14),
                       bg=current_theme["button_exit"], fg="white",
                       activebackground=current_theme["button_exit_hover"],
                       relief="flat", command=toggle_theme,
                       bd=0, highlightthickness=0)
toggle_btn.pack(side="bottom", pady=10)
add_hover_effect(toggle_btn, current_theme["button_exit"], current_theme["button_exit_hover"])

root.bind("<Escape>", lambda e: root.destroy())

root.mainloop()
