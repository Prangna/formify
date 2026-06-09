import os
import base64
import smtplib
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, render_template
from groq import Groq
from PIL import Image
import fitz  # PyMuPDF
import io

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def image_to_base64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def pdf_to_base64_image(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return image_to_base64(img)

def file_to_base64(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        return pdf_to_base64_image(file_bytes)
    else:
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        return image_to_base64(image)

SYSTEM_PROMPT = """You are an expert at converting scanned school proforma images into clean, editable HTML forms.

TASK: Convert the uploaded proforma image into a complete standalone HTML file that looks like the original and is fully editable by teachers.

=== CRITICAL RULES — FOLLOW EXACTLY ===

RULE 1 — EVERY EMPTY CELL/FIELD MUST BE EDITABLE:
- ANY table cell that is blank or empty in the image → put <input type="text" style="width:100%;border:none;border-bottom:1px solid #aaa;background:transparent;font-size:12px;font-family:Arial;outline:none;padding:2px;">
- ANY blank line after a label → <input type="text">
- ANY large empty box or text area → <textarea rows="2" style="width:100%;border:none;border-bottom:1px solid #aaa;background:transparent;font-size:12px;font-family:Arial;outline:none;resize:vertical;">
- Grade/class fields → <select> with options A,B,C,D,E
- Date fields → <input type="date">
- DO NOT leave any blank cell empty — every single blank cell needs an input field inside it

RULE 2 — TABLE STYLING:
- ALL table borders: border:1px solid #c8b96e (golden/olive color matching school proformas)
- Table background: #fffff0 (cream)
- Header cells (Activity, Class, Grade, Subject etc): background:#f5f0d8; color:#8b0000; font-weight:bold; text-align:center;
- NO red borders anywhere — use #c8b96e for all table borders
- border-collapse:collapse on all tables

RULE 3 — PAGE STYLING:
- Page background: #fffff0 (cream/off-white)
- Outer border of the full page: 4px solid #5a7a2e (green)
- Max width: 680px, centered on screen, padding: 24px
- Font: Arial throughout
- Headings/section titles: color:#8b0000 (dark red), bold

RULE 4 — STATIC TEXT (NOT EDITABLE):
- Column headers like "Activity", "Class", "Descriptive Indicators", "Grade" → plain text, NOT input
- Labels like "Name:", "Date:", "Place:" → plain text label, then input next to it
- Instructional text at bottom (footnotes, formulas) → plain text, NOT editable
- Pre-filled values like "IX", "X", "Delhi" → keep as plain text or pre-filled input value

RULE 5 — PRINT BUTTON:
- Add a green Print button at top: <button onclick="window.print()" style="...">Print</button>
- Hide it during print with @media print { .no-print { display:none; } }
- All inputs and borders must remain visible when printing

RULE 6 — OUTPUT FORMAT:
- Output ONLY raw HTML starting with <!DOCTYPE html>
- NO markdown, NO code fences, NO explanation
- Complete self-contained file, no external dependencies
- Must work offline in any browser
"""

def generate_form(base64_image: str) -> str:
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    },
                    {
                        "type": "text",
                        "text": """Convert this proforma image into a complete editable HTML form.

IMPORTANT REMINDERS:
1. Every blank/empty table cell MUST have an <input type="text"> inside it
2. Use border:1px solid #c8b96e for ALL table borders — NO red borders
3. Page must have green outer border (#5a7a2e) and cream background (#fffff0)
4. Output ONLY the HTML code — no markdown, no explanation, start with <!DOCTYPE html>"""
                    }
                ]
            }
        ],
        max_tokens=8000,
        temperature=0.1
    )
    html = response.choices[0].message.content.strip()
    # Strip markdown code fences if model adds them
    if html.startswith("```"):
        lines = html.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        html = "\n".join(lines).strip()
    return html

def send_feedback_email(name: str, email: str, message: str):
    mail_user = os.environ.get("MAIL_USER")
    mail_pass = os.environ.get("MAIL_PASS")
    if not mail_user or not mail_pass:
        return
    body = f"Formify Feedback\n\nFrom: {name}\nEmail: {email}\n\nMessage:\n{message}"
    msg = MIMEText(body)
    msg["Subject"] = f"Formify Feedback from {name}"
    msg["From"] = mail_user
    msg["To"] = "prathoreofficial@gmail.com"
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(mail_user, mail_pass)
            server.sendmail(mail_user, "prathoreofficial@gmail.com", msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Unsupported file type. Please upload PNG, JPG, WEBP or PDF."}), 400
    try:
        file_bytes = file.read()
        base64_image = file_to_base64(file_bytes, file.filename)
        html_form = generate_form(base64_image)
        return jsonify({"html": html_form})
    except Exception as e:
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500

@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json()
    send_feedback_email(
        data.get("name", "Anonymous"),
        data.get("email", ""),
        data.get("message", "")
    )
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
