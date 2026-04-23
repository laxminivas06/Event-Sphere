from fpdf import FPDF
import tempfile, os
pdf = FPDF(orientation='L', unit='mm', format='A5')
pdf.add_page()
pdf.set_font("Arial", 'B', 18)
pdf.cell(130, 12, "Test Event", ln=False)

import qrcode
from io import BytesIO
qr = qrcode.QRCode(version=1, box_size=10, border=4)
qr.add_data("Test")
qr.make(fit=True)
img = qr.make_image(fill_color='black', back_color='white')
buf = BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
tmp.write(buf.read()); tmp.close()
pdf.image(tmp.name, x=155, y=42, w=50, h=50)
os.unlink(tmp.name)

try:
    raw = pdf.output(dest='S')
except Exception as e:
    import traceback
    traceback.print_exc()
