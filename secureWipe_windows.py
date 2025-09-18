# secureWipe_windows.py
# Windows full-drive overwrite GUI + certificate integration
# WARNING: destructive. Run as Administrator and only on test devices.

import os
import sys
import time
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
    import hashlib
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def human_size(bytes_num):
    for unit in ['B','KB','MB','GB','TB']:
        if bytes_num < 1024.0:
            return f"{bytes_num:3.1f}{unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.1f}PB"

def get_physical_drives():
    """Return a list of physical drives via wmic (DeviceID,Model,Size,Index)."""
    drives = []
    try:
        out = subprocess.check_output(["wmic", "diskdrive", "get", "DeviceID,Model,Size,Index"], shell=True)
        lines = out.decode(errors='ignore').strip().splitlines()
        # skip header
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = [p for p in line.split() if p != ""]
            # this can be messy; fallback parse
            # we will attempt to capture Index and DeviceID (\\.\PHYSICALDRIVEn)
            try:
                # find last token numeric = Index, last-1 token size maybe numeric
                idx = int(parts[-1])
                size = parts[-2]
                deviceid = parts[0]
                model = " ".join(parts[1:-2]) if len(parts) > 3 else ""
            except Exception:
                # fallback: just iterate and build with index if present
                deviceid = line.strip()
                idx = None
                model = ""
                size = ""
            drives.append({
                "deviceid": deviceid,     # often like \\.\PHYSICALDRIVE1
                "index": idx,
                "model": model,
                "size": size
            })
    except Exception:
        pass
    return drives

def map_volume_to_physical(drive_letter):
    """
    Attempt to map a drive letter (e.g. 'F:') to a PhysicalDrive index using wmic.
    Returns physical device string like '\\\\.\\PhysicalDrive2' or None.
    """
    try:
        # Use wmic to get disk index via partition -> logicaldisk association
        # Step 1: find the partition device for this logical disk
        # Query: associators of logicaldisk where DeviceID="F:" /assocclass:Win32_LogicalDiskToPartition
        cmd = ['wmic', 'path', 'Win32_LogicalDiskToPartition', 'get', 'Antecedent,Dependent']
        out = subprocess.check_output(cmd, shell=True)
        lines = out.decode(errors='ignore').strip().splitlines()
        # parse lines to find partition that refers to our drive letter
        for line in lines:
            if not line.strip() or 'Antecedent' in line:
                continue
            if f'Dependent="Win32_LogicalDisk.DeviceID=\\"{drive_letter}\\""' in line or f'Dependent="Win32_LogicalDisk.DeviceID=\\"{drive_letter}:\\""' in line or f'"{drive_letter}"' in line:
                # line contains Antecedent which has the partition with DiskIndex
                # Example Antecedent: \\WIN-...\\ROOT\\CIMV2:Win32_DiskPartition.DeviceID="Disk #1, Partition #0"
                # We'll extract Disk #N
                if 'Disk #' in line:
                    try:
                        start = line.index('Disk #') + len('Disk #')
                        end = line.index(',', start)
                        disk_index = int(line[start:end].strip())
                        return f"\\\\.\\PhysicalDrive{disk_index}"
                    except Exception:
                        continue
    except Exception:
        pass
    return None

# ---------- Overwrite implementation ----------
def overwrite_whole_drive_windows(dev_path, passes, logf, progress_callback=None):
    """
    dev_path must be a raw device path: either '\\\\.\\PhysicalDriveN' or '\\\\.\\X' (volume)
    This function will attempt to open and write random bytes, then final zeros.
    """
    logf.write(f"\nOVERWRITE DEVICE PATH: {dev_path}\n")
    logf.flush()

    chunk_size = 4 * 1024 * 1024  # 4MiB
    try:
        fh = open(dev_path, "r+b", buffering=0)
    except Exception as e:
        logf.write(f"Failed to open {dev_path} for raw write: {e}\n")
        logf.flush()
        raise

    try:
        # Attempt to get total size via SetFilePointer64 approach not used here; we will try using Windows API via os to seek end
        try:
            fh.seek(0, os.SEEK_END)
            total_bytes = fh.tell()
            fh.seek(0)
        except Exception:
            total_bytes = 0

        if total_bytes == 0:
            logf.write("Could not determine device size. Will write until write fails.\n")
        else:
            logf.write(f"Device size (approx): {total_bytes} bytes\n")
        logf.flush()

        total_written = 0
        for p in range(passes):
            logf.write(f"\n--- Random pass {p+1}/{passes} ---\n")
            logf.flush()
            fh.seek(0)
            written_this_pass = 0
            while True:
                buf = os.urandom(chunk_size)
                try:
                    fh.write(buf)
                except Exception as e:
                    logf.write(f"Write error during random pass: {e}\n")
                    break
                written_this_pass += len(buf)
                total_written += len(buf)
                if progress_callback and total_bytes>0:
                    progress_callback(min(total_written, total_bytes), total_bytes)
                if total_bytes>0 and written_this_pass >= total_bytes:
                    break
            logf.write(f"Pass {p+1} wrote approx {written_this_pass} bytes\n")
            logf.flush()

        # final zeroing
        logf.write("\n--- Final zeroing pass ---\n")
        fh.seek(0)
        written_zero = 0
        zero = b'\x00' * chunk_size
        while True:
            try:
                fh.write(zero)
            except Exception as e:
                logf.write(f"Write error during zero pass: {e}\n")
                break
            written_zero += len(zero)
            total_written += len(zero)
            if progress_callback and total_bytes>0:
                progress_callback(min(total_written, total_bytes), total_bytes)
            if total_bytes>0 and written_zero >= total_bytes:
                break
        logf.write(f"Zero pass wrote approx {written_zero} bytes\n")
        logf.flush()

        # flush
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass

        fh.close()
        logf.write("Overwrite completed successfully (best-effort).\n")
        logf.flush()
        return True
    except Exception as e:
        logf.write(f"Exception during overwrite: {e}\n")
        logf.flush()
        try:
            fh.close()
        except Exception:
            pass
        raise

# ---------- GUI / Flow ----------
class WinWipeApp:
    def __init__(self, root):
        self.root = root
        root.title("SecureWipe - Windows Full-drive Wipe (Prototype)")
        root.geometry("920x560")

        tk.Label(root, text="Available Volumes (drive letters):", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8,0))
        self.volume_list = tk.Listbox(root, height=6, font=("Segoe UI", 11))
        self.volume_list.pack(fill="x", padx=12, pady=6)
        self.refresh_volumes()

        tk.Label(root, text="Detected Physical Drives:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8,0))
        self.phys_list = tk.Listbox(root, height=6, font=("Segoe UI", 11))
        self.phys_list.pack(fill="x", padx=12, pady=6)
        self.refresh_physical_drives()

        opts_frame = tk.Frame(root)
        opts_frame.pack(fill="x", padx=12, pady=6)
        tk.Label(opts_frame, text="Random passes:", font=("Segoe UI", 10)).grid(row=0,column=0,sticky="w")
        self.passes_spin = tk.Spinbox(opts_frame, from_=1, to=7, width=5); self.passes_spin.grid(row=0,column=1,sticky="w")

        self.nuke_phys_var = tk.BooleanVar(value=False)
        tk.Checkbutton(opts_frame, text="Nuke physical device (overwrite entire PhysicalDrive)", variable=self.nuke_phys_var).grid(row=0,column=2, padx=12, sticky="w")

        tk.Label(opts_frame, text="Operator ID:", font=("Segoe UI", 10)).grid(row=1,column=0,sticky="w")
        self.op_entry = tk.Entry(opts_frame); self.op_entry.insert(0,"OP123"); self.op_entry.grid(row=1,column=1,sticky="w")
        tk.Label(opts_frame, text="Organization:", font=("Segoe UI", 10)).grid(row=1,column=2,sticky="w")
        self.org_entry = tk.Entry(opts_frame); self.org_entry.insert(0,"SecureWipe Labs"); self.org_entry.grid(row=1,column=3,sticky="w")

        tk.Label(root, text="Live log:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8,0))
        self.log_text = tk.Text(root, height=12, wrap="none", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0,10))

        btn_frame = tk.Frame(root); btn_frame.pack(fill="x", padx=12, pady=8)
        self.wipe_btn = tk.Button(btn_frame, text="Start Wipe (DANGEROUS)", bg="#d9534f", fg="white", command=self.start_wipe)
        self.wipe_btn.pack(side="left", padx=(0,8))
        tk.Button(btn_frame, text="Refresh lists", command=self.refresh_all).pack(side="left")
        tk.Button(btn_frame, text="Open log folder", command=self.open_workdir).pack(side="right")

    def refresh_volumes(self):
        self.volume_list.delete(0, tk.END)
        partitions = psutil.disk_partitions(all=False)
        seen = set()
        for p in partitions:
            drive = p.device  # e.g. 'F:\\'
            if drive.endswith("\\") or drive.endswith("/"):
                drive_letter = drive[0:2]
            else:
                drive_letter = (drive + "")[:2]
            if drive_letter not in seen:
                seen.add(drive_letter)
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    size = human_size(usage.total)
                except Exception:
                    size = "Unknown"
                display = f"{drive_letter}    ({p.mountpoint})    {size}"
                self.volume_list.insert(tk.END, display)

    def refresh_physical_drives(self):
        self.phys_list.delete(0, tk.END)
        phys = get_physical_drives()
        if not phys:
            self.phys_list.insert(tk.END, "No physical drive info via WMIC.")
        else:
            for d in phys:
                idx = d.get("index")
                dev = d.get("deviceid") or f"\\\\.\\PhysicalDrive{idx}" if idx is not None else d.get("deviceid")
                model = d.get("model", "")
                size = d.get("size", "")
                self.phys_list.insert(tk.END, f"{dev}    {model}    {size}")

    def refresh_all(self):
        self.refresh_volumes()
        self.refresh_physical_drives()

    def open_workdir(self):
        try:
            import subprocess
            subprocess.Popen(["explorer", os.path.abspath(".")])
        except Exception:
            messagebox.showinfo("Open folder", f"Logs and certificates are under: {os.path.abspath('.')}")

    def log(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {text}\n")
        self.log_text.see(tk.END)

    def start_wipe(self):
        if not is_admin():
            messagebox.showerror("Administrator required", "Please run this script as Administrator.")
            return

        # Determine chosen target: prefer physical list selection if nuke option
        nuke_phys = self.nuke_phys_var.get()
        chosen_phys = None
        if nuke_phys:
            selp = self.phys_list.curselection()
            if not selp:
                messagebox.showwarning("Select physical device", "Please select a physical device to nuke.")
                return
            chosen_phys = self.phys_list.get(selp[0]).split()[0]  # e.g. \\.\PhysicalDrive2
            target_label = chosen_phys
        else:
            selv = self.volume_list.curselection()
            if not selv:
                messagebox.showwarning("Select volume", "Please select a volume (drive letter).")
                return
            vol = self.volume_list.get(selv[0]).split()[0]  # e.g. 'F:'
            # If user selected a volume, we still allow mapping to physical drive explicitly if they want
            target_label = vol
            # attempt auto-map to physical for user confirmation if they have not chosen physical explicitly
            phys = map_volume_to_physical(vol)
            if phys:
                # ask user if they want to nuke physical drive instead
                ans = messagebox.askyesno("Map to physical", f"Volume {vol} maps to {phys}. Do you want to overwrite the entire physical drive instead? (Yes = entire device, No = only volume)")
                if ans:
                    chosen_phys = phys
                    nuke_phys = True
                    target_label = phys

        # require strong confirmation
        confirm = simpledialog.askstring("Confirm", f"Type EXACTLY: WIPE DEVICE {target_label}")
        if not confirm or confirm.strip() != f"WIPE DEVICE {target_label}":
            messagebox.showinfo("Cancelled", "Wipe cancelled.")
            return

        passes = int(self.passes_spin.get())
        operator = self.op_entry.get().strip() or "OP_UNKNOWN"
        org = self.org_entry.get().strip() or "ORG_UNKNOWN"

        # start thread
        t = threading.Thread(target=self._wipe_thread, args=(target_label, chosen_phys, passes, operator, org))
        t.daemon = True
        t.start()

    def _wipe_thread(self, target_label, chosen_phys, passes, operator_id, organization):
        self.wipe_btn.config(state="disabled")
        
        # log_fname = f"wipe_log_{target_label.replace('\\\\','').replace(':','')}_{int(time.time())}.txt"
        safe_label = target_label.replace("\\", "").replace(":", "")
        log_fname = f"wipe_log_{safe_label}_{int(time.time())}.txt"

        log_path = os.path.join(os.path.abspath("."), log_fname)
        self.log(f"Writing log to: {log_path}")
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"SecureWipe Windows overwrite\nStarted: {datetime.now().isoformat()}\nTarget: {target_label}\nPhysical target: {chosen_phys}\nPasses: {passes}\nOperator: {operator_id}\nOrg: {organization}\n")
            logf.flush()

            def progress_cb(done, total):
                pct = (done/total)*100 if total>0 else 0
                self.log(f"Progress: {pct:.1f}% ({human_size(done)} / {human_size(total)})")

            try:
                # choose path to write
                if chosen_phys:
                    dev_path = chosen_phys
                else:
                    # user opted to overwrite only the volume; use \\.\X (volume) path
                    dev_path = r"\\.\%s" % target_label.strip(':')

                self.log(f"Starting overwrite on: {dev_path}")
                overwrite_whole_drive_windows(dev_path, passes, logf, progress_callback=progress_cb)
                success = True
            except Exception as e:
                logf.write(f"Exception during overwrite: {e}\n")
                logf.flush()
                self.log(f"Exception: {e}")
                success = False

            logf.write(f"Finished at {datetime.now().isoformat()}\n")
            logf.flush()

        # compute log hash
        with open(log_path, "rb") as lf:
            log_bytes = lf.read()
            log_hash = sha256_of_bytes(log_bytes)
        self.log(f"Wipe finished. Success={success}. Log SHA256: {log_hash}")

        # generate certificate if module available
        if certificate_generator:
            try:
                pdf_path, json_path = certificate_generator.generate_certificate(
                    selected_drive=target_label,
                    deleted_files=[f"Full overwrite {target_label}"],
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
    main()
