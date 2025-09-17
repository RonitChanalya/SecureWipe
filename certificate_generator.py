# certificate_generator.py
import subprocess
import platform
from uuid import uuid4
from datetime import datetime
import json
import psutil
import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

def generate_certificate(selected_drive=None, deleted_files=None, output_dir=None):
    """
    Generates a professional PDF + JSON certificate.
    Parameters:
      - selected_drive: drive path string (e.g. "D:\\" or "/mnt/some")
      - deleted_files: list of deleted file paths (can be [])
      - output_dir: optional directory where certificates will be saved.
                    If None, it will create a 'Certificates' folder under selected_drive.
    Returns: (pdf_fullpath, json_fullpath)
    """
    if deleted_files is None:
        deleted_files = []

    # Ensure selected_drive is a path string when provided
    if selected_drive:
        selected_drive = os.path.abspath(selected_drive)

    # ------------------------------------------------------------------
    # COMPANY & APP DETAILS
    # ------------------------------------------------------------------
    company_name = "SecureWipe"
    company_address = "VIT-AP University MH-5 1018 717"
    company_contact = "+91 7453811860"
    company_website = "https://secure-wipe-xi.vercel.app/"
    verify_link = "https://secure-wipe-xi.vercel.app/verify"
    software_version = "SecureWipe v2.0"

    # ------------------------------------------------------------------
    # AUTO DETECT DEVICE INFO
    # ------------------------------------------------------------------
    system_make_model = f"{platform.node()} / {platform.system()} {platform.release()}"

    # Try to get more detailed system info on Windows (best-effort)
    try:
        if platform.system().lower().startswith("win"):
            wmic_cs = subprocess.check_output(["wmic", "computersystem", "get", "manufacturer,model"], shell=True)
            lines = wmic_cs.decode(errors='ignore').strip().splitlines()
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 2:
                    system_make_model = ' '.join(parts)
    except Exception:
        pass

    device_serial_asset = platform.node()

    # ------------------------------------------------------------------
    # AUTO DETECT DRIVE INFO (best-effort for the specified drive)
    # ------------------------------------------------------------------
    drive_manufacturer_model = "Unknown"
    drive_serial_number = "Unknown"
    drive_capacity_interface = "Unknown"

    try:
        if platform.system().lower().startswith("win"):
            wmic_disk = subprocess.check_output(
                ["wmic", "diskdrive", "get", "Model,SerialNumber,Size,InterfaceType"], shell=True
            )
            lines = wmic_disk.decode(errors='ignore').strip().splitlines()
            if len(lines) > 1:
                # attempt to parse the first non-empty line after header
                for line in lines[1:]:
                    if line.strip():
                        first_drive_line = line.strip()
                        parts = [p for p in first_drive_line.split(" ") if p != ""]
                        if len(parts) >= 4:
                            drive_manufacturer_model = " ".join(parts[:-3])
                            drive_serial_number = parts[-3]
                            interface = parts[-2]
                            try:
                                size_bytes = int(parts[-1])
                                size_gb = size_bytes // (1024**3)
                                drive_capacity_interface = f"{size_gb}GB {interface}"
                            except:
                                drive_capacity_interface = interface
                        break
        else:
            # On linux/mac use psutil fallback
            parts = psutil.disk_partitions()
            if parts:
                # attempt to get a partition that matches the selected_drive mountpoint
                target = None
                if selected_drive:
                    for p in parts:
                        if os.path.abspath(p.mountpoint).lower() in os.path.abspath(selected_drive).lower():
                            target = p
                            break
                if target is None:
                    target = parts[0]
                usage = psutil.disk_usage(target.mountpoint)
                size_gb = usage.total // (1024**3)
                drive_capacity_interface = f"{size_gb}GB"
                drive_manufacturer_model = getattr(target, "device", str(target))
    except Exception:
        pass

    # ------------------------------------------------------------------
    # AUTO GENERATED CERTIFICATE DETAILS
    # ------------------------------------------------------------------
    certificate_number = str(uuid4())
    date_time_issue = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # decide output dir
    if output_dir:
        out_dir = os.path.abspath(output_dir)
    elif selected_drive:
        # create Certificates folder under the drive root
        # selected_drive might be something like "D:\\" or "/mnt/sda1"
        out_dir = os.path.join(selected_drive, "Certificates")
    else:
        out_dir = os.path.abspath(".")  # fallback to current dir

    os.makedirs(out_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # OUTPUT FILES
    # ------------------------------------------------------------------
    pdf_filename = os.path.join(out_dir, f"SecureWipe_Certificate_{certificate_number}.pdf")
    json_filename = os.path.join(out_dir, f"SecureWipe_Certificate_{certificate_number}.json")

    # ------------------------------------------------------------------
    # JSON DATA
    # ------------------------------------------------------------------
    certificate_data = {
        "certificate_number": certificate_number,
        "date_time_issue": date_time_issue,
        "company": {
            "name": company_name,
            "address": company_address,
            "contact": company_contact,
            "website": company_website
        },
        "software_version": software_version,
        "device": {
            "make_model": system_make_model,
            "serial_asset": device_serial_asset
        },
        "drive": {
            "manufacturer_model": drive_manufacturer_model,
            "serial_number": drive_serial_number,
            "capacity_interface": drive_capacity_interface
        },
        "files_deleted_count": len(deleted_files),
        "deleted_files_sample": deleted_files[:10],   # include small sample for traceability
        "verify_link": verify_link
    }

    # save JSON
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(certificate_data, f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------
    # BUILD PDF
    # ------------------------------------------------------------------
    pdf = SimpleDocTemplate(pdf_filename, pagesize=A4,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=TA_CENTER,
                                 fontSize=22, spaceAfter=12)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], alignment=TA_CENTER,
                                    fontSize=10, textColor=colors.grey)

    elements.append(Paragraph(f"<b>{company_name}</b>", styles['Heading2']))
    elements.append(Paragraph(f"{company_address} | {company_contact}", subtitle_style))
    elements.append(Paragraph(f"<a href='{company_website}' color='blue'>{company_website}</a>", subtitle_style))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("<b>Certificate of Secure Data Wipe</b>", title_style))
    elements.append(Paragraph(f"Certificate Number: {certificate_number}", subtitle_style))
    elements.append(Paragraph(f"Issued on: {date_time_issue}", subtitle_style))
    elements.append(Spacer(1, 14))

    # Table of details
    table_data = [
        ['Software Version', software_version],
        ['Device Make/Model', system_make_model],
        ['Device Serial / Asset Tag', device_serial_asset],
        ['Drive Manufacturer / Model', drive_manufacturer_model],
        ['Drive Serial Number', drive_serial_number],
        ['Drive Capacity & Interface', drive_capacity_interface],
        ['Files Deleted (count)', str(len(deleted_files))]
    ]

    table = Table(table_data, colWidths=[180, 320])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 18))

    elements.append(Paragraph("Authorized Signature: _______________________", styles['Normal']))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"Verify this certificate at: <a href='{verify_link}' color='blue'>{verify_link}</a>", subtitle_style))

    pdf.build(elements)

    return pdf_filename, json_filename


# Standalone test
if __name__ == "__main__":
    pdf, jsn = generate_certificate(selected_drive=".", deleted_files=["/tmp/a.txt", "/tmp/b.txt"])
    print("Generated:", pdf, jsn)
