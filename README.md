# Formify 📄✨
**Convert any school proforma image/PDF into an editable HTML form — instantly.**

Built by [Rathore's Academy](https://rathoresacademy.wordpress.com) — free tool for Indian teachers.

---

## What it does
Upload any scanned proforma (report card, fee receipt, admit card, attendance sheet, leave form) as an image or PDF → AI reads the layout → Generates a ready-to-fill, printable HTML form.

## Tech Stack
- Python 3.11 + Flask
- Groq API (llama-4-scout vision model)
- pdf2image + Pillow for PDF support
- Deployed on Render (free tier)

## Local Setup

```bash
git clone https://github.com/Prangna/formify
cd formify
pip install -r requirements.txt
```

Create a `.env` file:
```
GROQ_API_KEY=your_groq_api_key
MAIL_USER=your_gmail@gmail.com
MAIL_PASS=your_gmail_app_password
```

Install poppler (required for PDF support):
- **Windows**: Download from https://github.com/oschwartz10612/poppler-windows
- **Mac**: `brew install poppler`
- **Linux/Render**: `apt-get install -y poppler-utils`

Run:
```bash
python app.py
```

## Deploy on Render
1. Push to GitHub (repo name: formify)
2. New Web Service on Render → connect repo
3. Build command: `apt-get install -y poppler-utils && pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add environment variables: `GROQ_API_KEY`, `MAIL_USER`, `MAIL_PASS`

## Environment Variables
| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq API key |
| `MAIL_USER` | Gmail address for sending feedback |
| `MAIL_PASS` | Gmail App Password |
