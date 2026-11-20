import re
import pymupdf as fitz

def extract_questions_from_pdf(pdf_path):
    """
    Extracts MCQ questions, options (A-D), and answer keys from a PDF question paper
    using PyMuPDF with regex pattern matching.
    """
    extracted_questions = []
    full_text = ""

    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            full_text += page.get_text() + "\n"
        doc.close()
    except Exception as e:
        return [], f"PyMuPDF failed to read PDF: {str(e)}"

    if not full_text.strip():
        return [], "No readable text found in PDF. Scanned document might require OCR."

    # Normalize lines
    lines = [line.strip() for line in full_text.splitlines() if line.strip()]

    # Pattern to match questions like:
    # 1. Question text here?
    # Q1. Question text here?
    # 1) Question text here?
    q_pattern = re.compile(r'^(?:Q(?:uestion)?\s*)?(\d+)[\.\)]\s*(.*)', re.IGNORECASE)
    opt_pattern = re.compile(r'^\(?([A-Da-d])\)?[.\-\s]+(.*)')
    ans_pattern = re.compile(r'^(?:Ans(?:wer)?|Correct\s*Option)[\s:\-]+([A-Da-d])', re.IGNORECASE)

    current_q = None

    for line in lines:
        q_match = q_pattern.match(line)
        opt_match = opt_pattern.match(line)
        ans_match = ans_pattern.match(line)

        if q_match and not opt_match:
            # New question detected
            if current_q and current_q.get('text') and current_q.get('options'):
                extracted_questions.append(current_q)
            q_num = q_match.group(1)
            q_text = q_match.group(2).strip()
            current_q = {
                'number': q_num,
                'text': q_text,
                'options': {},
                'correct_answer': None,
                'marks': 1
            }
        elif ans_match and current_q:
            current_q['correct_answer'] = ans_match.group(1).upper()
        elif opt_match and current_q:
            opt_letter = opt_match.group(1).upper()
            opt_text = opt_match.group(2).strip()
            current_q['options'][opt_letter] = opt_text
        elif current_q:
            # Continuation line
            if not current_q['options']:
                current_q['text'] += " " + line
            else:
                last_opt = sorted(current_q['options'].keys())[-1]
                current_q['options'][last_opt] += " " + line

    if current_q and current_q.get('text') and current_q.get('options'):
        extracted_questions.append(current_q)

    # Sort questions by extracted number to strictly preserve PDF question order
    try:
        extracted_questions.sort(
            key=lambda x: int(x.get('number', 0)) if str(x.get('number', '')).isdigit() else 999999
        )
    except Exception:
        pass

    return extracted_questions, None
