from pypdf import PdfReader

def text_extractor_pdf(file_path):
    pdf_file = PdfReader(file_path)
    pdf_text = ''
    for pages in pdf_file.pages:
        pdf_text += pages.extract_text()

    return pdf_text
