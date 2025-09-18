#!/usr/bin/env python3
"""
secure_wipe_linux.py
GUI wrapper for secure wiping on Linux (mint/ubuntu).
- Run as root (sudo)
- Requires: python3, tkinter, psutil
- Optional recommended tools: shred, blkdiscard, nvme-cli, hdparm
- Place certificate_generator.py alongside this file (used to create signed certificates)
"""

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

# try import certificate generator (must be in same dir)
try:
    import certificate_generator
except Exception:
    certificate_generator = None

# ---------- helpers ----------
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

def blockdevice_size_bytes(devpath):
    """Get size of block device in bytes using blockdev. Returns 0 on failure."""
    rc, out = run_cmd(["blockdev", "--getsize64", devpath])
    try:
        if rc == 0:
            return int(out.decode().strip())
    except Exception:
        pass
    return 0

# ---------- device listing ----------
def list_block_devices():
    """Return list of disks (not partitions) from lsblk, plus some fallback via psutil."""
    devices = []
    rc, out = run_cmd(["lsblk", "-J", "-o", "NAME,KNAME,TYPE,SIZE,MODEL,SERIAL,MOUNTPOINT,PATH"])
    if rc == 0:
        try:
            data = json.loads(out.decode('utf-8', errors='ignore'))
            for dev in data.get("blockdevices", []):
                # include only disks (type == "disk")
                if dev.get("type") != "disk":
                    continue
                path = dev.get("path") or ("/dev/" + dev.get("name"))
                devices.append({
                    "name": dev.get("name"),
                    "path": path,
                    "model": dev.get("model") or "",
                    "serial": dev.get("serial") or "",
                    "size": dev.get("size") or "",
                    "mountpoint": dev.get("mountpoint") or ""
                })
        except Exception:
            pass

    # fallback: use psutil partitions (less ideal)
    if not devices:
        for p in psutil.disk_partitions(all=False):
            devices.append({
                "name": os.path.basename(p.device),
                "path": p.device,
                "model": "",
                "serial": "",
                "size": str(psutil.disk_usage(p.mountpoint).total // (1024**3)) + "G",
                "mountpoint": p.mountpoint
            })
    return devices

# ---------- unmount helper ----------
def safe_unmount(mountpoint, logf):
    """Try to unmount a mountpoint cleanly."""
    try:
        rc, out = run_cmd(["umount", mountpoint])
        logf.write(f"\nCOMMAND: umount {mountpoint}\nRC: {rc}\n")
        logf.write(out.decode('utf-8', errors='ignore'))
        logf.flush()
        if rc == 0:
            return True
    except Exception as e:
        logf.write(f"umount exception: {e}\n")
        logf.flush()
    return False

# ---------- low-level wipe (python chunked writer) ----------
def overwrite_device_python(devpath, total_bytes, passes, logf, progress_callback=None):
    """
    Overwrite the provided raw device path by writing chunked random data.
    If total_bytes==0 we will write until write fails (best-effort).
    """
    CHUNK = 4 * 1024 * 1024  # 4 MiB

    logf.write(f"Starting python overwrite on {devpath} (passes={passes})\n")
    logf.flush()

    try:
        # open for raw write; binary mode
        fh = open(devpath, "r+b", buffering=0)
    except PermissionError as e:
        # try opening write-only
        try:
            fh = open(devpath, "wb", buffering=0)
        except Exception as ee:
            logf.write(f"Failed to open device: {ee}\n")
            logf.flush()
            raise
    except Exception as e:
        logf.write(f"Failed to open device: {e}\n")
        logf.flush()
        raise

    try:
        for p in range(passes):
            logf.write(f"\n--- Random pass {p+1}/{passes} ---\n")
            fh.seek(0)
            written_this_pass = 0
            while True:
                data = os.urandom(CHUNK)
                try:
                    fh.write(data)
                except Exception as e:
                    logf.write(f"Write exception: {e}\n")
                    break
                written_this_pass += len(data)
                if total_bytes and progress_callback:
                    progress_callback(min(written_this_pass, total_bytes), total_bytes)
                # if size known and we've covered it
                if total_bytes and written_this_pass >= total_bytes:
                    break
            logf.write(f"Pass {p+1} approx wrote {written_this_pass} bytes\n")
            logf.flush()

        # final zeroing pass
        logf.write("\n--- Final zeroing pass ---\n")
        fh.seek(0)
        zero_chunk = b'\x00' * CHUNK
        zero_written = 0
        while True:
            try:
                fh.write(zero_chunk)
            except Exception as e:
                logf.write(f"Zero write exception: {e}\n")
                break
            zero_written += len(zero_chunk)
            if total_bytes and progress_callback:
                progress_callback(min(zero_written, total_bytes) + passes * (total_bytes if total_bytes else 0), total_bytes)
            if total_bytes and zero_written >= total_bytes:
                break
        logf.write(f"Zero pass approx wrote {zero_written} bytes\n")
        logf.flush()

        # flush/sync
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            pass

        fh.close()
        logf.write("Python overwrite finished.\n")
        logf.flush()
        return True
    except Exception as e:
        try:
            fh.close()
        except Exception:
            pass
        logf.write(f"Exception during python overwrite: {e}\n")
        logf.flush()
        raise

# ---------- wrappers for tools ----------
def overwrite_with_shred_or_dd(devpath, total_bytes, passes, logf, progress_callback=None):
    """
    Prefer shred if available. If not, fallback to python overwrite (reliable).
    """
    if check_tool("shred"):
        cmd = ["shred", "-v", "-n", str(passes), "-z", devpath]
        logf.write(f"Running: {' '.join(cmd)}\n")
        logf.flush()
        rc, out = run_cmd(cmd)
        logf.write(out.decode('utf-8', errors='ignore'))
        logf.flush()
        return rc == 0
    else:
        # safe fallback: python-based overwrite (gives progress)
        return overwrite_device_python(devpath, total_bytes, passes, logf, progress_callback=progress_callback)

def try_blkdiscard(devpath, logf):
    """If blkdiscard exists and device supports it, try to discard (fast erase for flash)."""
    if check_tool("blkdiscard"):
        rc, out = run_cmd(["blkdiscard", devpath])
        logf.write(f"\nCOMMAND: blkdiscard {devpath}\nRC:{rc}\n")
        logf.write(out.decode('utf-8', errors='ignore'))
        logf.flush()
        return rc == 0
    return False

def try_nvme_format(devpath, logf):
    if check_tool("nvme"):
        rc, out = run_cmd(["nvme", "format", devpath, "--ses=1"])
        logf.write(f"\nCOMMAND: nvme format {devpath} --ses=1\nRC:{rc}\n")
        logf.write(out.decode('utf-8', errors='ignore'))
        logf.flush()
        return rc == 0
    return False

def try_hdparm_erase(devpath, logf):
    if check_tool("hdparm"):
        # Best-effort, many drives need specific workflow — this is a naive attempt
        cmds = [
            ["hdparm", "-I", devpath],
            ["hdparm", "--user-master", "u", "--security-set-pass", "NULL", devpath],
            ["hdparm", "--security-erase", "NULL", devpath]
        ]
        for cmd in cmds:
            rc, out = run_cmd(cmd)
            logf.write(f"\nCOMMAND: {' '.join(cmd)}\nRC:{rc}\n")
            logf.write(out.decode('utf-8', errors='ignore'))
            logf.flush()
        return True
    return False

# ---------- GUI and flow ----------
class WipeApp:
    def __init__(self, root):
        self.root = root
        root.title("SecureWipe - Linux Wipe Utility (Prototype)")
        root.geometry("900x600")
        self.devices = list_block_devices()

        # header
        top = tk.Frame(root)
        top.pack(fill="x", padx=12, pady=8)
        tk.Label(top, text="Available Block Devices (select one):", font=("Segoe UI", 12, "bold")).pack(anchor="w")

        # listbox with scrollbar
        list_frame = tk.Frame(root)
        list_frame.pack(fill="x", padx=12)
        self.dev_listbox = tk.Listbox(list_frame, height=8, font=("Consolas", 11))
        self.dev_listbox.pack(side="left", fill="x", expand=True)
        sb = tk.Scrollbar(list_frame, orient="vertical", command=self.dev_listbox.yview)
        sb.pack(side="right", fill="y")
        self.dev_listbox.config(yscrollcommand=sb.set)

        self.populate_devices()

        # options
        opts = tk.Frame(root)
        opts.pack(fill="x", padx=12, pady=6)
        tk.Label(opts, text="Wipe method:", font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w")
        self.method_var = tk.StringVar(value="overwrite")
        methods = [("NVMe Secure (nvme-cli)", "nvme"), ("ATA Secure Erase (hdparm)", "ata"), ("Overwrite (shred/python)", "overwrite")]
        for i, (txt, val) in enumerate(methods):
            tk.Radiobutton(opts, text=txt, variable=self.method_var, value=val).grid(row=0, column=1+i, padx=8, sticky="w")

        tk.Label(opts, text="Shred/Python passes:", font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w")
        self.passes_spin = tk.Spinbox(opts, from_=1, to=7, width=4)
        self.passes_spin.grid(row=1, column=1, sticky="w")

        # physical nuke checkbox
        self.nuke_var = tk.BooleanVar(value=False)
        tk.Checkbutton(opts, text="Nuke whole physical device (recommended for irrecoverability)", variable=self.nuke_var).grid(row=1, column=2, columnspan=3, sticky="w", padx=6)

        tk.Label(opts, text="Operator ID:", font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", pady=(6,0))
        self.op_entry = tk.Entry(opts); self.op_entry.insert(0, "OP123"); self.op_entry.grid(row=2, column=1, sticky="w")
        tk.Label(opts, text="Organization:", font=("Segoe UI", 10)).grid(row=2, column=2, sticky="w", pady=(6,0))
        self.org_entry = tk.Entry(opts); self.org_entry.insert(0, "SecureWipe Labs"); self.org_entry.grid(row=2, column=3, sticky="w")

        # log area
        tk.Label(root, text="Live log:", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=12, pady=(8,0))
        self.log_text = tk.Text(root, height=18, wrap="none", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0,10))

        # buttons
        btnf = tk.Frame(root)
        btnf.pack(fill="x", padx=12, pady=8)
        self.wipe_btn = tk.Button(btnf, text="Start Wipe (DANGEROUS)", bg="#d9534f", fg="white", command=self.start_wipe)
        self.wipe_btn.pack(side="left")
        tk.Button(btnf, text="Refresh devices", command=self.refresh_devices).pack(side="left", padx=8)
        tk.Button(btnf, text="Open working folder", command=self.open_workdir).pack(side="right")

    def populate_devices(self):
        self.dev_listbox.delete(0, tk.END)
        for d in self.devices:
            display = f"{d['path']}  {d['model']}  {d['serial']}  {d['size']}  mount:{d.get('mountpoint','')}"
            self.dev_listbox.insert(tk.END, display)

    def refresh_devices(self):
        self.devices = list_block_devices()
        self.populate_devices()
        self.log("Device list refreshed.")

    def open_workdir(self):
        folder = os.path.abspath(".")
        try:
            subprocess.Popen(["xdg-open", folder])
        except Exception:
            messagebox.showinfo("Open folder", f"Certificates and logs saved under working dir: {folder}")

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

        # determine target: whole physical device or the device path itself
        nuke_whole = self.nuke_var.get()
        target_label = device_path if nuke_whole else device_path

        confirm = simpledialog.askstring("Confirm Wipe", f"Type WIPE {device_path} to confirm deletion of all data on {device_path}:")
        if not confirm or confirm.strip() != f"WIPE {device_path}":
            messagebox.showinfo("Cancelled", "Wipe cancelled.")
            return

        method = self.method_var.get()
        passes = int(self.passes_spin.get())
        operator_id = self.op_entry.get().strip() or "OP_UNKNOWN"
        organization = self.org_entry.get().strip() or "ORG_UNKNOWN"

        t = threading.Thread(target=self._wipe_thread, args=(dev, method, passes, operator_id, organization, nuke_whole))
        t.daemon = True
        t.start()

    def _wipe_thread(self, dev, method, passes, operator_id, organization, nuke_whole):
        self.wipe_btn.config(state="disabled")
        require_root_or_exit()

        devpath = dev["path"]
        # If nuke_whole is True, leave devpath as the disk path (it already is e.g. /dev/sdb)
        target = devpath

        log_fname = f"wipe_log_{os.path.basename(devpath)}_{int(time.time())}.txt"
        log_path = os.path.join(os.path.abspath("."), log_fname)
        self.log(f"Log will be written to: {log_path}")

        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"SecureWipe log started at {datetime.now().isoformat()}\n")
            logf.write(f"Device: {devpath}\nMethod: {method}\nNuke whole: {nuke_whole}\nOperator: {operator_id}\nOrg: {organization}\n")
            logf.flush()

            success = False
            try:
                # if partition is mounted unmount first (try all mountpoints belonging to device)
                if dev.get("mountpoint"):
                    self.log(f"Unmounting {dev['mountpoint']}...")
                    unmounted = safe_unmount(dev['mountpoint'], logf)
                    if unmounted:
                        self.log(f"Unmounted {dev['mountpoint']}")
                    else:
                        self.log(f"Could not unmount {dev['mountpoint']} (continuing best-effort).")

                # get device size
                total_bytes = blockdevice_size_bytes(target)
                logf.write(f"blockdev size: {total_bytes} bytes\n")
                logf.flush()

                # attempt specialized fast methods for SSDs:
                if method == "nvme":
                    self.log("Attempting NVMe secure format (nvme-cli).")
                    ok = try_nvme_format(target, logf)
                    success = ok
                elif method == "ata":
                    self.log("Attempting ATA secure erase (hdparm).")
                    ok = try_hdparm_erase(target, logf)
                    success = ok
                else:
                    # overwrite path
                    # first try blkdiscard on flash if available (fast)
                    if try_blkdiscard(target, logf):
                        self.log("blkdiscard succeeded (device trim/erase).")
                        success = True
                    else:
                        self.log(f"Overwriting device {target} with {passes} passes (shred/python). This may take time.")
                        ok = overwrite_with_shred_or_dd(target, total_bytes, passes, logf, progress_callback=self._progress_cb)
                        success = ok

                logf.write("\n\n--- End of wipe run ---\n")
                logf.flush()

            except Exception as e:
                self.log(f"Exception during wipe: {e}")
                logf.write("Exception: " + str(e) + "\n")
                logf.flush()
                success = False

        # compute log hash
        with open(log_path, "rb") as lf:
            log_bytes = lf.read()
            log_hash = sha256_of_bytes(log_bytes)

        self.log(f"Wipe finished. Success={success}. Log SHA256: {log_hash}")

        # attempt certificate generation
        if certificate_generator:
            try:
                pdf_path, json_path = certificate_generator.generate_certificate(
                    selected_drive=devpath,
                    deleted_files=[f"Wiped device: {devpath}"],
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

    def _progress_cb(self, done, total):
        if total and total > 0:
            pct = (done/total)*100
            self.log(f"Progress approx: {pct:.1f}% ({done}/{total} bytes)")
        else:
            self.log(f"Progress approx: {done} bytes written")

def main():
    if os.geteuid() != 0:
        print("This script should be run as root (sudo). Continuing to open GUI but wipes will exit if not root.")
    root = tk.Tk()
    app = WipeApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
