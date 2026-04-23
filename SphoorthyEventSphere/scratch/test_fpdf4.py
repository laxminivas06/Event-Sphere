from fpdf import FPDF
pdf = FPDF()
pdf.add_page()
pdf.set_font("Arial", 'B', 18)
pdf.cell(10, 10, "Test Event 🎉")
try:
    pdf.output()
except Exception as e:
    import traceback
    traceback.print_exc()
