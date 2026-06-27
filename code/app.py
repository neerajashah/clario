import streamlit as st
import base64
from pathlib import Path

st.set_page_config(
    page_title="Clario · Claim Verification",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⬡ Clario")
    st.caption("AI Claim Verification · v1.0")
    st.divider()

    st.markdown("**Navigation**")
    page = st.radio("", ["Demo Cases", "Live Verification", "About"], label_visibility="collapsed")

    st.divider()
    st.markdown("**Display**")
    theme = st.selectbox("Theme", ["Light", "Dark"], index=0)
    image_size = st.select_slider("Image size", options=["Small", "Medium", "Large"], value="Medium")
    show_raw_flags = st.toggle("Show all risk flags", value=True)

    st.divider()
    st.markdown("**About**")
    st.caption("Clario verifies insurance damage claims using Gemini 2.5 Flash — analysing conversation transcripts and photographic evidence in a single multimodal API call.")
    st.caption("Built by [Neeraja Shah](https://github.com/neerajashah) · HackerRank Orchestrate Hackathon, June 2026")

# ── Theme tokens ──────────────────────────────────────────────────────────────
if theme == "Dark":
    BG       = "#0F1923"
    SURFACE  = "#1E2D3D"
    BORDER   = "#2D3F52"
    TEXT     = "#E2E8F0"
    SUBTEXT  = "#94A3B8"
    NAV_BG   = "#0A1219"
else:
    BG       = "#F7F8FA"
    SURFACE  = "#FFFFFF"
    BORDER   = "#E2E8F0"
    TEXT     = "#111111"
    SUBTEXT  = "#64748B"
    NAV_BG   = "#0F1923"

IMG_MAX = {"Small": "160px", "Medium": "220px", "Large": "320px"}[image_size]

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
.stApp {{ background-color: {BG}; }}
.stDeployButton {{ display: none; }}
header[data-testid="stHeader"] {{ background: transparent; }}

.clario-nav {{
    background: {NAV_BG};
    padding: 13px 28px;
    display: flex;
    align-items: center;
    gap: 12px;
    margin: -1rem -1rem 1.5rem -1rem;
    border-bottom: 1px solid #1E2D3D;
}}
.clario-logo {{ color:#FFF; font-size:17px; font-weight:700; letter-spacing:-0.3px; }}
.clario-logo span {{ color:#3B82F6; }}
.clario-nav-tag {{
    background:#1E2D3D; color:#94A3B8; font-size:10px; font-weight:600;
    padding:3px 8px; border-radius:4px; letter-spacing:0.8px; text-transform:uppercase;
}}

.section-label {{
    font-size:10px; font-weight:700; color:#94A3B8;
    text-transform:uppercase; letter-spacing:1.2px; margin-bottom:8px;
}}

/* Conversation bubble */
.claim-header {{
    font-size:10px; font-weight:700; color:#94A3B8;
    text-transform:uppercase; letter-spacing:1px; margin-bottom:10px;
}}
.chat-wrap {{
    background:{SURFACE}; border:1px solid {BORDER};
    border-radius:10px; padding:14px 18px; margin-bottom:14px;
}}
.chat-line {{ display:flex; gap:8px; margin-bottom:8px; align-items:flex-start; }}
.chat-line:last-child {{ margin-bottom:0; }}
.chat-role {{
    font-size:10px; font-weight:700; min-width:64px;
    padding-top:2px; text-transform:uppercase; letter-spacing:0.5px;
}}
.chat-role.customer {{ color:#3B82F6; }}
.chat-role.support {{ color:#8B5CF6; }}
.chat-text {{ font-size:13px; color:{TEXT}; line-height:1.55; }}

/* Image strip */
.img-strip {{ display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; }}
.img-strip img {{
    height:{IMG_MAX}; width:auto; max-width:260px;
    border-radius:8px; border:1px solid {BORDER};
    object-fit:cover; flex-shrink:0;
}}

/* Verdict */
.verdict-supported  {{ background:#F0FDF4; border-left:4px solid #16A34A; border-radius:0 8px 8px 0; padding:14px 18px; margin-bottom:16px; }}
.verdict-contradicted {{ background:#FFF1F2; border-left:4px solid #DC2626; border-radius:0 8px 8px 0; padding:14px 18px; margin-bottom:16px; }}
.verdict-nei        {{ background:#FFFBEB; border-left:4px solid #D97706; border-radius:0 8px 8px 0; padding:14px 18px; margin-bottom:16px; }}
.verdict-label {{ font-size:10px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; margin-bottom:4px; }}
.verdict-supported  .verdict-label {{ color:#16A34A; }}
.verdict-contradicted .verdict-label {{ color:#DC2626; }}
.verdict-nei        .verdict-label {{ color:#D97706; }}
.verdict-text {{ font-size:13px; color:{TEXT}; line-height:1.6; }}

/* Metric card */
.metric-card {{
    background:{SURFACE}; border:1px solid {BORDER};
    border-radius:8px; padding:13px 14px; text-align:center;
}}
.m-label {{ font-size:10px; color:{SUBTEXT}; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }}
.m-value {{ font-size:21px; font-weight:700; color:{TEXT}; line-height:1; }}
.m-sub   {{ font-size:11px; color:{SUBTEXT}; margin-top:4px; }}

/* Info row */
.info-row {{
    background:{SURFACE}; border:1px solid {BORDER};
    border-radius:8px; padding:13px 18px;
    margin-bottom:10px; font-size:13px; color:{TEXT}; line-height:1.6;
}}
.info-row strong {{ color:{TEXT}; font-weight:600; }}

/* Flag pill */
.flag-pill {{
    display:inline-block; background:#FEF2F2; border:1px solid #FECACA;
    color:#DC2626; font-size:11px; font-weight:500;
    padding:3px 10px; border-radius:100px; margin:3px 4px 3px 0;
}}

/* Tab override */
.stTabs [data-baseweb="tab-list"] {{
    gap:0; background:{SURFACE}; border:1px solid {BORDER};
    border-radius:8px; padding:4px; margin-bottom:20px;
}}
.stTabs [data-baseweb="tab"] {{
    border-radius:6px; font-size:13px; font-weight:500; color:{SUBTEXT}; padding:7px 18px;
}}
.stTabs [aria-selected="true"] {{ background:#0F1923 !important; color:white !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ display:none; }}
.stTabs [data-baseweb="tab-border"] {{ display:none; }}
</style>
""", unsafe_allow_html=True)

# ── Nav bar ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="clario-nav">
    <div class="clario-logo">Clar<span>io</span></div>
    <div class="clario-nav-tag">AI Claim Verification</div>
</div>
""", unsafe_allow_html=True)

# ── Demo data ─────────────────────────────────────────────────────────────────
DEMO_CASES = [
    {
        "id": "case_049",
        "title": "Car — Rear Bumper",
        "object": "Car", "part": "Rear Bumper",
        "language": "Spanish", "lang_code": "es",
        "images": ["dataset/images/test/case_049/img_1.jpg"],
        "conversation": [
            ("Customer", "Quiero reportar daño en el parachoques trasero."),
            ("Support",  "¿Es solo el parachoques trasero?"),
            ("Customer", "Sí, el parachoques de atrás está dañado."),
            ("Support",  "¿Hay otro daño en el auto?"),
            ("Customer", "No, solo el parachoques trasero."),
        ],
        "claim_status": "contradicted",
        "evidence_standard_met": "No",
        "evidence_standard_met_reason": "No damage is visible on the claimed rear bumper in either image. One image has been digitally manipulated to include an instruction to approve the claim.",
        "risk_flags": ["possible_manipulation", "user_history_risk", "manual_review_required", "low_light_or_glare"],
        "issue_type": "none", "severity": "None",
        "fraud_risk_score": 65, "confidence_score": 85,
        "justification": "No damage is visible on the rear bumper in either submitted image. One image contains a digital manipulation instructing to approve the claim — detected and ignored.",
    },
    {
        "id": "case_006",
        "title": "Car — Hood (Hail Dents)",
        "object": "Car", "part": "Hood",
        "language": "English", "lang_code": "en",
        "images": ["dataset/images/test/case_006/img_1.jpg"],
        "conversation": [
            ("Customer", "The weather was bad last night and I had parked outside."),
            ("Customer", "Later a colleague mentioned my car looked different."),
            ("Customer", "The hood seems to have small hail dents — please review the hood for hail damage."),
        ],
        "claim_status": "not_enough_information",
        "evidence_standard_met": "No",
        "evidence_standard_met_reason": "The submitted image is too blurry and contains a watermark, preventing a clear assessment of the claimed hail dents on the car hood.",
        "risk_flags": ["user_history_risk", "blurry_image", "low_light_or_glare", "damage_not_visible", "manual_review_required"],
        "issue_type": "dent", "severity": "Unknown",
        "fraud_risk_score": 25, "confidence_score": 40,
        "justification": "The single submitted image is too blurry and obstructed by a watermark to confirm the presence, nature, or severity of the claimed hail dents on the car hood.",
    },
    {
        "id": "case_050",
        "title": "Laptop — Screen Crack",
        "object": "Laptop", "part": "Screen",
        "language": "Mixed (Chinese + English)", "lang_code": "zh-en",
        "images": ["dataset/images/test/case_050/img_1.jpg"],
        "conversation": [
            ("Customer", "Wo de laptop screen you crack."),
            ("Support",  "Are you reporting a cracked laptop screen?"),
            ("Customer", "Yes, laptop screen cracked. Qing bang wo check screen."),
            ("Support",  "Is the keyboard or body damaged too?"),
            ("Customer", "No, only screen crack."),
        ],
        "claim_status": "contradicted",
        "evidence_standard_met": "No",
        "evidence_standard_met_reason": "Neither image provides clear visual evidence of a cracked laptop screen. Image 1 shows no damage, and Image 2 is obstructed by a note with no visible damage on the exposed parts.",
        "risk_flags": ["cropped_or_obstructed"],
        "issue_type": "crack", "severity": "None",
        "fraud_risk_score": 30, "confidence_score": 90,
        "justification": "The submitted images do not show any cracks on the laptop screen. Image 1 clearly shows an undamaged screen, and Image 2, while partially obstructed by a note claiming damage, does not visually confirm any cracks.",
    },
    {
        "id": "case_052",
        "title": "Package — Crushed Corner",
        "object": "Package", "part": "Package Corner",
        "language": "English", "lang_code": "en",
        "images": ["dataset/images/test/case_052/img_2.jpg"],
        "conversation": [
            ("Customer", "The cardboard box corner is crushed."),
            ("Support",  "To confirm, cardboard box and not a mailer?"),
            ("Customer", "Correct, cardboard box corner."),
            ("Support",  "Is the product inside part of this claim?"),
            ("Customer", "No, package corner only."),
        ],
        "claim_status": "supported",
        "evidence_standard_met": "Yes",
        "evidence_standard_met_reason": "Image clearly shows a cardboard box with a crushed corner, directly supporting the claim and meeting evidence requirements for package exterior damage.",
        "risk_flags": ["user_history_risk", "wrong_object"],
        "issue_type": "crushed_packaging", "severity": "Medium",
        "fraud_risk_score": 15, "confidence_score": 95,
        "justification": "Image clearly shows a cardboard box with a visibly crushed bottom right corner, consistent with the customer's claim.",
    },
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def img_to_b64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return ""

def render_conversation(turns):
    lines = ""
    for role, text in turns:
        role_class = "customer" if role.lower() == "customer" else "support"
        lines += f'<div class="chat-line"><span class="chat-role {role_class}">{role}</span><span class="chat-text">{text}</span></div>'
    st.markdown(f'<div class="chat-wrap">{lines}</div>', unsafe_allow_html=True)

def render_images(paths):
    imgs_html = ""
    for p in paths:
        b64 = img_to_b64(p)
        if b64:
            imgs_html += f'<img src="data:image/jpeg;base64,{b64}" alt="Evidence image">'
    if imgs_html:
        st.markdown(f'<div class="img-strip">{imgs_html}</div>', unsafe_allow_html=True)

def render_verdict(case):
    status = case["claim_status"]
    css   = {"supported": "verdict-supported", "contradicted": "verdict-contradicted"}.get(status, "verdict-nei")
    label = {"supported": "✓ Claim Supported", "contradicted": "✕ Claim Contradicted"}.get(status, "⚠ Insufficient Evidence")
    st.markdown(f'<div class="{css}"><div class="verdict-label">{label}</div><div class="verdict-text">{case["justification"]}</div></div>', unsafe_allow_html=True)

def render_metrics(case):
    fraud, conf, sev, lang = case["fraud_risk_score"], case["confidence_score"], case["severity"], case["language"]
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="metric-card"><div class="m-label">Fraud Risk</div><div class="m-value">{fraud}<span style="font-size:12px;font-weight:400;color:#94A3B8">/100</span></div><div class="m-sub">{"High" if fraud>50 else "Moderate" if fraud>25 else "Low"}</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card"><div class="m-label">Confidence</div><div class="m-value">{conf}<span style="font-size:12px;font-weight:400;color:#94A3B8">%</span></div><div class="m-sub">Model certainty</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card"><div class="m-label">Severity</div><div class="m-value" style="font-size:15px;padding-top:5px">{sev}</div><div class="m-sub">Damage level</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="metric-card"><div class="m-label">Language</div><div class="m-value" style="font-size:13px;padding-top:5px">{lang}</div><div class="m-sub">Auto-detected</div></div>', unsafe_allow_html=True)

def render_details(case, show_flags):
    st.markdown(f"""<div class="info-row">
        <strong>Issue Type</strong> &nbsp;·&nbsp; {case['issue_type'].replace('_',' ').title()}
        &emsp;|&emsp; <strong>Part</strong> &nbsp;·&nbsp; {case['part']}
        &emsp;|&emsp; <strong>Evidence Met</strong> &nbsp;·&nbsp; {case['evidence_standard_met']}
    </div>""", unsafe_allow_html=True)
    st.markdown(f'<div class="info-row"><strong>Evidence Note</strong><br><span style="margin-top:4px;display:block">{case["evidence_standard_met_reason"]}</span></div>', unsafe_allow_html=True)
    flags = case.get("risk_flags", [])
    if flags and show_flags:
        pills = "".join([f'<span class="flag-pill">{f.replace("_"," ")}</span>' for f in flags])
        st.markdown(f'<div class="info-row"><strong>Risk Flags</strong><div style="margin-top:8px">{pills}</div></div>', unsafe_allow_html=True)

# ── Pages ─────────────────────────────────────────────────────────────────────
if page == "Demo Cases":
    left, right = st.columns([1, 2], gap="large")

    with left:
        st.markdown('<div class="section-label">Select a Case</div>', unsafe_allow_html=True)
        st.caption("Real results from Clario's pipeline on 44 HackerRank Orchestrate test claims.")
        st.markdown("")
        for i, c in enumerate(DEMO_CASES):
            dot = "🟢" if c["claim_status"]=="supported" else "🔴" if c["claim_status"]=="contradicted" else "🟡"
            if st.button(f"{dot}  {c['title']}", key=f"case_{i}", use_container_width=True):
                st.session_state["selected_case"] = i
                st.rerun()

    with right:
        case = DEMO_CASES[st.session_state.get("selected_case", 0)]
        st.markdown(f'<div class="section-label">Case · {case["id"].upper().replace("_"," ")} &nbsp;·&nbsp; {case["object"]} &nbsp;·&nbsp; {case["language"]}</div>', unsafe_allow_html=True)
        render_conversation(case["conversation"])
        render_images(case["images"])
        render_verdict(case)
        render_metrics(case)
        render_details(case, show_raw_flags)

elif page == "Live Verification":
    st.markdown('<div class="section-label">Live Verification</div>', unsafe_allow_html=True)
    st.caption("Run Clario on your own claim. Requires a free Gemini API key from [aistudio.google.com](https://aistudio.google.com).")
    st.markdown("")

    api_key_input = st.text_input("Gemini API Key", type="password", placeholder="AIza...",
        help="Used only for this request. Never stored.")

    col1, col2 = st.columns([1, 1], gap="large")
    with col1:
        st.markdown('<div class="section-label">Claim Details</div>', unsafe_allow_html=True)
        claim_text = st.text_area("Claim conversation", height=130,
            placeholder="Customer: My laptop screen has a crack...\nSupport: Can you describe where?")
        claim_object = st.selectbox("Object type", ["car", "laptop", "package"])
        user_id = st.text_input("User ID", value="user_demo")
        uploaded_files = st.file_uploader("Evidence images", type=["jpg","jpeg","png"], accept_multiple_files=True)
        verify_btn = st.button("Run Verification", type="primary", use_container_width=True)

    with col2:
        if uploaded_files:
            st.markdown('<div class="section-label">Uploaded Images</div>', unsafe_allow_html=True)
            imgs_html = ""
            for f in uploaded_files:
                b64 = base64.b64encode(f.read()).decode()
                imgs_html += f'<img src="data:image/jpeg;base64,{b64}" alt="{f.name}">'
            st.markdown(f'<div class="img-strip">{imgs_html}</div>', unsafe_allow_html=True)

    if verify_btn:
        if not api_key_input:
            st.error("Please enter your Gemini API key.")
        elif not claim_text:
            st.error("Please enter a claim description.")
        elif not uploaded_files:
            st.error("Please upload at least one evidence image.")
        else:
            import sys, os, tempfile
            sys.path.insert(0, str(Path(__file__).parent))
            from dotenv import load_dotenv
            load_dotenv()
            try:
                from data_loader import find_repo_root, ClaimRecord, ImageRef
                from agent import ClaimReviewAgent
                os.environ["GEMINI_API_KEY"] = api_key_input
                with st.spinner("Analysing claim with Gemini Vision..."):
                    repo_root = find_repo_root()
                    agent = ClaimReviewAgent.from_env(repo_root=repo_root)
                    agent.vision_client.api_key = api_key_input
                    import google.genai as genai
                    agent.vision_client._client = genai.Client(api_key=api_key_input)
                    tmp_dir = Path(tempfile.mkdtemp())
                    image_refs = []
                    for f in uploaded_files:
                        tmp_path = tmp_dir / f.name
                        tmp_path.write_bytes(f.read())
                        image_refs.append(ImageRef(image_id=Path(f.name).stem, relative_path=str(tmp_path), absolute_path=tmp_path))
                    claim = ClaimRecord(user_id=user_id, user_claim=claim_text, claim_object=claim_object, images=tuple(image_refs))
                    result = agent.review_claim(claim)
                live_case = {
                    "claim_status": result.get("claim_status","not_enough_information"),
                    "justification": result.get("claim_status_justification",""),
                    "fraud_risk_score": result.get("fraud_risk_score", 0),
                    "confidence_score": result.get("confidence_score", 0),
                    "severity": result.get("severity","unknown").capitalize(),
                    "language": result.get("claim_language","en"),
                    "part": result.get("object_part","—"),
                    "issue_type": result.get("issue_type","—"),
                    "evidence_standard_met": result.get("evidence_standard_met","—"),
                    "evidence_standard_met_reason": result.get("evidence_standard_met_reason",""),
                    "risk_flags": [f for f in str(result.get("risk_flags","")).split(";") if f and f.lower()!="none"],
                }
                render_verdict(live_case)
                render_metrics(live_case)
                render_details(live_case, True)
            except Exception as e:
                st.error(f"Verification failed: {e}")
                st.info("Quota error? Try again tomorrow or switch to the Demo tab.")

elif page == "About":
    st.markdown('<div class="section-label">About Clario</div>', unsafe_allow_html=True)
    st.markdown("")
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown(f"""<div class="info-row">
            <strong>What it does</strong><br><span style="display:block;margin-top:6px;color:{SUBTEXT}">
            Clario verifies insurance damage claims by jointly analysing customer conversation transcripts
            and photographic evidence in a single Gemini 2.5 Flash API call — returning a structured
            verdict with fraud risk score, confidence score, severity, and risk flags.
            </span></div>""", unsafe_allow_html=True)
        st.markdown(f"""<div class="info-row">
            <strong>Architecture</strong><br><span style="display:block;margin-top:6px;color:{SUBTEXT}">
            Single-call design — one Gemini Vision call per claim handles vision analysis, text reasoning,
            and structured JSON output simultaneously. No chaining, no extra latency.
            </span></div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="info-row">
            <strong>Key Features</strong><br>
            <span style="display:block;margin-top:6px;color:{SUBTEXT}">
            · Prompt injection detection<br>
            · Multilingual — English, Hindi, Hinglish, Spanish, Chinese-English<br>
            · Fraud risk scoring (0–100)<br>
            · Confidence scoring (0–100)<br>
            · 3 object types: car, laptop, package<br>
            · Validated on 44 real test cases
            </span></div>""", unsafe_allow_html=True)
        st.markdown(f"""<div class="info-row">
            <strong>Built by</strong><br><span style="display:block;margin-top:6px;color:{SUBTEXT}">
            Neeraja Shah · Final-year BTech AIML, DJSCE Mumbai<br>
            HackerRank Orchestrate Hackathon, June 2026<br>
            <a href="https://github.com/neerajashah" style="color:#3B82F6">github.com/neerajashah</a>
            </span></div>""", unsafe_allow_html=True)