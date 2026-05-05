import re
import json
import uuid

def extract_appointments(text):
    """Универсальная версия: работает и с таблицами |, и с обычным текстом"""
    patient_id = str(uuid.uuid4())
    appointments_json = {"patient_id": patient_id, "appointments": []}
    
    if not text:
        return appointments_json
    
    # Проверяем, есть ли таблицы с |
    if '|' in text:
        return _extract_from_table(text, patient_id)
    else:
        return _extract_from_plain_text(text, patient_id)


def _extract_from_plain_text(text, patient_id):
    """Извлекает из обычного текста (без |)"""
    appointments_json = {"patient_id": patient_id, "appointments": []}
    
    block_match = re.search(
        r'Назначения\s*\(исследования,?\s*консультации\)(.*?)(?=Листок нетрудоспособности)',
        text, re.DOTALL | re.IGNORECASE
    )
    
    if not block_match:
        return appointments_json
    
    block_text = block_match.group(1).strip()
    block_text = re.sub(r'^Лекарственные препараты[^\\n]*\n?', '', block_text, flags=re.IGNORECASE)
    block_text = re.sub(r'в\s*\n\s*(\d+)', r'в \1', block_text)  # Склеиваем переносы
    
    lines = [line.strip() for line in block_text.split('\n') if line.strip()]
    
    appointment_pattern = re.compile(
        r'(.*?)\s*[–-]\s*(\d{1,2}\.\d{2}\.\d{2,4})\s+в\s+(\d{1,2})(?::(\d{2}))?\s+в\s+(\d+)(?:\s*(?:кб|каб\.?|кабинете?|инете?))?\b',
        re.IGNORECASE
    )
    
    for line in lines:
        match = appointment_pattern.search(line)
        if match:
            appointments_json["appointments"].append({
                "description": match.group(1).strip(),
                "date": match.group(2),
                "time": f"{match.group(3)}:{match.group(4) or '00'}",
                "cabinet": match.group(5)
            })
    
    return appointments_json


def _extract_from_table(text, patient_id):
    """Извлекает из табличного формата (с |) — ваш оригинальный код"""
    appointments_json = {"patient_id": patient_id, "appointments": []}
    
    appointment_pattern = re.compile(
        r'Назначения \(исследования, консультации\).*?\n(\|.*\|.*\n(?!.*Листок нетрудоспособности.*\n)(\|.*\|\n)*)',
        re.DOTALL
    )
    
    details_pattern = re.compile(
        r'[–-]\s*(\d{1,2}\.\d{2}\.\d{2,4})\s+в\s+(\d{1,2})(?::(\d{2}))?\s+в\s+(\d+)',
        re.IGNORECASE
    )
    
    tables = appointment_pattern.findall(text)
    
    for table in tables:
        rows = table[0].strip().split("\n")
        for row in rows:
            cells = [cell.strip() for cell in row.split("|") if cell.strip()]
            if not cells or "Листок нетрудоспособности" in cells[0]:
                continue
            
            match = details_pattern.search(cells[0])
            if match:
                appointments_json["appointments"].append({
                    "description": cells[0].split('–')[0].strip(),
                    "date": match.group(1),
                    "time": f"{match.group(2)}:{match.group(3) or '00'}",
                    "cabinet": match.group(4).strip()
                })
    
    return appointments_json

def save_json(data, filename):
    json_str = json.dumps(data, ensure_ascii=False, indent=4)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(json_str)
    return json_str