# secureWipe_windows.py
# Windows full-drive overwrite GUI + certificate integration
# WARNING: destructive. Run as Administrator and only on test devices.

import os
import sys
import time
import json
import ctypes
import hashlib
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import psutil
import subprocess

try:
    import certificate_generator
except Exception:
    certificate_generator = None

# ---------- Helpers ----------
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def sha256_of_bytes(b):
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def human_size(bytes_num):
    for unit in ['B','KB','MB','GB','TB','PB']:
        if bytes_num < 1024.0:
            return f"{bytes_num:3.1f}{unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.1f}EB"

# ---------- Physical drive discovery (WMIC) ----------
def list_physical_drives_wmic():
    """
    Returns list of dicts: { 'deviceid': '\\\\.\\PhysicalDriveN', 'model': ..., 'size': int_bytes }
    Uses WMIC (Windows-only) as best-effort.
    """
    drives = []
    try:
        out = subprocess.check_output("wmic diskdrive get DeviceID,Model,Size /format:csv", shell=True)
        text = out.decode(errors='ignore').strip().splitlines()
        # CSV format: Node,DeviceID,Model,Size
        for line in text:
            if not line or line.lower().startswith("node"):
                continue
            parts = line.split(',')
            if len(parts) < 4:
                continue
            _, deviceid, model, size = parts
            if deviceid:
                deviceid = deviceid.strip()
                model = model.strip()
                try:
                    size_bytes = int(size.strip())
                except:
                    size_bytes = 0
                drives.append({
                    "deviceid": deviceid,  # like \\.\PHYSICALDRIVE2
                    "model": model,
                    "size": size_bytes
                })
    except Exception:
        # If wmic fails, return empty list
        pass
    return drives

# ---------- Overwrite implementation ----------
def overwrite_raw_device(dev_path, total_bytes, passes, logf, progress_callback=None):
    """
    Core: open dev_path (raw) and overwrite.
    dev_path: string - either r"\\.\F:" or r"\\.\PhysicalDrive2"
    total_bytes: int or 0 if unknown
    passes: number of random passes (1..7)
    logf: file handle
    progress_callback(done_bytes, total_bytes)
    """
    CHUNK = 4 * 1024 * 1024  # 4 MB
    logf.write(f"Opening raw device for write: {dev_path}\n")
    logf.flush()
    try:
        fh = open(dev_path, "r+b", buffering=0)
    except Exception as e:
        logf.write(f"Failed to open {dev_path} for raw write: {e}\n")
        logf.flush()
        raise

    try:
        total_written = 0
        # Random passes
        for p in range(passes):
            logf.write(f"\n--- Random pass {p+1}/{passes} ---\n")
            logf.flush()
            fh.seek(0)
            bytes_written_this_pass = 0
            while True:
                chunk = os.urandom(CHUNK)
                try:
                    fh.write(chunk)
                except Exception as e:
                    logf.write(f"Write exception during random pass: {e}\n")
                    break
                bytes_written_this_pass += len(chunk)
                total_written += len(chunk)
                if progress_callback and total_bytes > 0:
                    progress_callback(min(total_written, total_bytes), total_bytes)
                # stop when we've written at least device size (if known)
                if total_bytes > 0 and bytes_written_this_pass >= total_bytes:
                    break
            logf.write(f"Pass {p+1} wrote approx {bytes_written_this_pass} bytes\n")
            logf.flush()

        # Final zero pass
        logf.write("\n--- Final zeroing pass ---\n")
        fh.seek(0)
        bytes_written_zero = 0
        zero_chunk = b'\x00' * CHUNK
        while True:
            try:
                fh.write(zero_chunk)
            except Exception as e:
                logf.write(f"Write exception during zero pass: {e}\n")
                break
            bytes_written_zero += len(zero_chunk)
            total_written += len(zero_chunk)
            if progress_callback and total_bytes > 0:
                progress_callback(min(total_written, total_bytes), total_bytes)
            if total_bytes > 0 and bytes_written_zero >= total_bytes:
                break
        logf.write(f"Zero pass wrote approx {bytes_written_zero} bytes\n")
        logf.flush()

        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass

        logf.write("Overwrite finished. Closing handle.\n")
        logf.flush()
        fh.close()
        return True
    except Exception:
        try:
            fh.close()
        except:
            pass
        raise

# ---------- GUI / Flow ----------
class WinWipeApp:
    def __init__(self, root):
        self.root = root
        root.title("SecureWipe - Windows Full-drive Wipe (Prototype)")
        root.geometry("900x560")

        top = tk.Frame(root); top.pack(fill="x", pady=8, padx=8)
        tk.Label(top, text="Select target (logical volume or physical device):", font=("Segoe UI", 11, "bold")).pack(anchor="w")

        # listbox with scrollbar
        listframe = tk.Frame(root)
        listframe.pack(fill="x", padx=12)
        self.listbox = tk.Listbox(listframe, height=8, font=("Segoe UI", 11))
        self.listbox.pack(side="left", fill="x", expand=True)
        scrollbar = tk.Scrollbar(listframe, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        self.refresh_btn = tk.Button(root, text="Refresh drives", command=self.refresh_drives)
        self.refresh_btn.pack(anchor="w", padx=12, pady=(6,0))

        opts_frame = tk.Frame(root)
        opts_frame.pack(fill="x", padx=12, pady=6)
        tk.Label(opts_frame, text="Random passes:", font=("Segoe UI", 10)).grid(row=0,column=0,sticky="w")
        self.passes_spin = tk.Spinbox(opts_frame, from_=1, to=7, width=5)
        self.passes_spin.grid(row=0,column=1,sticky="w")

        tk.Label(opts_frame, text="Operator ID:", font=("Segoe UI", 10)).grid(row=0,column=2,sticky="w", padx=(20,0))
        self.op_entry = tk.Entry(opts_frame); self.op_entry.insert(0,"OP123"); self.op_entry.grid(row=0,column=3,sticky="w")

        tk.Label(opts_frame, text="Organization:", font=("Segoe UI", 10)).grid(row=0,column=4,sticky="w", padx=(20,0))
        self.org_entry = tk.Entry(opts_frame); self.org_entry.insert(0,"SecureWipe Labs"); self.org_entry.grid(row=0,column=5,sticky="w")

        tk.Label(root, text="Live log:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8,0))
        self.log_text = tk.Text(root, height=14, wrap="none", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0,10))

        btn_frame = tk.Frame(root); btn_frame.pack(fill="x", padx=12, pady=8)
        self.wipe_btn = tk.Button(btn_frame, text="Start Full Device Wipe (DANGEROUS)", bg="#d9534f", fg="white", command=self.start_wipe)
        self.wipe_btn.pack(side="left", padx=(0,8))
        tk.Button(btn_frame, text="Open workdir", command=self.open_workdir).pack(side="right")

        self.refresh_drives()

    def log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {text}\n")
        self.log_text.see(tk.END)

    def open_workdir(self):
        try:
            subprocess.Popen(["explorer", os.path.abspath(".")])
        except Exception:
            messagebox.showinfo("Open folder", f"Logs and certificates are under: {os.path.abspath('.')}")

    def refresh_drives(self):
        """
        Populate listbox with:
          - Logical volumes (drive letters) shown as "F:  (mountpoint)  3.8GB"
          - Physical drives (\\.\PHYSICALDRIVEN) shown as "\\.\PHYSICALDRIVE2  (Model)  3.8GB"
        The underlying entry string will be used to determine dev path.
        """
        self.listbox.delete(0, tk.END)

        # Logical volumes
        partitions = psutil.disk_partitions(all=False)
        seen_letters = set()
        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                size = human_size(usage.total)
            except Exception:
                size = "Unknown"
            dev = p.device  # e.g. 'F:\\'
            # normalize to 'F:'
            drive_letter = None
            if dev and len(dev) >= 2 and dev[1] == ':':
                drive_letter = dev[0:2]
            elif dev and dev.endswith("\\"):
                drive_letter = dev[0:2]
            if not drive_letter:
                continue
            if drive_letter in seen_letters:
                continue
            seen_letters.add(drive_letter)
            display = f"{drive_letter}\t(volume)    {p.mountpoint}    {size}"
            self.listbox.insert(tk.END, display)

        # Physical drives (wmic)
        phys = list_physical_drives_wmic()
        for d in phys:
            deviceid = d.get("deviceid")  # e.g. \\.\PHYSICALDRIVE2
            model = d.get("model") or ""
            size = d.get("size") or 0
            size_h = human_size(size) if size else "Unknown"
            display = f"{deviceid}\t(physical)    {model}    {size_h}"
            self.listbox.insert(tk.END, display)

        # Also add raw physical devices for which wmic failed; try to enumerate by checking \\.\PhysicalDriveN up to 10
        # Only if no physicals found via WMIC
        if not phys:
            for n in range(0, 8):
                candidate = r"\\.\PhysicalDrive{}".format(n)
                try:
                    # attempt to open minimal handle to see if exists (read-only)
                    with open(candidate, "rb", buffering=0):
                        pass
                    display = f"{candidate}\t(physical)    Unknown model"
                    self.listbox.insert(tk.END, display)
                except Exception:
                    # not present
                    pass

    def start_wipe(self):
        if not is_admin():
            messagebox.showerror("Administrator required", "Please run this script as Administrator.")
            return
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Select target", "Please select a logical volume or a physical device.")
            return
        entry = self.listbox.get(sel[0])
        target_token = entry.split('\t')[0].strip()
        # target_token is either 'F:' or '\\.\PHYSICALDRIVE2'
        # Ask explicit confirmation
        confirm_text = f"Type WIPE {target_token} to confirm full-device overwrite (This is IRREVERSIBLE):"
        confirm = simpledialog.askstring("Confirm Wipe", confirm_text)
        if not confirm or confirm.strip() != f"WIPE {target_token}":
            messagebox.showinfo("Cancelled", "Wipe cancelled.")
            return

        passes = int(self.passes_spin.get())
        operator = self.op_entry.get().strip() or "OP_UNKNOWN"
        org = self.org_entry.get().strip() or "ORG_UNKNOWN"

        t = threading.Thread(target=self._wipe_thread, args=(target_token, passes, operator, org))
        t.daemon = True
        t.start()

    def _wipe_thread(self, target_token, passes, operator_id, organization):
        self.wipe_btn.config(state="disabled")
        ts = int(time.time())
        # use short name for log file
        safe_name = target_token.replace('\\', '').replace(':', '')
        log_fname = f"wipe_log_{safe_name}_{ts}.txt"
        log_path = os.path.join(os.path.abspath("."), log_fname)
        self.log(f"Writing log to: {log_path}")

        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"SecureWipe Windows full-device overwrite\nStarted: {datetime.now().isoformat()}\nTarget: {target_token}\nPasses: {passes}\nOperator: {operator_id}\nOrg: {organization}\n")
            logf.flush()

            # compute target dev path & size
            dev_path = None
            total_bytes = 0
            if target_token.upper().startswith(r"\\.\PHYSICALDRIVE".upper()):
                dev_path = target_token
                # try to get size via wmic
                try:
                    out = subprocess.check_output(f'wmic diskdrive where "DeviceID=\'{target_token}\'" get Size /format:csv', shell=True)
                    text = out.decode(errors='ignore').strip().splitlines()
                    for line in text:
                        if not line or line.lower().startswith("node"):
                            continue
                        parts = line.split(',')
                        if len(parts) >= 2:
                            try:
                                total_bytes = int(parts[-1])
                            except Exception:
                                total_bytes = 0
                except Exception:
                    # fallback: 0
                    total_bytes = 0
            else:
                # assume it's a drive letter like 'F:'
                # Build raw path \\.\F:
                if not target_token.endswith(':'):
                    target_token = target_token + ":"
                dev_path = r"\\.\%s" % target_token
                # Determine size via psutil
                try:
                    mountpoint = target_token + "\\"
                    usage = psutil.disk_usage(mountpoint)
                    total_bytes = usage.total
                except Exception:
                    total_bytes = 0

            logf.write(f"Resolved dev_path: {dev_path}\n")
            if total_bytes:
                logf.write(f"Resolved size: {total_bytes} bytes ({human_size(total_bytes)})\n")
            else:
                logf.write("Size unknown; will write until device reports write error or until OS stops writes.\n")
            logf.flush()

            def progress_cb(done, total):
                pct = (done/total)*100 if total and total>0 else 0
                self.log(f"Progress: {pct:.1f}% ({human_size(done)} / {human_size(total)})" if total>0 else f"Progress bytes written: {human_size(done)}")

            success = False
            try:
                overwrite_raw_device(dev_path, total_bytes, passes, logf, progress_callback=progress_cb)
                success = True
            except Exception as e:
                logf.write(f"Exception during overwrite: {e}\n")
                logf.flush()
                self.log(f"Exception: {e}")
                success = False

            logf.write(f"Finished at {datetime.now().isoformat()}\n")
            logf.flush()

        # compute SHA256 hash of log
        with open(log_path, "rb") as lf:
            log_bytes = lf.read()
            log_hash = sha256_of_bytes(log_bytes)
        self.log(f"Wipe finished. Success={success}. Log SHA256: {log_hash}")

        # generate certificate if module available
        if certificate_generator:
            try:
                pdf_path, json_path = certificate_generator.generate_certificate(
                    selected_drive=target_token,
                    deleted_files=[f"Full-device overwrite {target_token}"],
                    output_dir=None,
                    operator_id=operator_id,
                    organization=organization,
                    contact_info="N/A",
                    wipe_log_text=log_hash
                )
                self.log(f"Certificate generated: {pdf_path}, {json_path}")
                messagebox.showinfo("Certificate", f"Certificate created:\n{pdf_path}\n{json_path}")
            except Exception as e:
                self.log(f"Certificate generation failed: {e}")
                messagebox.showerror("Certificate Error", f"Could not generate certificate: {e}")
        else:
            self.log("certificate_generator not found; skipping certificate.")

        self.wipe_btn.config(state="normal")

def main():
    root = tk.Tk()
    app = WinWipeApp(root)
    root.mainloop()

if __name__ == "__main__":
    if not is_admin():
        messagebox.showwarning("Administrator required", "Please run this script as Administrator.")
    main()
