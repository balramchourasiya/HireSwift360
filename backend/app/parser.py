import re, io
from pathlib import Path
import fitz
from docx import Document

SKILL_DICTIONARY = ["c", "c++", "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django", "flask", "sql", "postgresql", "mysql", "mongodb", "aws", "azure", "docker", "kubernetes", "git", "linux", "embedded c", "microcontrollers", "rtos", "data structures", "html", "css", "machine learning", "nlp", "tensorflow", "pytorch", "excel", "power bi", "communication", "salesforce", "spi", "i2c", "uart", "can protocol", "arm", "stm32", "freertos", "jira", "agile", "rest api", "redis", "fastapi", "pandas", "numpy", "opencv", "matlab", "verilog", "vhdl", "testing", "debugging"]
SECTION_ALIASES = {"summary": ["summary", "profile", "objective", "professional summary"], "experience": ["experience", "work experience", "employment", "professional experience"], "education": ["education", "academic background", "qualification"], "projects": ["projects", "personal projects", "academic projects"], "certifications": ["certifications", "certificates", "licenses"], "skills": ["skills", "technical skills", "core competencies"]}

def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        with fitz.open(stream=content, filetype="pdf") as doc:
            return "\n".join(page.get_text("text") for page in doc)
    if suffix == ".docx":
        doc = Document(io.BytesIO(content))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows: parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    raise ValueError("Only PDF and DOCX files are supported")

def _sections(text):
    result = {key: "" for key in SECTION_ALIASES}
    current = None
    for line in text.splitlines():
        clean = line.strip().strip(" :|-•")
        normalized = clean.lower()
        heading = next((key for key, aliases in SECTION_ALIASES.items() if normalized in aliases), None)
        if heading: current = heading; continue
        if current and clean: result[current] += clean + "\n"
    return {k: v.strip()[:12000] for k, v in result.items()}

def parse_resume(text: str) -> dict:
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    email = (re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I) or [""])[0].lower()
    phone = (re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text) or [""])[0].strip()
    name = "Unknown candidate"
    for line in lines[:10]:
        if 1 < len(line.split()) <= 4 and len(line) < 80 and not re.search(r"@|\d|resume|curriculum|profile|linkedin|github", line, re.I): name = line[:180]; break
    lower = text.lower()
    evidence = {}
    for skill in SKILL_DICTIONARY:
        pattern = r"(?<![a-z0-9+#.])" + re.escape(skill) + r"(?![a-z0-9+#.])"
        match = re.search(pattern, lower)
        if match: evidence[skill] = text[max(0, match.start()-65):min(len(text), match.end()+100)].replace("\n", " ")
    skills = sorted(evidence.keys())
    exp = 0.0
    exp_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?(?:relevant\s+)?experience", lower)
    if exp_match: exp = float(exp_match.group(1))
    else:
        dates = re.findall(r"\b(20(?:0\d|1\d|2\d))\b", text)
        if len(dates) >= 2: exp = max(0.0, min(40.0, max(map(int, dates)) - min(map(int, dates))))
    years = re.findall(r"\b(20(?:0\d|1\d|2\d))\b", text)
    grad = max(map(int, years)) if years else None
    def number(pattern):
        m = re.search(pattern, lower)
        return float(m.group(1)) if m else None
    tenth = number(r"(?:10th|ssc|class x)[^\n%]{0,35}(\d{2}(?:\.\d+)?)\s*%")
    twelfth = number(r"(?:12th|hsc|class xii|puc)[^\n%]{0,35}(\d{2}(?:\.\d+)?)\s*%")
    cgpa = number(r"(?:cgpa|gpa)[^\d]{0,10}(\d(?:\.\d+)?)")
    location = ""
    for line in lines:
        if re.search(r"\b(bengaluru|bangalore|hyderabad|pune|chennai|mumbai|delhi|noida|gurugram|gurgaon|kolkata)\b", line, re.I): location = line[:160]; break
    sections = _sections(text)
    education = sections.get("education", "")[:3000]
    return {"full_name": name, "email": email, "phone": phone, "skills": skills, "skill_evidence": evidence,
            "sections": sections, "experience_years": exp, "graduation_year": grad, "tenth_percentage": tenth,
            "twelfth_percentage": twelfth, "cgpa": cgpa, "education": education, "location": location}
