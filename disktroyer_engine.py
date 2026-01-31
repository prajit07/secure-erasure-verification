# disktroyer_engine.py
"""
DisktroyerEngine: wipe engine (safe demo by default), certificate generation,
PDF creation with QR, compute PDF hash helper.

THIS FILE DOES NOT PERFORM REAL ERASURE UNLESS you set real_mode=True explicitly.
"""

import subprocess as sp
import threading
import time
import datetime
import hashlib
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox

# PDF / QR libs
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfgen import canvas
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

try:
    import qrcode
    QR_AVAILABLE = True
except Exception:
    QR_AVAILABLE = False

# For PDF overlay/merging
try:
    from PyPDF2 import PdfReader, PdfWriter
    PYPDF2_AVAILABLE = True
except Exception:
    PYPDF2_AVAILABLE = False


class DisktroyerEngine:
    def __init__(self, gui=None, demo_mode=True):
        """
        gui: reference to GUI object (to update status_text, progress_bar)
        demo_mode: when True, simulate wipes; when False and real_mode True -> run real commands
        """
        self.gui = gui
        self.demo_mode = demo_mode
        self.real_mode = False  # Must be explicitly set True to run destructive actions.
        self.selected_disk = None
        self.wipe_var = tk.IntVar(value=0) if gui else tk.IntVar(value=0)
        self.is_vm = True  # heuristic; can be updated by GUI if needed
        self.certificate_data = {}
        self.wipe_process = None
        self.wipe_thread = None

    # -------------------- Wipe orchestration -------------------- #
    def start_wiping(self):
        """Initiate wiping process (called from GUI)."""
        if self.gui:
            self.gui.show_progress_page()
            self.gui.progress_bar.start(10)

        # Prepare certificate metadata
        now = datetime.datetime.utcnow().isoformat()
        sel = self.gui.selected_disk if self.gui and self.gui.selected_disk else self.selected_disk
        if not sel:
            raise RuntimeError("No disk selected")

        self.selected_disk = sel  # sync
        self.certificate_data = {
            'device': f"/dev/{sel['name']}",
            'size': sel['size'],
            'type': sel['type'],
            'security_level': ['', 'Low', 'Medium', 'High'][self.wipe_var.get()],
            'environment': 'Virtual Machine' if self.is_vm else 'Physical Hardware',
            'start_time': now,
            'status': 'In Progress',
            'tool_version': 'Disktroyer-1.0',
            'compliance': 'NIST SP 800-88'
        }

        # Run wiping in separate thread
        self.wipe_thread = threading.Thread(target=self.perform_wipe, daemon=True)
        self.wipe_thread.start()

    def perform_wipe(self):
        try:
            self.update_status("Starting wipe procedure...")
            time.sleep(0.8)
            self.update_status("Unmounting partitions...")
            self.unmount_disk()
            time.sleep(0.6)

            cmd = self.get_wipe_command()
            self.update_status(f"Determined wipe command (simulated): {cmd}")
            self.update_status("⚠️ DO NOT INTERRUPT (demo mode) ⚠️")

            if self.demo_mode or not self.real_mode:
                self.simulate_wipe()
            else:
                self.execute_wipe_command(cmd)
            time.sleep(3)

            # finalize certificate
            self.certificate_data['end_time'] = datetime.datetime.utcnow().isoformat()
            self.certificate_data['status'] = 'Completed'

            start = datetime.datetime.fromisoformat(self.certificate_data['start_time'])
            end = datetime.datetime.fromisoformat(self.certificate_data['end_time'])
            self.certificate_data['duration'] = str(end - start)

            # Create PDF cert (without QR first), hash PDF, then we can anchor externally
            pdf_path = self.create_certificate_pdf(self.certificate_data, filename="certificate_noqr.pdf")
            pdf_hash = self.hash_file_sha256(pdf_path)
            self.certificate_data['pdf_hash'] = pdf_hash

            self.update_status(f"Certificate PDF created: {pdf_path}")
            self.update_status(f"Certificate PDF SHA256: {pdf_hash}")

            # At this point GUI or external script may call anchor_upload to store hash on-chain.
            # We'll embed a QR that points to verification URL placeholder (it can be updated post-anchoring).
            qr_path, verify_url = self.generate_qr_for_pdf_hash(pdf_hash, tx=None, output="qr.png")
            final_pdf = self.embed_qr_in_pdf(pdf_path, qr_path, output="certificate_final.pdf")

            self.certificate_data['pdf_path'] = os.path.abspath(final_pdf)
            self.update_status(f"Final PDF with QR: {final_pdf}")
            self.update_status("✅ Wipe simulation complete")

            # generate certificate_hash (hash of certificate data)
            cert_string = json.dumps(self.certificate_data, sort_keys=True)
            cert_hash = hashlib.sha256(cert_string.encode()).hexdigest()
            self.certificate_data['certificate_hash'] = cert_hash

            self.update_status(f"Certificate metadata hash: {cert_hash}")

            if self.gui:
                # Ensure GUI shows certificate page with the text
                self.gui.root.after(1000, lambda: self.complete_wipe_and_show_certificate())
        except Exception as e:
            self.certificate_data['status'] = 'Failed'
            self.certificate_data['error'] = str(e)
            self.update_status(f"❌ Error during wipe: {e}")
            if self.gui:
                self.gui.root.after(1000, lambda: self.complete_wipe_and_show_certificate())

    def complete_wipe_and_show_certificate(self):
        if self.gui:
            self.gui.progress_bar.stop()
            self.gui.show_certificate_page()
            # insert certificate text (read-only)
            self.gui.cert_info_text.config(state="normal")
            self.gui.cert_info_text.delete(1.0, tk.END)
            self.gui.cert_info_text.insert(tk.END, self.generate_certificate_text())
            self.gui.cert_info_text.config(state="disabled")

    # -------------------- Helpers -------------------- #
    def get_wipe_command(self):
        disk_name = self.selected_disk['name']
        disk_type = self.selected_disk['type'].lower()
        level = self.wipe_var.get()
        # For demo we return suggested command (not executed unless real_mode=True)
        if self.is_vm:
            if level == 1:
                return f"shred -v -n 1 -z /dev/{disk_name}"
            elif level == 2:
                return f"shred -v -n 3 -z /dev/{disk_name}"
            else:
                return f"shred -v -n 8 -z /dev/{disk_name}"
        else:
            if 'nvme' in disk_type:
                if level == 1:
                    return f"nvme format /dev/{disk_name} --ses=1"
                elif level == 2:
                    return f"nvme format /dev/{disk_name} --ses=2"
                else:
                    return f"nvme sanitize /dev/{disk_name} --ause"
            elif 'ssd' in disk_type:
                if level >= 2:
                    return f"hdparm --user-master u --security-set-pass p /dev/{disk_name} && hdparm --user-master u --security-erase-enhanced p /dev/{disk_name}"
                else:
                    return f"hdparm --user-master u --security-set-pass p /dev/{disk_name} && hdparm --user-master u --security-erase p /dev/{disk_name}"
            else:
                if level == 1:
                    return f"dd if=/dev/urandom of=/dev/{disk_name} bs=1M status=progress"
                elif level == 2:
                    return f"shred -v -n 8 -z /dev/{disk_name}"
                else:
                    return f"shred -v -n 35 -z /dev/{disk_name}"

    def unmount_disk(self):
        """Attempt to unmount partitions; fall back to lazy unmount."""
        try:
            disk_name = self.selected_disk['name']
            result = sp.run(['grep', f'/dev/{disk_name}', '/proc/mounts'], capture_output=True, text=True)
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    if not line:
                        continue
                    partition = line.split()[0]
                    self.update_status(f"Unmounting {partition}...")
                    try:
                        sp.run(['umount', partition], check=True, timeout=30)
                        self.update_status(f"✅ Unmounted {partition}")
                    except sp.CalledProcessError:
                        # fallback to lazy unmount (may cause data loss)
                        sp.run(['umount', '-l', partition], timeout=30)
                        self.update_status(f"⚠️ Force (lazy) unmounted {partition} (data loss possible)")
            else:
                self.update_status("No mounted partitions found")
        except Exception as e:
            self.update_status(f"Warning: Could not unmount: {e}")

    def simulate_wipe(self):
        """Simulated wiping that adapts by level"""
        level = self.wipe_var.get()
        if level == 1:
            num_passes = 1
        elif level == 2:
            num_passes = 3
        else:
            num_passes = 7

        for p in range(1, num_passes + 1):
            self.update_status(f"Pass {p}/{num_passes}: Overwriting data...")
            for progress in range(0, 101, 20):
                time.sleep(0.3 + 0.05 * level)  # slightly slower for higher level
                self.update_status(f"  Progress: {progress}%")

    def execute_wipe_command(self, cmd):
        """Execute actual wipe. Only runs if real_mode=True (dangerous)."""
        if not self.real_mode:
            raise RuntimeError("Attempt to run destructive command while real_mode is False")
        # split command safely and run with sudo if required (not implemented here)
        process = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT, universal_newlines=True)
        self.wipe_process = process
        for line in iter(process.stdout.readline, ''):
            if line:
                self.update_status(line.strip())
        process.wait()
        if process.returncode != 0:
            raise sp.CalledProcessError(process.returncode, cmd)

    # -------------------- Certificate / PDF / QR helpers -------------------- #
    def generate_certificate_text(self):
        cert = self.certificate_data
        text = []
        text.append("SECURE DATA WIPING CERTIFICATE\n" + "=" * 50 + "\n\n")
        for k, v in cert.items():
            text.append(f"{k}: {v}\n")
        return "".join(text)

    def create_certificate_pdf(self, cert_dict, filename="certificate.pdf"):
        """Create a simple PDF containing certificate fields (no QR)."""
        if not PDF_AVAILABLE:
            raise RuntimeError("reportlab not available")
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(filename, pagesize=letter)
        story = []
        story.append(Paragraph("SECURE DATA WIPING CERTIFICATE", styles['Title']))
        story.append(Spacer(1, 12))
        for k, v in cert_dict.items():
            story.append(Paragraph(f"<b>{k}:</b> {v}", styles['Normal']))
            story.append(Spacer(1, 6))
        doc.build(story)
        return filename

    def hash_file_sha256(self, path):
        """Return hex sha256 of file contents."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()

    def generate_qr_for_pdf_hash(self, pdf_hash, tx=None, output="qr.png"):
        """Generate a QR that points to a verification URL containing the hash (and tx if present)."""
        # Simple verify URL pattern; in production change to your verification server
        verify_url = f"http://localhost:5000/verify/{pdf_hash}"
        if tx:
            verify_url += f"?tx={tx}"
        if not QR_AVAILABLE:
            raise RuntimeError("qrcode not installed")
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(verify_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(output)
        return output, verify_url

    def embed_qr_in_pdf(self, pdf_path, qr_path, output="certificate_final.pdf"):
        """Overlay QR image onto the last page of the PDF and save as output."""
        if not PYPDF2_AVAILABLE:
            raise RuntimeError("PyPDF2 not installed")
        # create a single-page PDF with QR at chosen position
        overlay_pdf = "qr_overlay.pdf"
        c = canvas.Canvas(overlay_pdf, pagesize=letter)
        # place QR at bottom-right
        c.drawImage(qr_path, 430, 40, width=120, height=120)
        c.save()

        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        overlay_page = PdfReader(overlay_pdf).pages[0]

        for i, p in enumerate(reader.pages):
            if i == len(reader.pages) - 1:
                p.merge_page(overlay_page)
            writer.add_page(p)

        with open(output, "wb") as f:
            writer.write(f)

        # cleanup overlay
        try:
            os.remove(overlay_pdf)
        except Exception:
            pass
        return output

    # -------------------- UI update helper -------------------- #
    def update_status(self, message):
        """If GUI provided, append messages to status_text; otherwise print."""
        ts = datetime.datetime.utcnow().strftime("%H:%M:%S")
        msg = f"[{ts}] {message}"
        print(msg)
        if self.gui and hasattr(self.gui, "status_text"):
            def append():
                self.gui.status_text.insert(tk.END, msg + "\n")
                self.gui.status_text.see(tk.END)
            self.gui.root.after(0, append)

