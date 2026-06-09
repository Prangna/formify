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
    """Convert first page of PDF to base64 PNG using PyMuPDF — no poppler needed."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    mat = fitz.Matrix(2.0, 2.0)  # 2x zoom = ~144 DPI
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

SYSTEM_PROMPT = """You are an expert at converting scanned proforma images into clean, editable HTML forms.

When given an image of any proforma (report card, fee receipt, admit card, attendance sheet, leave form, certificate, or any school/office document), you must:

1. ANALYZE the image carefully — identify all:
   - Headings and subheadings
   - Labels and their corresponding input fields
   - Tables (preserve exact rows, columns, merged cells)
   - Checkboxes, dropdowns, or select fields
   - Static text that should not be editable
   - Logos or image placeholder areas

2. GENERATE a complete, standalone HTML file that:
   - Perfectly mirrors the visual layout of the original proforma
   - Uses a cream/off-white background (#fffff0) matching typical school proformas
   - Has a green border (#5a7a2e) around the page if the original has a border
   - Makes every blank line, empty box, or fill-in area into an editable <input> or <textarea>
   - Keeps all static text (labels, headings, instructions) as plain HTML text — NOT editable
   - Uses tables to replicate table layouts exactly
   - Uses Arial font throughout
   - Red color (#8b0000) for headings and section titles
   - Has a Print button (hidden during print) that calls window.print()
   - Is fully self-contained — no external CSS, no external JS, no CDN links
   - Works offline in any browser

3. HTML RULES:
   - All CSS must be inside a <style> tag in <head>
   - Input fields: border:none; border-bottom:1px solid #888; background:transparent; font-family:Arial; font-size:13px; outline:none;
   - Input fields on focus: border-bottom-color:#5a7a2e
   - Table cells that need input: put <input type="text"> inside the <td>
   - Large text areas: use <textarea> with resize:vertical
   - For grade/option fields with limited choices: use <select> with appropriate <option> values
   - Page width: max 680px centered on screen
   - Print media query: hide print button, keep all borders and inputs visible

4. OUTPUT RULES:
   - Output ONLY the complete HTML code
   - Start with <!DOCTYPE html>
   - No explanation, no markdown, no code fences
   - The HTML must be complete and functional as-is
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
                        "text": "Convert this proforma image into a complete editable HTML form. Follow all rules exactly. Output only the HTML code, nothing else."
                    }
                ]
            }
        ],
        max_tokens=8000,
        temperature=0.2
    )
    html = response.choices[0].message.content.strip()
    # Strip markdown code fences if model adds them
    if html.startswith("```"):
        lines = html.split("\n")
        lines = lines[1:]  # remove first ```html line
        if lines[-1].strip() == "```":
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
