from fpdf import FPDF
pdf = FPDF(orientation='L', unit='mm', format='A5')
pdf.add_page()
pdf.set_fill_color(30, 27, 75)
pdf.rect(0, 0, 210, 40, 'F')
try:
    raw = pdf.output()
    print("Type of raw from pdf.output():", type(raw))
except Exception as e:
    print("Error:", e)
