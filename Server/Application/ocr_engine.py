# -*- coding: utf-8 -*-
import os
from pypdf import PdfReader, PdfWriter  # <-- замена
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTRect, LTFigure
import pdfplumber
from pdf2image import convert_from_path
from PIL import Image

def text_extraction(element):
    line_text = element.get_text()
    line_formats = []
    for text_line in element:
        if isinstance(text_line, LTTextContainer):
            for character in text_line:
                if isinstance(character, LTChar):
                    line_formats.extend([character.fontname, character.size])
    return (line_text, list(set(line_formats)))

def crop_image(element, pageObj):
    [image_left, image_top, image_right, image_bottom] = [
        element.x0, element.y0, element.x1, element.y1
    ]
    pageObj.mediabox.lower_left = (image_left, image_bottom)
    pageObj.mediabox.upper_right = (image_right, image_top)
    cropped_pdf_writer = PdfWriter()  # <-- pypdf
    cropped_pdf_writer.add_page(pageObj)
    with open('cropped_image.pdf', 'wb') as f:
        cropped_pdf_writer.write(f)

def convert_to_images(input_file):
    images = convert_from_path(input_file, dpi=200)
    image = images[0]
    output_file = "PDF_image.png"
    image.save(output_file, "PNG")
    return output_file

def image_to_text(image_path):
    import pytesseract
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang='rus')

def extract_table(pdf_path, page_num, table_num):
    with pdfplumber.open(pdf_path) as pdf:
        table_page = pdf.pages[page_num]
        return table_page.extract_tables()[table_num]

def table_converter(table):
    table_string = ''
    for row_num in range(len(table)):
        row = table[row_num]
        cleaned_row = [
            item.replace('\n', ' ') if item is not None and '\n' in item 
            else 'None' if item is None else item 
            for item in row
        ]
        table_string += ('|' + '|'.join(cleaned_row) + '|' + '\n')
    return table_string[:-1]

def process_pdf(pdf_path, target_page=2):
    """Обрабатывает PDF и возвращает текст со страницы с назначениями"""
    pdfFileObj = open(pdf_path, 'rb')
    pdfReaded = PdfReader(pdfFileObj)  # <-- pypdf
    
    text_per_page = {}
    
    for pagenum, page in enumerate(extract_pages(pdf_path)):
        pageObj = pdfReaded.pages[pagenum]
        page_text = []
        line_format = []
        text_from_images = []
        text_from_tables = []
        page_content = []
        table_num = 0
        first_element = True
        table_extraction_flag = False
        
        with pdfplumber.open(pdf_path) as pdf:
            page_tables = pdf.pages[pagenum]
            tables = page_tables.find_tables()
        
        page_elements = [(element.y1, element) for element in page._objs]
        page_elements.sort(key=lambda a: a[0], reverse=True)
        
        for i, component in enumerate(page_elements):
            pos = component[0]
            element = component[1]
            
            if isinstance(element, LTTextContainer):
                if not table_extraction_flag:
                    line_text, format_per_line = text_extraction(element)
                    page_text.append(line_text)
                    line_format.append(format_per_line)
                    page_content.append(line_text)
            
            if isinstance(element, LTFigure):
                crop_image(element, pageObj)
                convert_to_images('cropped_image.pdf')
                image_text = image_to_text('PDF_image.png')
                text_from_images.append(image_text)
                page_content.append(image_text)
                page_text.append('image')
                line_format.append('image')
            
            if isinstance(element, LTRect):
                if first_element and (table_num + 1) <= len(tables):
                    lower_side = page.bbox[3] - tables[table_num].bbox[3]
                    upper_side = element.y1
                    table = extract_table(pdf_path, pagenum, table_num)
                    table_string = table_converter(table)
                    text_from_tables.append(table_string)
                    page_content.append(table_string)
                    table_extraction_flag = True
                    first_element = False
                    page_text.append('table')
                    line_format.append('table')
                
                if element.y0 >= lower_side and element.y1 <= upper_side:
                    pass
                elif i + 1 < len(page_elements) and not isinstance(page_elements[i + 1][1], LTRect):
                    table_extraction_flag = False
                    first_element = True
                    table_num += 1
        
        dctkey = f'Page_{pagenum}'
        text_per_page[dctkey] = [page_text, line_format, text_from_images, text_from_tables, page_content]
    
    pdfFileObj.close()
    
    # Cleanup temp files
    for f in ['cropped_image.pdf', 'PDF_image.png']:
        if os.path.exists(f):
            os.remove(f)
    
    page_key = f'Page_{target_page}'
    if page_key in text_per_page:
        return ''.join(text_per_page[page_key][4])
    return ''