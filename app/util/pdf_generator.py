from xhtml2pdf import pisa # library for converting HTML to PDF
from io import BytesIO  # temporary in-memory file for PDF output

def html_to_pdf(html: str) -> bytes: # convert HTML string to PDF bytes
    output = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=output) # generate PDF from HTML and write to output
    if pisa_status.err: # check for errors during PDF generation, Error handling was added after an AI-assisted code review
        raise Exception("Error generating PDF")
    return output.getvalue() # return the generated PDF as bytes

