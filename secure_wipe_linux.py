#!/usr/bin/env python3
# secure_wipe_linux.py
# GUI wrapper for secure wiping on Linux (mint/ubuntu).
# Requires: python3, tkinter, psutil, certificate_generator.py in same folder,
#           nvme-cli (for NVMe), hdparm (for ATA), shred or dd.
#
# Usage: sudo python3 secure_wipe_linux.py

import os
import sys
import json
import subprocess
import threading
import hashlib
import time
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import psutil

try:
    import certificate_generator
except Exception:
    certificate_generator = None

# ---------- Helpers ----------
def require_root_or_exit():
    if os.geteuid() != 0:
        messagebox.showerror("Root required", "This tool must be run as root (sudo). Exiting.")
        sys.exit(1)

def run_cmd(cmd, capture=True, shell=False):
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=shell)
        return 0, out
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output
    except Exception as e:
        return 1, str(e).encode('utf-8')

def check_tool(name):
    return subprocess.call(["which", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0

def sha256_of_bytes(b):
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

# ---------- Block device listing ----------
def list_block_devices():
    rc, out = run_cmd(["lsblk", "-J", "-o", "NAME,KNAME,SERIAL,SIZE,MODEL,TYPE,MOUNTPOINT,PATH"])
    devices = []
    if rc == 0:
        try:
            data = json.loads(out.decode('utf-8', errors='ignore'))
            for dev in data.get("blockdevices", []):
                if dev.get("type") != "disk":
                    continue
                devices.append({
                    "name": dev.get("name"),
                    "path": dev.get("path") or f"/dev/{dev.get('name')}",
                    "model": dev.get("model") or "",
                    "serial": dev.get("serial") or "",
                    "size": dev.get("size") or "",
                    "mountpoint": dev.get("mountpoint")
                })
        except Exception:
            pass
    if not devices:
        for part in psutil.disk_partitions(all=False):
            devices.append({
                "name": os.path.basename(part.device),
                "path": part.device,
                "model": "",
                "serial": "",
                "size": str(psutil.disk_usage(part.mountpoint).total // (1024**3)) + "GB",
                "mountpoint": part.mountpoint
            })
    return devices

# ---------- Wipe implementations ----------
def nvme_secure_format(device_path, log_file_f):
    cmds = [
        ["nvme", "list"],
        ["nvme", "format", device_path, "--ses=1"],
    ]
    for cmd in cmds:
        rc, out = run_cmd(cmd)
        log_file_f.write(f"\n\nCOMMAND: {' '.join(cmd)}\nRC: {rc}\n")
        log_file_f.write(out.decode('utf-8', errors='ignore'))
        log_file_f.flush()
    return True

def ata_secure_erase(device_path, log_file_f):
    cmds = [
        ["hdparm", "-I", device_path],
        ["hdparm", "--user-master", "u", "--security-set-pass", "NULL", device_path],
        ["hdparm", "--security-erase", "NULL", device_path]
    ]
    for cmd in cmds:
        rc, out = run_cmd(cmd)
        log_file_f.write(f"\n\nCOMMAND: {' '.join(cmd)}\nRC: {rc}\n")
        log_file_f.write(out.decode('utf-8', errors='ignore'))
        log_file_f.flush()
    return True

def overwrite_shred(device_path, passes, log_file_f, progress_callback=None):
    if check_tool("shred"):
        cmd = ["shred", "-v", "-n", str(passes), "-z", device_path]
        rc, out = run_cmd(cmd)
        log_file_f.write(f"\n\nCOMMAND: {' '.join(cmd)}\nRC: {rc}\n")
        log_file_f.write(out.decode('utf-8', errors='ignore'))
        log_file_f.flush()
        return rc == 0
    else:
        try:
            dd1 = ["dd", "if=/dev/zero", f"of={device_path}", "bs=4M", "status=progress"]
            rc1, out1 = run_cmd(dd1)
            log_file_f.write(f"\n\nCOMMAND: {' '.join(dd1)}\nRC: {rc1}\n")
            log_file_f.write(out1.decode('utf-8', errors='ignore'))
            log_file_f.flush()
            dd2 = ["dd", "if=/dev/urandom", f"of={device_path}", "bs=4M", "status=progress"]
            rc2, out2 = run_cmd(dd2)
            log_file_f.write(f"\n\nCOMMAND: {' '.join(dd2)}\nRC: {rc2}\n")
            log_file_f.write(out2.decode('utf-8', errors='ignore'))
            log_file_f.flush()
            return (rc1 == 0) and (rc2 == 0)
        except Exception as e:
            log_file_f.write("\n\nDD fallback exception: " + str(e))
            log_file_f.flush()
            return False

# ---------- GUI / Flow ----------
class WipeApp:
    def __init__(self, root):
        self.root = root
        root.title("SecureWipe - Linux Wipe Utility (Prototype)")
        root.geometry("820x520")
        self.devices = list_block_devices()

        self.frame_top = tk.Frame(root)
        self.frame_top.pack(fill="x", padx=12, pady=8)

        tk.Label(self.frame_top, text="Available Block Devices (select exactly one):", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.dev_listbox = tk.Listbox(self.frame_top, height=8, font=("Segoe UI", 11))
        self.dev_listbox.pack(fill="x", pady=6)
        for d in self.devices:
            display = f"{d['path']}  {d['model']}  {d['serial']}  {d['size']}"
            self.dev_listbox.insert(tk.END, display)

        self.frame_opts = tk.Frame(root)
        self.frame_opts.pack(fill="x", padx=12, pady=6)

        tk.Label(self.frame_opts, text="Wipe method:", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w")
        self.method_var = tk.StringVar(value="overwrite")
        methods = [("NVMe Secure (nvme-cli)", "nvme"), ("ATA Secure Erase (hdparm)", "ata"), ("Overwrite (shred/dd)", "overwrite")]
        col = 0
        for txt, val in methods:
            tk.Radiobutton(self.frame_opts, text=txt, variable=self.method_var, value=val).grid(row=0, column=col, padx=8, sticky="w")
            col += 1

        tk.Label(self.frame_opts, text="Shred passes (if overwrite):", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w")
        self.passes_spin = tk.Spinbox(self.frame_opts, from_=1, to=7, width=4)
        self.passes_spin.grid(row=1, column=1, sticky="w")

        tk.Label(self.frame_opts, text="Operator ID:", font=("Segoe UI", 10)).grid(row=1, column=2, sticky="w", padx=(20,0))
        self.op_entry = tk.Entry(self.frame_opts)
        self.op_entry.insert(0, "OP123")
        self.op_entry.grid(row=1, column=3, sticky="w")

        tk.Label(self.frame_opts, text="Organization:", font=("Segoe UI", 10)).grid(row=1, column=4, sticky="w", padx=(20,0))
        self.org_entry = tk.Entry(self.frame_opts)
        self.org_entry.insert(0, "SecureWipe Labs")
        self.org_entry.grid(row=1, column=5, sticky="w")

        tk.Label(root, text="Live log:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8,0))
        self.log_text = tk.Text(root, height=12, wrap="none", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0,10))

        btn_frame = tk.Frame(root)
        btn_frame.pack(fill="x", padx=12, pady=8)
        self.wipe_btn = tk.Button(btn_frame, text="Start Wipe (DANGEROUS)", bg="#d9534f", fg="white", command=self.start_wipe)
        self.wipe_btn.pack(side="left", padx=(0,8))
        tk.Button(btn_frame, text="Refresh devices", command=self.refresh_devices).pack(side="left")
        tk.Button(btn_frame, text="Open Certificates folder", command=self.open_cert_folder).pack(side="right")

    def refresh_devices(self):
        self.devices = list_block_devices()
        self.dev_listbox.delete(0, tk.END)
        for d in self.devices:
            display = f"{d['path']}  {d['model']}  {d['serial']}  {d['size']}"
            self.dev_listbox.insert(tk.END, display)

    def open_cert_folder(self):
        folder = os.path.abspath(".")
        try:
            subprocess.Popen(["xdg-open", folder])
        except Exception:
            messagebox.showinfo("Open folder", f"Certificates saved under working dir: {folder}")

    def log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {text}\n")
        self.log_text.see(tk.END)

    def start_wipe(self):
        sel = self.dev_listbox.curselection()
        if not sel:
            messagebox.showwarning("Select device", "Please select one device to wipe.")
            return
        idx = sel[0]
        dev = self.devices[idx]
        device_path = dev["path"]

        confirm = simpledialog.askstring("Confirm Wipe", f"Type WIPE {device_path} to confirm deletion of all data on {device_path}:")
        if not confirm or confirm.strip() != f"WIPE {device_path}":
            messagebox.showinfo("Cancelled", "Wipe cancelled.")
            return

        method = self.method_var.get()
        passes = int(self.passes_spin.get())
        operator_id = self.op_entry.get().strip() or "OP_UNKNOWN"
        organization = self.org_entry.get().strip() or "ORG_UNKNOWN"

        t = threading.Thread(target=self._wipe_thread, args=(device_path, method, passes, operator_id, organization))
        t.daemon = True
        t.start()

    def _wipe_thread(self, device_path, method, passes, operator_id, organization):
        self.wipe_btn.config(state="disabled")
        require_root_or_exit()

        log_fname = f"wipe_log_{os.path.basename(device_path)}_{int(time.time())}.txt"
        log_path = os.path.join(os.path.abspath("."), log_fname)
        self.log(f"Log will be written to: {log_path}")
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"SecureWipe log started at {datetime.now().isoformat()}\n")
            logf.write(f"Device: {device_path}\nMethod: {method}\n\n")
            logf.flush()
            success = False
            try:
                if method == "nvme":
                    if not check_tool("nvme"):
                        self.log("nvme-cli not found in PATH. Please install 'nvme-cli'. Aborting.")
                        logf.write("nvme-cli not found\n")
                    else:
                        self.log("Running NVMe secure format (nvme-cli). This may take a while.")
                        nvme_secure_format(device_path, logf)
                        success = True
                elif method == "ata":
                    if not check_tool("hdparm"):
                        self.log("hdparm not found in PATH. Please install 'hdparm'. Aborting.")
                        logf.write("hdparm not found\n")
                    else:
                        self.log("Running ATA Secure Erase (hdparm). This may require unlocking and takes time.")
                        ata_secure_erase(device_path, logf)
                        success = True
                else:
                    self.log(f"Overwriting device with {passes} passes (shred/dd).")
                    ok = overwrite_shred(device_path, passes, logf)
                    success = ok

                logf.write("\n\n--- End of wipe run ---\n")
                logf.flush()

            except Exception as e:
                self.log(f"Exception during wipe: {e}")
                logf.write("Exception: " + str(e) + "\n")
                logf.flush()
                success = False

        with open(log_path, "rb") as lf:
            log_bytes = lf.read()
            log_hash = sha256_of_bytes(log_bytes)

        self.log(f"Wipe finished. Success={success}. Log SHA256: {log_hash}")

        if certificate_generator:
            try:
                pdf_path, json_path = certificate_generator.generate_certificate(
                    selected_drive=os.path.dirname(device_path) if os.path.isdir(os.path.dirname(device_path)) else device_path,
                    deleted_files=[f"Wiped device: {device_path}"],
                    output_dir=None,
                    operator_id=operator_id,
                    organization=organization,
                    contact_info="N/A",
                    wipe_log_text=log_hash
                )
                self.log(f"Certificate generated: {pdf_path} and {json_path}")
                messagebox.showinfo("Certificate", f"Certificate generated:\n{pdf_path}\n{json_path}")
            except Exception as e:
                self.log(f"Certificate generation failed: {e}")
                messagebox.showerror("Certificate Error", f"Could not generate certificate: {e}")
        else:
            self.log("certificate_generator module not found; skipping certificate generation.")

        self.wipe_btn.config(state="normal")

def main():
    root = tk.Tk()
    app = WipeApp(root)
    root.mainloop()

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script must be run as root. Re-run with sudo.")
    main()
