from fpdf import FPDF
pdf = FPDF(orientation='L', unit='mm', format='A5')
pdf.add_page()
pdf.set_margins(10, 10, 10)
pdf.set_auto_page_break(False)
pdf.set_fill_color(30, 27, 75)
pdf.rect(0, 0, 210, 40, 'F')
raw = pdf.output(dest='S')
