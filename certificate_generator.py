# certificate_generator.py (with robust JSON hash signing)
import subprocess, platform, json, psutil, os, hashlib
from uuid import uuid4
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
from cryptography.hazmat.backends import default_backend
import base64

# ------------------------------
# Persistent device_id helper
# ------------------------------
DEVICE_ID_FILE = os.path.join(os.path.abspath("."), "device_id.txt")

def get_device_id():
    if os.path.exists(DEVICE_ID_FILE):
        try:
            with open(DEVICE_ID_FILE, "r") as f:
                device_id = f.read().strip()
                if device_id:
                    return device_id
        except:
            pass
    device_id = str(uuid4())
    try:
        with open(DEVICE_ID_FILE, "w") as f:
            f.write(device_id)
    except:
        pass
    return device_id

# ------------------------------
# Signing function
# ------------------------------
def sign_certificate_data(data_bytes):
    """Sign certificate data using RSA private key."""
    with open("private_key.pem", "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend()
        )

    signature = private_key.sign(
        data_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")

# ------------------------------
# Certificate generation
# ------------------------------
def generate_certificate(selected_drive=None, deleted_files=None, output_dir=None,
                         operator_id="OP123", organization="SecureWipe Labs",
                         contact_info="+91 7453811860", wipe_log_text="sample log"):
    if deleted_files is None:
        deleted_files = []

    if selected_drive:
        selected_drive = os.path.abspath(selected_drive)

    company_name = "SecureWipe"
    company_address = "VIT-AP University MH-5 1018 717"
    company_contact = "+91 7453811860"
    company_website = "https://secure-wipe-xi.vercel.app/"
    software_version = "SecureWipe v2.0"
    base_verify_link = "https://secure-wipe-xi.vercel.app/verify/"
    sanitization_standard = "NIST SP 800-88 Purge – Secure Erase"

    # ------------------------------
    # Device info
    # ------------------------------
    system_make_model = f"{platform.node()} / {platform.system()} {platform.release()}"
    try:
        if platform.system().lower().startswith("win"):
            wmic_cs = subprocess.check_output(
                ["wmic", "computersystem", "get", "manufacturer,model"], shell=True
            )
            lines = wmic_cs.decode(errors='ignore').strip().splitlines()
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 2:
                    system_make_model = ' '.join(parts)
    except:
        pass

    device_serial_asset = platform.node()
    device_id = get_device_id()

    # Drive info
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
                for line in lines[1:]:
                    if line.strip():
                        parts = [p for p in line.strip().split(" ") if p != ""]
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
            parts = psutil.disk_partitions()
            if parts:
                target = parts[0]
                usage = psutil.disk_usage(target.mountpoint)
                size_gb = usage.total // (1024**3)
                drive_capacity_interface = f"{size_gb}GB"
                drive_manufacturer_model = getattr(target, "device", str(target))
    except:
        pass

    # Certificate info
    certificate_number = str(uuid4())
    date_time_issue = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    verify_link = base_verify_link + certificate_number
    hidden_areas = "HPA/DCO and SSD spare sectors addressed during purge"

    # ------------------------------
    # JSON data (before signing)
    # ------------------------------
    certificate_data = {
        "certificate_id": certificate_number,
        "issued_on": date_time_issue,
        "sanitization_standard": sanitization_standard,
        "device": {
            "make_model": system_make_model,
            "serial_asset": device_serial_asset,
            "device_id": device_id,
            "drive_model": drive_manufacturer_model,
            "drive_serial": drive_serial_number,
            "capacity_interface": drive_capacity_interface,
            "hidden_areas": hidden_areas
        },
        "operator": {
            "operator_id": operator_id,
            "organization": organization,
            "contact_info": contact_info
        },
        "files_deleted_count": len(deleted_files),
        "deleted_files_sample": deleted_files[:10],
        "verify_link": verify_link,
        "tool_version": software_version
    }

    # ------------------------------
    # Robust signing: hash JSON first
    # ------------------------------
    json_bytes = json.dumps(certificate_data, sort_keys=True).encode("utf-8")
    json_hash = hashlib.sha256(json_bytes).digest()  # hash the JSON
    signature = sign_certificate_data(json_hash)
    certificate_data["hash"] = hashlib.sha256((wipe_log_text + drive_serial_number + device_id).encode("utf-8")).hexdigest()
    certificate_data["digital_signature"] = signature

    # ------------------------------
    # Output files
    # ------------------------------
    if output_dir:
        out_dir = os.path.abspath(output_dir)
    elif selected_drive:
        out_dir = os.path.join(selected_drive, "Certificates")
    else:
        out_dir = os.path.abspath(".")
    os.makedirs(out_dir, exist_ok=True)

    pdf_filename = os.path.join(out_dir, f"SecureWipe_Certificate_{certificate_number}.pdf")
    json_filename = os.path.join(out_dir, f"SecureWipe_Certificate_{certificate_number}.json")

    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(certificate_data, f, indent=4, ensure_ascii=False)

    # ------------------------------
    # PDF build
    # ------------------------------
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
    elements.append(Paragraph(f"Standard: {sanitization_standard}", subtitle_style))
    elements.append(Spacer(1, 14))

    table_data = [
        ['Software Version', software_version],
        ['Operator ID', operator_id],
        ['Organization', organization],
        ['Contact Info', contact_info],
        ['Device Make/Model', system_make_model],
        ['Drive Model', drive_manufacturer_model],
        ['Drive Serial Number', drive_serial_number],
        ['Drive Capacity & Interface', drive_capacity_interface],
        ['Device ID', device_id],
        ['Hidden Areas', hidden_areas],
        ['Files Deleted (count)', str(len(deleted_files))],
        ['SHA-256 Log Hash', certificate_data["hash"][:32] + '...']
    ]

    table = Table(table_data, colWidths=[180, 320])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 18))

    elements.append(Paragraph("Digital Signature (Base64):", styles['Normal']))
    elements.append(Paragraph(signature[:64] + '...', styles['Normal']))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"Verify this certificate at: <a href='{verify_link}' color='blue'>{verify_link}</a>", subtitle_style))

    pdf.build(elements)
    return pdf_filename, json_filename

# Standalone test
if __name__ == "__main__":
    pdf, jsn = generate_certificate(selected_drive=".", deleted_files=["/tmp/a.txt", "/tmp/b.txt"])
    print("Generated:", pdf, jsn)
