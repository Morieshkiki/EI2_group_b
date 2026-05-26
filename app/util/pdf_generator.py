from xhtml2pdf import pisa
from io import BytesIO

def html_to_pdf(html: str) -> bytes:
    output = BytesIO()
    pisa_status = pisa.CreatePDF(src=html, dest=output)
    if pisa_status.err:
        raise Exception("Error generating PDF")
    return output.getvalue()