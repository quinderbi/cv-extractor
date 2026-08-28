import io
import json
import re
import uuid
from xml.sax.saxutils import escape as _xml_escape

import streamlit as st

from src.pdf_parser import extract_text_from_pdf
from src.api_client import extract_cv_text

st.set_page_config(
    page_title="CV/Resume Extractor",
    page_icon=":memo:",
)

st.title("CV/Resume Extractor")
st.write(
    "Upload your CV/Resume in PDF format, then edit the extracted fields before downloading "
    "the final JSON, an ATS-friendly PDF, or a LaTeX (.tex) source file."
)

# ============================================================
# HELPER
# ============================================================

def parse_technologies(raw: str) -> list[str]:
    """Ubah string 'Python, React, SQL' menjadi list ['Python', 'React', 'SQL']."""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _non_empty_lines(text: str) -> list[str]:
    """Pecah teks multi-baris menjadi list baris yang tidak kosong."""
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


# ============================================================
# EXPORT: ATS-FRIENDLY PDF (reportlab)
# ============================================================

def build_ats_pdf(cv: dict) -> bytes:
    """Bangun PDF resume dengan layout ATS-friendly (satu kolom, teks polos,
    tanpa tabel/grafik) dari data CV, lalu kembalikan sebagai bytes."""
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

    def esc(text) -> str:
        return _xml_escape(str(text or ""))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        title=cv.get("personal_information", {}).get("full_name", "Resume"),
    )

    base = getSampleStyleSheet()
    name_style = ParagraphStyle(
        "NameStyle", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, alignment=TA_LEFT, spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "ContactStyle", parent=base["Normal"], fontSize=9.5, leading=12, spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "SectionStyle", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=11.5, leading=14, spaceBefore=10, spaceAfter=4,
    )
    subheading_style = ParagraphStyle(
        "SubheadingStyle", parent=base["Normal"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, spaceAfter=1,
    )
    meta_style = ParagraphStyle(
        "MetaStyle", parent=base["Normal"], fontName="Helvetica-Oblique",
        fontSize=9.5, leading=12, spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "BodyStyle", parent=base["Normal"], fontSize=10, leading=13, spaceAfter=2,
    )

    story = []

    # --- Header ---
    personal = cv.get("personal_information", {}) or {}
    story.append(Paragraph(esc(personal.get("full_name")), name_style))
    contact_parts = [
        esc(v) for v in [
            personal.get("email"), personal.get("phone"),
            personal.get("location"), personal.get("linkedin"),
        ] if v
    ]
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), contact_style))
    story.append(HRFlowable(width="100%", thickness=0.75, color="#000000", spaceAfter=4))

    def section_title(title: str):
        story.append(Paragraph(esc(title).upper(), section_style))

    # --- Experience ---
    experience = [e for e in cv.get("experience") or [] if e.get("position") or e.get("company")]
    if experience:
        section_title("Experience")
        for exp in experience:
            header = esc(exp.get("position"))
            if exp.get("company"):
                header += f", {esc(exp.get('company'))}"
            story.append(Paragraph(header, subheading_style))
            date_range = " - ".join(esc(d) for d in [exp.get("start_date"), exp.get("end_date")] if d)
            if date_range:
                story.append(Paragraph(date_range, meta_style))
            lines = _non_empty_lines(exp.get("description", ""))
            if len(lines) > 1:
                for line in lines:
                    story.append(Paragraph(f"- {esc(line)}", body_style))
            elif lines:
                story.append(Paragraph(esc(lines[0]), body_style))
            story.append(Spacer(1, 4))

    # --- Education ---
    education = [e for e in cv.get("education") or [] if e.get("institution") or e.get("degree")]
    if education:
        section_title("Education")
        for edu in education:
            header = esc(edu.get("degree"))
            if edu.get("institution"):
                header += f", {esc(edu.get('institution'))}" if header else esc(edu.get("institution"))
            story.append(Paragraph(header, subheading_style))
            date_range = " - ".join(esc(d) for d in [edu.get("start_date"), edu.get("end_date")] if d)
            if date_range:
                story.append(Paragraph(date_range, meta_style))
            lines = _non_empty_lines(edu.get("description", ""))
            for line in lines:
                story.append(Paragraph(f"- {esc(line)}", body_style))
            story.append(Spacer(1, 4))

    # --- Projects ---
    projects = [p for p in cv.get("projects") or [] if p.get("title")]
    if projects:
        section_title("Projects")
        for proj in projects:
            header = esc(proj.get("title"))
            story.append(Paragraph(header, subheading_style))
            tech = proj.get("technologies") or []
            if tech:
                story.append(Paragraph(esc(", ".join(tech)), meta_style))
            if proj.get("link"):
                story.append(Paragraph(esc(proj.get("link")), meta_style))
            lines = _non_empty_lines(proj.get("description", ""))
            for line in lines:
                story.append(Paragraph(f"- {esc(line)}", body_style))
            story.append(Spacer(1, 4))

    # --- Certifications ---
    certifications = [c for c in cv.get("certifications") or [] if c]
    if certifications:
        section_title("Certifications")
        story.append(Paragraph(esc(", ".join(certifications)), body_style))
        story.append(Spacer(1, 4))

    # --- Skills ---
    skills = [s for s in cv.get("skills") or [] if s]
    if skills:
        section_title("Skills")
        story.append(Paragraph(esc(", ".join(skills)), body_style))
        story.append(Spacer(1, 4))

    # --- Languages ---
    languages = [l for l in cv.get("languages") or [] if l]
    if languages:
        section_title("Languages")
        story.append(Paragraph(esc(", ".join(languages)), body_style))

    doc.build(story)
    return buffer.getvalue()


# ============================================================
# EXPORT: LATEX SOURCE (.tex)
# ============================================================

_LATEX_SPECIAL_CHARS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}
_LATEX_SPECIAL_RE = re.compile(
    "|".join(re.escape(ch) for ch in sorted(_LATEX_SPECIAL_CHARS, key=len, reverse=True))
)


def latex_escape(text) -> str:
    """Escape karakter spesial LaTeX supaya teks bebas aman disisipkan ke sumber .tex."""
    if not text:
        return ""
    return _LATEX_SPECIAL_RE.sub(lambda m: _LATEX_SPECIAL_CHARS[m.group()], str(text))


def build_latex_resume(cv: dict) -> str:
    """Bangun sumber LaTeX (.tex) ATS-friendly dari data CV."""
    lines: list[str] = []
    add = lines.append

    add(r"\documentclass[10pt]{article}")
    add(r"\usepackage[margin=0.75in]{geometry}")
    add(r"\usepackage{enumitem}")
    add(r"\usepackage{hyperref}")
    add(r"\usepackage{parskip}")
    add(r"\pagestyle{empty}")
    add(r"\setlist[itemize]{leftmargin=*, itemsep=1pt, topsep=2pt, parsep=0pt}")
    add(r"\begin{document}")
    add("")

    personal = cv.get("personal_information", {}) or {}
    add(r"{\LARGE \textbf{%s}} \\[2pt]" % latex_escape(personal.get("full_name")))
    contact_parts = []
    if personal.get("email"):
        contact_parts.append(latex_escape(personal["email"]))
    if personal.get("phone"):
        contact_parts.append(latex_escape(personal["phone"]))
    if personal.get("location"):
        contact_parts.append(latex_escape(personal["location"]))
    if personal.get("linkedin"):
        contact_parts.append(r"\url{%s}" % personal["linkedin"])
    if contact_parts:
        add(" \\textbar\\ ".join(contact_parts) + r" \\[4pt]")
    add(r"\hrule")
    add("")

    def section(title: str):
        add(r"\section*{%s}" % latex_escape(title.upper()))

    experience = [e for e in cv.get("experience") or [] if e.get("position") or e.get("company")]
    if experience:
        section("Experience")
        for exp in experience:
            header = latex_escape(exp.get("position"))
            if exp.get("company"):
                header += f", {latex_escape(exp.get('company'))}"
            date_range = " -- ".join(latex_escape(d) for d in [exp.get("start_date"), exp.get("end_date")] if d)
            add(r"\noindent\textbf{%s} \hfill \textit{%s} \\" % (header, date_range))
            desc_lines = _non_empty_lines(exp.get("description", ""))
            if desc_lines:
                add(r"\begin{itemize}")
                for line in desc_lines:
                    add(r"\item %s" % latex_escape(line))
                add(r"\end{itemize}")
            add("")

    education = [e for e in cv.get("education") or [] if e.get("institution") or e.get("degree")]
    if education:
        section("Education")
        for edu in education:
            header = latex_escape(edu.get("degree"))
            if edu.get("institution"):
                header = f"{header}, {latex_escape(edu.get('institution'))}" if header else latex_escape(edu.get("institution"))
            date_range = " -- ".join(latex_escape(d) for d in [edu.get("start_date"), edu.get("end_date")] if d)
            add(r"\noindent\textbf{%s} \hfill \textit{%s} \\" % (header, date_range))
            desc_lines = _non_empty_lines(edu.get("description", ""))
            if desc_lines:
                add(r"\begin{itemize}")
                for line in desc_lines:
                    add(r"\item %s" % latex_escape(line))
                add(r"\end{itemize}")
            add("")

    projects = [p for p in cv.get("projects") or [] if p.get("title")]
    if projects:
        section("Projects")
        for proj in projects:
            add(r"\noindent\textbf{%s} \\" % latex_escape(proj.get("title")))
            tech = proj.get("technologies") or []
            if tech:
                add(r"\textit{%s} \\" % latex_escape(", ".join(tech)))
            if proj.get("link"):
                add(r"\url{%s} \\" % proj["link"])
            desc_lines = _non_empty_lines(proj.get("description", ""))
            if desc_lines:
                add(r"\begin{itemize}")
                for line in desc_lines:
                    add(r"\item %s" % latex_escape(line))
                add(r"\end{itemize}")
            add("")

    certifications = [c for c in cv.get("certifications") or [] if c]
    if certifications:
        section("Certifications")
        add(latex_escape(", ".join(certifications)) + r" \\")
        add("")

    skills = [s for s in cv.get("skills") or [] if s]
    if skills:
        section("Skills")
        add(latex_escape(", ".join(skills)) + r" \\")
        add("")

    languages = [l for l in cv.get("languages") or [] if l]
    if languages:
        section("Languages")
        add(latex_escape(", ".join(languages)) + r" \\")
        add("")

    add(r"\end{document}")
    return "\n".join(lines)


# ============================================================
# INISIALISASI SESSION STATE
# ============================================================

# Field personal information (statis)
default_personal_fields = {
    "full_name": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin": "",
}
for key, default in default_personal_fields.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- Education ---
if "education_ids" not in st.session_state:
    st.session_state.education_ids = []

EDUCATION_FIELD_DEFAULTS = {
    "institution": "",
    "degree": "",
    "start_date": "",
    "end_date": "",
    "description": "",
}


def add_education_entry(data: dict | None = None):
    """Tambah satu entry education baru ke session_state."""
    entry_id = str(uuid.uuid4())
    st.session_state.education_ids.append(entry_id)
    data = data or {}
    for field, default in EDUCATION_FIELD_DEFAULTS.items():
        st.session_state[f"edu_{entry_id}_{field}"] = data.get(field, default)


def remove_education_entry(entry_id: str):
    """Hapus satu entry education dari session_state."""
    st.session_state.education_ids.remove(entry_id)
    for field in EDUCATION_FIELD_DEFAULTS:
        st.session_state.pop(f"edu_{entry_id}_{field}", None)


def clear_all_education():
    """Hapus semua entry education."""
    for entry_id in list(st.session_state.education_ids):
        remove_education_entry(entry_id)


# --- Experience ---
if "experience_ids" not in st.session_state:
    st.session_state.experience_ids = []

EXPERIENCE_FIELD_DEFAULTS = {
    "company": "",
    "position": "",
    "start_date": "",
    "end_date": "",
    "description": "",
}


def add_experience_entry(data: dict | None = None):
    """Tambah satu entry experience baru ke session_state."""
    entry_id = str(uuid.uuid4())
    st.session_state.experience_ids.append(entry_id)
    data = data or {}
    for field, default in EXPERIENCE_FIELD_DEFAULTS.items():
        st.session_state[f"exp_{entry_id}_{field}"] = data.get(field, default)


def remove_experience_entry(entry_id: str):
    """Hapus satu entry experience dari session_state."""
    st.session_state.experience_ids.remove(entry_id)
    for field in EXPERIENCE_FIELD_DEFAULTS:
        st.session_state.pop(f"exp_{entry_id}_{field}", None)


def clear_all_experience():
    """Hapus semua entry experience."""
    for entry_id in list(st.session_state.experience_ids):
        remove_experience_entry(entry_id)


# --- Projects ---
if "project_ids" not in st.session_state:
    st.session_state.project_ids = []

PROJECT_FIELD_DEFAULTS = {
    "title": "",
    "description": "",
    "technologies": "",  # disimpan sbg string "Python, React, SQL" di UI
    "link": "",
}


def add_project_entry(data: dict | None = None):
    """Tambah satu entry project baru ke session_state."""
    entry_id = str(uuid.uuid4())
    st.session_state.project_ids.append(entry_id)
    data = data or {}

    for field, default in PROJECT_FIELD_DEFAULTS.items():
        value = data.get(field, default)
        # Kalau technologies datang dari API sebagai list, gabung jadi string
        if field == "technologies" and isinstance(value, list):
            value = ", ".join(value)
        st.session_state[f"proj_{entry_id}_{field}"] = value


def remove_project_entry(entry_id: str):
    """Hapus satu entry project dari session_state."""
    st.session_state.project_ids.remove(entry_id)
    for field in PROJECT_FIELD_DEFAULTS:
        st.session_state.pop(f"proj_{entry_id}_{field}", None)


def clear_all_project():
    """Hapus semua entry project."""
    for entry_id in list(st.session_state.project_ids):
        remove_project_entry(entry_id)


# --- Certifications (list[str]) ---
if "certification_ids" not in st.session_state:
    st.session_state.certification_ids = []


def add_certification_entry(value: str = ""):
    """Tambah satu entry certification (string) baru ke session_state."""
    entry_id = str(uuid.uuid4())
    st.session_state.certification_ids.append(entry_id)
    st.session_state[f"cert_{entry_id}_value"] = value


def remove_certification_entry(entry_id: str):
    """Hapus satu entry certification dari session_state."""
    st.session_state.certification_ids.remove(entry_id)
    st.session_state.pop(f"cert_{entry_id}_value", None)


def clear_all_certification():
    """Hapus semua entry certification."""
    for entry_id in list(st.session_state.certification_ids):
        remove_certification_entry(entry_id)


# --- Skills (list[str]) ---
if "skill_ids" not in st.session_state:
    st.session_state.skill_ids = []


def add_skill_entry(value: str = ""):
    """Tambah satu entry skill (string) baru ke session_state."""
    entry_id = str(uuid.uuid4())
    st.session_state.skill_ids.append(entry_id)
    st.session_state[f"skill_{entry_id}_value"] = value


def remove_skill_entry(entry_id: str):
    """Hapus satu entry skill dari session_state."""
    st.session_state.skill_ids.remove(entry_id)
    st.session_state.pop(f"skill_{entry_id}_value", None)


def clear_all_skill():
    """Hapus semua entry skill."""
    for entry_id in list(st.session_state.skill_ids):
        remove_skill_entry(entry_id)


# --- Languages (list[str]) ---
if "language_ids" not in st.session_state:
    st.session_state.language_ids = []


def add_language_entry(value: str = ""):
    """Tambah satu entry language (string) baru ke session_state."""
    entry_id = str(uuid.uuid4())
    st.session_state.language_ids.append(entry_id)
    st.session_state[f"lang_{entry_id}_value"] = value


def remove_language_entry(entry_id: str):
    """Hapus satu entry language dari session_state."""
    st.session_state.language_ids.remove(entry_id)
    st.session_state.pop(f"lang_{entry_id}_value", None)


def clear_all_language():
    """Hapus semua entry language."""
    for entry_id in list(st.session_state.language_ids):
        remove_language_entry(entry_id)


# ============================================================
# UPLOAD & EKSTRAKSI
# ============================================================

with st.form("upload_form", clear_on_submit=True):
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
    submit_button = st.form_submit_button("Extract Information")

if uploaded_file is not None and submit_button:
    pdf_bytes = uploaded_file.getvalue()
    with st.spinner("Extracting information..."):
        try:
            extracted_text = extract_text_from_pdf(pdf_bytes)
            extracted_cv = extract_cv_text(extracted_text)

            # --- Personal information ---
            personal_info = extracted_cv.get("personal_information", {})
            st.session_state["full_name"] = personal_info.get("full_name", "")
            st.session_state["email"] = personal_info.get("email", "")
            st.session_state["phone"] = personal_info.get("phone", "")
            st.session_state["location"] = personal_info.get("location", "")
            st.session_state["linkedin"] = personal_info.get("linkedin", "")

            # --- Education (dinamis) ---
            clear_all_education()
            for edu in extracted_cv.get("education", []) or []:
                add_education_entry(edu)
            if not st.session_state.education_ids:
                add_education_entry()

            # --- Experience (dinamis) ---
            clear_all_experience()
            for exp in extracted_cv.get("experience", []) or []:
                add_experience_entry(exp)
            if not st.session_state.experience_ids:
                add_experience_entry()

            # --- Projects (dinamis) ---
            clear_all_project()
            for proj in extracted_cv.get("projects", []) or []:
                add_project_entry(proj)
            if not st.session_state.project_ids:
                add_project_entry()

            # --- Certifications (dinamis, list[str]) ---
            clear_all_certification()
            for cert in extracted_cv.get("certifications", []) or []:
                add_certification_entry(cert)
            if not st.session_state.certification_ids:
                add_certification_entry()

            # --- Skills (dinamis, list[str]) ---
            clear_all_skill()
            for skill in extracted_cv.get("skills", []) or []:
                add_skill_entry(skill)
            if not st.session_state.skill_ids:
                add_skill_entry()

            # --- Languages (dinamis, list[str]) ---
            clear_all_language()
            for lang in extracted_cv.get("languages", []) or []:
                add_language_entry(lang)
            if not st.session_state.language_ids:
                add_language_entry()

            st.success("Information extracted successfully.")
        except ValueError:
            st.error("Failed to extract text from the PDF. Please ensure the file is a valid PDF.")
        except RuntimeError:
            st.error("Converter Service is Not Available")

# ============================================================
# PERSONAL INFORMATION
# ============================================================

st.subheader("Personal Information")

st.text_input("Full Name", key="full_name")
column = st.columns(2)
column[0].text_input("Email", key="email")
column[1].text_input("Phone", key="phone")
column[0].text_input("Location", key="location")
column[1].text_input("LinkedIn URL", key="linkedin")

# ============================================================
# EDUCATION (DINAMIS)
# ============================================================

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Education")
    add_education = st.button("Add Education")

if not st.session_state.education_ids:
    st.caption("Belum ada data pendidikan. Klik tombol di atas untuk menambah.")

for idx, entry_id in enumerate(st.session_state.education_ids):
    with st.container(border=True):
        container = st.container(horizontal=True, vertical_alignment="center")

        container.markdown(f"**Education #{idx + 1}**", width="stretch")
        if container.button("Hapus", key=f"remove_edu_{entry_id}"):
            remove_education_entry(entry_id)
            st.rerun()

        edu_col = st.columns(2)
        edu_col[0].text_input("Institution", key=f"edu_{entry_id}_institution")
        edu_col[1].text_input("Degree", key=f"edu_{entry_id}_degree")
        date_col = st.columns(2)
        date_col[0].text_input("Start Date", key=f"edu_{entry_id}_start_date")
        date_col[1].text_input("End Date", key=f"edu_{entry_id}_end_date")
        st.text_area("Description", key=f"edu_{entry_id}_description")

if add_education:
    add_education_entry()
    st.rerun()

# ============================================================
# EXPERIENCE (DINAMIS)
# ============================================================

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Experience")
    add_experience = st.button("Add Experience")

if not st.session_state.experience_ids:
    st.caption("Belum ada data pengalaman kerja. Klik tombol di atas untuk menambah.")

for idx, entry_id in enumerate(st.session_state.experience_ids):
    with st.container(border=True):
        container = st.container(horizontal=True, vertical_alignment="center")

        container.markdown(f"**Experience #{idx + 1}**", width="stretch")
        if container.button("Hapus", key=f"remove_exp_{entry_id}"):
            remove_experience_entry(entry_id)
            st.rerun()

        exp_col = st.columns(2)
        exp_col[0].text_input("Company", key=f"exp_{entry_id}_company")
        exp_col[1].text_input("Position", key=f"exp_{entry_id}_position")
        date_col = st.columns(2)
        date_col[0].text_input("Start Date", key=f"exp_{entry_id}_start_date")
        date_col[1].text_input("End Date", key=f"exp_{entry_id}_end_date")
        st.text_area("Description", key=f"exp_{entry_id}_description")

if add_experience:
    add_experience_entry()
    st.rerun()

# ============================================================
# PROJECTS (DINAMIS)
# ============================================================

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Projects")
    add_project = st.button("Add Project")

if not st.session_state.project_ids:
    st.caption("Belum ada data project. Klik tombol di atas untuk menambah.")

for idx, entry_id in enumerate(st.session_state.project_ids):
    with st.container(border=True):
        container = st.container(horizontal=True, vertical_alignment="center")

        container.markdown(f"**Project #{idx + 1}**", width="stretch")
        if container.button("Hapus", key=f"remove_proj_{entry_id}"):
            remove_project_entry(entry_id)
            st.rerun()

        proj_col = st.columns(2)
        proj_col[0].text_input("Title", key=f"proj_{entry_id}_title")
        proj_col[1].text_input("Link", key=f"proj_{entry_id}_link")

        st.text_input(
            "Technologies (pisahkan dengan koma)",
            key=f"proj_{entry_id}_technologies",
            help="Contoh: Python, React, PostgreSQL",
        )

        st.text_area("Description", key=f"proj_{entry_id}_description")

if add_project:
    add_project_entry()
    st.rerun()

# ============================================================
# CERTIFICATIONS (DINAMIS, list[str])
# ============================================================

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Certifications")
    add_certification = st.button("Add Certification")

if not st.session_state.certification_ids:
    st.caption("Belum ada data sertifikasi. Klik tombol di atas untuk menambah.")
else:
    with st.container(border=True):
        for idx, entry_id in enumerate(st.session_state.certification_ids):
            row = st.container(horizontal=True, vertical_alignment="bottom")

            row.text_input(f"Certification {idx + 1}", key=f"cert_{entry_id}_value", width="stretch")
            if row.button("🗑️", key=f"remove_cert_{entry_id}"):
                remove_certification_entry(entry_id)
                st.rerun()

if add_certification:
    add_certification_entry()
    st.rerun()

# ============================================================
# SKILLS (DINAMIS, list[str])
# ============================================================

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Skills")
    add_skill = st.button("Add Skill")

if not st.session_state.skill_ids:
    st.caption("Belum ada data skill. Klik tombol di atas untuk menambah.")
else:
    with st.container(border=True):
        for idx, entry_id in enumerate(st.session_state.skill_ids):
            row = st.container(horizontal=True, vertical_alignment="bottom")

            row.text_input(f"Skill {idx + 1}", key=f"skill_{entry_id}_value", width="stretch")
            if row.button("🗑️", key=f"remove_skill_{entry_id}"):
                remove_skill_entry(entry_id)
                st.rerun()

if add_skill:
    add_skill_entry()
    st.rerun()

# ============================================================
# LANGUAGES (DINAMIS, list[str])
# ============================================================

with st.container(horizontal=True, vertical_alignment="center"):
    st.subheader("Languages")
    add_language = st.button("Add Language")

if not st.session_state.language_ids:
    st.caption("Belum ada data bahasa. Klik tombol di atas untuk menambah.")
else:
    with st.container(border=True):
        for idx, entry_id in enumerate(st.session_state.language_ids):
            row = st.container(horizontal=True, vertical_alignment="bottom")

            row.text_input(f"Language {idx + 1}", key=f"lang_{entry_id}_value", width="stretch")
            if row.button("🗑️", key=f"remove_lang_{entry_id}"):
                remove_language_entry(entry_id)
                st.rerun()

if add_language:
    add_language_entry()
    st.rerun()

# ============================================================
# SUSUN JSON FINAL & DOWNLOAD
# ============================================================

final_cv = {
    "personal_information": {
        "full_name": st.session_state["full_name"],
        "email": st.session_state["email"],
        "phone": st.session_state["phone"],
        "location": st.session_state["location"],
        "linkedin": st.session_state["linkedin"],
    },
    "education": [
        {
            "institution": st.session_state[f"edu_{entry_id}_institution"],
            "degree": st.session_state[f"edu_{entry_id}_degree"],
            "start_date": st.session_state[f"edu_{entry_id}_start_date"],
            "end_date": st.session_state[f"edu_{entry_id}_end_date"],
            "description": st.session_state[f"edu_{entry_id}_description"],
        }
        for entry_id in st.session_state.education_ids
    ],
    "experience": [
        {
            "company": st.session_state[f"exp_{entry_id}_company"],
            "position": st.session_state[f"exp_{entry_id}_position"],
            "start_date": st.session_state[f"exp_{entry_id}_start_date"],
            "end_date": st.session_state[f"exp_{entry_id}_end_date"],
            "description": st.session_state[f"exp_{entry_id}_description"],
        }
        for entry_id in st.session_state.experience_ids
    ],
    "projects": [
        {
            "title": st.session_state[f"proj_{entry_id}_title"],
            "description": st.session_state[f"proj_{entry_id}_description"],
            "technologies": parse_technologies(st.session_state[f"proj_{entry_id}_technologies"]),
            "link": st.session_state[f"proj_{entry_id}_link"],
        }
        for entry_id in st.session_state.project_ids
    ],
    "certifications": [
        st.session_state[f"cert_{entry_id}_value"]
        for entry_id in st.session_state.certification_ids
        if st.session_state[f"cert_{entry_id}_value"]
    ],
    "skills": [
        st.session_state[f"skill_{entry_id}_value"]
        for entry_id in st.session_state.skill_ids
        if st.session_state[f"skill_{entry_id}_value"]
    ],
    "languages": [
        st.session_state[f"lang_{entry_id}_value"]
        for entry_id in st.session_state.language_ids
        if st.session_state[f"lang_{entry_id}_value"]
    ],
}

st.divider()
st.subheader("Download")

base_filename = final_cv["personal_information"]["full_name"].strip().replace(" ", "_") or "cv_extracted"

download_col = st.columns(3)

download_col[0].download_button(
    label="Download JSON",
    data=json.dumps(final_cv, indent=2, ensure_ascii=False),
    file_name=f"{base_filename}.json",
    mime="application/json",
)

try:
    pdf_bytes = build_ats_pdf(final_cv)
    download_col[1].download_button(
        label="Download PDF (ATS)",
        data=pdf_bytes,
        file_name=f"{base_filename}.pdf",
        mime="application/pdf",
    )
except ImportError:
    download_col[1].button("Download PDF (ATS)", disabled=True, help="Package 'reportlab' belum terpasang.")
except Exception as exc:  # noqa: BLE001
    download_col[1].button("Download PDF (ATS)", disabled=True, help=f"Gagal membuat PDF: {exc}")

try:
    tex_source = build_latex_resume(final_cv)
    download_col[2].download_button(
        label="Download LaTeX (.tex)",
        data=tex_source,
        file_name=f"{base_filename}.tex",
        mime="text/x-tex",
    )
except Exception as exc:  # noqa: BLE001
    download_col[2].button("Download LaTeX (.tex)", disabled=True, help=f"Gagal membuat .tex: {exc}")