from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
import os, csv, json
from werkzeug.utils import secure_filename
import google.generativeai as genai

app = Flask(__name__)
app.secret_key = "a_very_long_random_secret_123456789"

# === CONFIG ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY not set! Please set it before running the app.")

genai.configure(api_key=GEMINI_API_KEY)

RESUMES_FOLDER = os.path.join(app.root_path, "resumes")
USERS_CSV = os.path.join(app.root_path, "users.csv")
SUBMISSIONS_CSV = os.path.join(app.root_path, "submissions.csv")
ALLOWED_EXT = {".pdf"}

# Ensure folders & CSVs exist
os.makedirs(RESUMES_FOLDER, exist_ok=True)
if not os.path.exists(USERS_CSV):
    with open(USERS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Email", "Password", "IsAdmin"])
        writer.writerow(["admin@admin.com", "admin123", "1"])

if not os.path.exists(SUBMISSIONS_CSV):
    with open(SUBMISSIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Email", "Skills", "Filename", "AIScore", "BestRole", "AIFeedback"])

# === HELPERS ===
def allowed_file(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXT

def extract_text_from_pdf(filepath: str) -> str:
    try:
        import PyPDF2
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text.strip()
    except Exception as e:
        return f"Error extracting text: {e}"

def analyze_resume_with_ai(skills_text: str) -> tuple:
    """
    Send skills to Gemini API and get score & best role
    """
    try:
        model = genai.GenerativeModel("models/gemini-1.5-flash")
        prompt = f"""
        Analyze the following skills: {skills_text}
        - Give a score from 0 to 100 (higher = better fit for software engineering roles)
        - Suggest the most suitable job role
        Respond in JSON: {{"score": number, "best_role": "string"}}
        """
        response = model.generate_content(prompt)
        content = getattr(response, "text", response.parts[0].text)


        try:
            parsed = json.loads(content)
            score = int(parsed.get("score", 50))
            best_role = parsed.get("best_role", "Generalist")
        except json.JSONDecodeError:
            score = 50
            best_role = "Unknown"

        return score, best_role, content
    except Exception as e:
        return 0, "AI Processing Failed", f"AI Error: {e}"

# === ROUTES ===
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        if not email or not password:
            flash("Provide email and password", "danger")
            return redirect(url_for("signup"))

        with open(USERS_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Email") == email:
                    flash("Account already exists. Please login.", "warning")
                    return redirect(url_for("login"))

        with open(USERS_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([email, password, "0"])

        flash("Account created. Please login.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        found = False
        is_admin = False
        with open(USERS_CSV, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Email") == email and row.get("Password") == password:
                    found = True
                    is_admin = (row.get("IsAdmin") == "1")
                    break
        if found:
            session["user"] = email
            session["is_admin"] = bool(is_admin)
            flash("Logged in successfully", "success")
            if is_admin:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("upload"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user" not in session:
        flash("Please login to upload resume", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        skills = request.form.get("skills", "").strip()
        resume = request.files.get("resume")

        if not (name and email and skills and resume):
            flash("All fields required", "danger")
            return redirect(url_for("upload"))

        if not allowed_file(resume.filename):
            flash("Only PDF resumes are allowed", "danger")
            return redirect(url_for("upload"))

        filename = secure_filename(resume.filename)
        save_path = os.path.join(RESUMES_FOLDER, filename)

        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(save_path):
            filename = f"{base}_{counter}{ext}"
            save_path = os.path.join(RESUMES_FOLDER, filename)
            counter += 1

        resume.save(save_path)

        # AI Analysis
        score, best_role, raw_feedback = analyze_resume_with_ai(skills)

        with open(SUBMISSIONS_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([name, email, skills, filename, score, best_role, raw_feedback])

        flash(f"Resume uploaded! AI Score: {score}, Suggested Role: {best_role}", "success")
        return redirect(url_for("upload"))

    return render_template("upload.html")

@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"):
        flash("Admin access required", "danger")
        return redirect(url_for("login"))

    rows = []
    if os.path.exists(SUBMISSIONS_CSV):
        with open(SUBMISSIONS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    rows.sort(key=lambda r: int(r.get("AIScore", 0)), reverse=True)
    return render_template("admin.html", data=rows)

@app.route("/resumes/<path:filename>")
def serve_resume(filename):
    return send_from_directory(RESUMES_FOLDER, filename, as_attachment=False)

if __name__ == "__main__":
    app.run(debug=True)
