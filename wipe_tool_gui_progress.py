import tkinter as tk
from tkinter import messagebox, simpledialog

# ---------- Functions ----------
def quick_wipe():
    drives_window = tk.Toplevel(root)
    drives_window.title("Quick Wipe - Select Drives")
    drives_window.geometry("400x300")
    drives_window.configure(bg="#1e1e2f")

    tk.Label(drives_window, text="Select drives to wipe:", font=("Segoe UI", 16),
             bg="#1e1e2f", fg="#f5f5f5").pack(pady=20)

    # Mock drives
    drives = ["C:", "D:", "E:"]
    check_vars = []
    for d in drives:
        var = tk.BooleanVar()
        cb = tk.Checkbutton(drives_window, text=d, variable=var,
                            font=("Segoe UI", 14), bg="#1e1e2f", fg="#c9c9c9",
                            selectcolor="#44475a", activebackground="#1e1e2f")
        cb.pack(anchor="w", padx=40, pady=5)
        check_vars.append((d, var))

    def run_wipe():
        selected = [d for d, v in check_vars if v.get()]
        if not selected:
            messagebox.showwarning("No drive selected", "Please select at least one drive.")
        else:
            drives_window.destroy()
            messagebox.showinfo("Wipe Complete (Mock)", f"Drives wiped: {', '.join(selected)}")

    btn = tk.Button(drives_window, text="Wipe Selected Drives", font=("Segoe UI", 14, "bold"),
                    bg="#00c3ff", fg="white", activebackground="#00a5d9", width=20,
                    height=2, relief="flat", command=run_wipe,
                    bd=0, highlightthickness=0)
    btn.pack(pady=20)
    add_hover_effect(btn, "#00c3ff", "#00a5d9")

def full_wipe():
    confirm = simpledialog.askstring("Full Wipe", "Type WIPE ALL to confirm complete wipe:")
    if confirm and confirm.strip().upper() == "WIPE ALL":
        messagebox.showwarning("Full Wipe (Mock)", "All drives wiped (mock).")
    else:
        messagebox.showerror("Incorrect", "You must type 'WIPE ALL' to proceed.")

# ---------- Hover effect ----------
def add_hover_effect(widget, base_color, hover_color):
    def on_enter(e):
        widget['bg'] = hover_color
    def on_leave(e):
        widget['bg'] = base_color
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

# ---------- GUI ----------
root = tk.Tk()
root.title("Drive Wipe Utility")
root.attributes('-fullscreen', True)
root.configure(bg="#1e1e2f")

# Heading
tk.Label(root, text="Drive Wipe Utility", font=("Segoe UI", 40, "bold"),
         bg="#1e1e2f", fg="#f5f5f5").pack(pady=40)

tk.Label(root, text="Choose your wipe option below.\nQuick Wipe removes selected drives.\nFull Wipe nukes the entire system.",
         font=("Segoe UI", 18), bg="#1e1e2f", fg="#c9c9c9", justify="center").pack(pady=10)

# Buttons frame
frame = tk.Frame(root, bg="#1e1e2f")
frame.pack(pady=100)

# Quick Wipe button
quick_btn = tk.Button(frame, text="Quick Wipe", font=("Segoe UI", 20, "bold"),
                      bg="#00c3ff", fg="white", activebackground="#00a5d9",
                      relief="flat", width=15, height=2, command=quick_wipe,
                      bd=0, highlightthickness=0)
quick_btn.grid(row=0, column=0, padx=40)
add_hover_effect(quick_btn, "#00c3ff", "#00a5d9")

# Full Wipe button
full_btn = tk.Button(frame, text="Full Wipe", font=("Segoe UI", 20, "bold"),
                     bg="#ff3b30", fg="white", activebackground="#d92e26",
                     relief="flat", width=15, height=2, command=full_wipe,
                     bd=0, highlightthickness=0)
full_btn.grid(row=0, column=1, padx=40)
add_hover_effect(full_btn, "#ff3b30", "#d92e26")

# Exit button
exit_btn = tk.Button(root, text="Exit", font=("Segoe UI", 14),
                     bg="#44475a", fg="white", activebackground="#555a6b",
                     relief="flat", command=root.destroy,
                     bd=0, highlightthickness=0)
exit_btn.pack(side="bottom", pady=30)

root.bind("<Escape>", lambda e: root.destroy())

root.mainloop()
