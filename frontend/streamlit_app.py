import os

import requests
import streamlit as st

DEFAULT_API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
REQUEST_TIMEOUT = 180
MAX_FILES = 10  # mirrors MAX_FILES_PER_UPLOAD in app/config.py
MAX_FILE_MB = 10  # mirrors MAX_FILE_SIZE in app/config.py

st.set_page_config(
    page_title="Document Insight",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Visual design ----------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

    :root {
        --bg: #080d18;
        --panel: #101a2b;
        --panel-soft: #121f34;
        --line: rgba(139, 170, 220, 0.16);
        --text: #eef4ff;
        --muted: #8fa2c2;
        --blue: #4f8cff;
        --blue-bright: #6ba3ff;
        --cyan: #51d5ee;
    }

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(ellipse at 12% 0%, rgba(36, 91, 180, 0.20), transparent 34%),
            radial-gradient(ellipse at 90% 8%, rgba(29, 129, 173, 0.10), transparent 28%),
            var(--bg);
        color: var(--text);
    }

    [data-testid="stHeader"] {
        background: rgba(8, 13, 24, 0.72);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1627 0%, #0a1220 100%);
        border-right: 1px solid var(--line);
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.5rem;
    }

    .brand-lockup {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 0 0 1.8rem 0;
    }

    .brand-mark {
        width: 42px;
        height: 42px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 13px;
        color: white;
        font-size: 23px;
        font-weight: 700;
        background: linear-gradient(135deg, #397bff, #31c6e8);
        box-shadow: 0 8px 26px rgba(55, 126, 255, 0.28);
    }

    .brand-name {
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 700;
        font-size: 1.02rem;
        color: #f4f7ff;
        letter-spacing: -0.3px;
        line-height: 1.2;
    }

    .brand-subtitle {
        font-size: 0.74rem;
        color: var(--muted);
        margin-top: 3px;
    }

    .eyebrow {
        text-transform: uppercase;
        letter-spacing: 0.16em;
        color: #77aaff;
        font-size: 0.72rem;
        font-weight: 700;
        margin-bottom: 0.55rem;
    }

    .hero-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: clamp(2rem, 4vw, 3.05rem);
        line-height: 1.08;
        font-weight: 700;
        letter-spacing: -1.8px;
        color: #f3f7ff;
        margin: 0 0 0.8rem 0;
    }

    .hero-title span {
        background: linear-gradient(90deg, #6ba3ff 0%, #56d8ee 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .hero-copy {
        color: #9aacc9;
        font-size: 1.02rem;
        line-height: 1.65;
        max-width: 760px;
        margin-bottom: 1.5rem;
    }

    .section-heading {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.2rem;
        font-weight: 600;
        color: #eef4ff;
        letter-spacing: -0.35px;
        margin-bottom: 0.2rem;
    }

    .section-copy {
        color: var(--muted);
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }

    .surface-card {
        background: linear-gradient(145deg, rgba(18, 31, 52, 0.96), rgba(13, 23, 40, 0.96));
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 1.2rem 1.25rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.10);
    }

    .metric-label {
        color: #91a6c9;
        font-size: 0.78rem;
        margin-bottom: 0.35rem;
    }

    .metric-value {
        color: #f3f7ff;
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 700;
        font-size: 1.5rem;
    }

    .status-dot {
        display: inline-block;
        height: 8px;
        width: 8px;
        background: #46d6a2;
        border-radius: 50%;
        margin-right: 8px;
        box-shadow: 0 0 12px rgba(70, 214, 162, 0.6);
    }

    .answer-label {
        color: #75a9ff;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-weight: 700;
        margin-bottom: 0.55rem;
    }

    .answer-text {
        color: #f1f6ff;
        font-size: 1.12rem;
        line-height: 1.7;
        font-weight: 500;
    }

    .source-meta {
        color: #8fa5c8;
        font-size: 0.85rem;
        margin-bottom: 0.55rem;
    }

    div[data-testid="stTabs"] button {
        border-radius: 10px;
        padding: 0.65rem 1rem;
        color: #91a5c7;
        font-weight: 600;
    }

    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: #eaf2ff;
        background: rgba(64, 123, 237, 0.14);
    }

    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
        background-color: #5a95ff;
    }

    .stButton > button {
        border: 1px solid rgba(112, 163, 255, 0.35);
        border-radius: 10px;
        min-height: 2.7rem;
        font-weight: 700;
        color: #ffffff;
        background: linear-gradient(105deg, #3478f6, #2863d5);
        transition: all 0.18s ease;
        box-shadow: 0 7px 20px rgba(45, 105, 225, 0.16);
    }

    .stButton > button:hover {
        border-color: #7db0ff;
        background: linear-gradient(105deg, #4388ff, #3474e9);
        transform: translateY(-1px);
    }

    .stButton > button:disabled {
        color: #7e91b2;
        background: #18253a;
        border-color: var(--line);
        box-shadow: none;
    }

    .stTextInput input, .stTextArea textarea {
        background: #0c1627 !important;
        color: #eff5ff !important;
        border: 1px solid rgba(132, 163, 211, 0.22) !important;
        border-radius: 10px !important;
    }

    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #5a95ff !important;
        box-shadow: 0 0 0 1px #5a95ff !important;
    }

    [data-baseweb="select"] > div {
        background: #0c1627;
        border-color: rgba(132, 163, 211, 0.22);
        border-radius: 10px;
        color: #eff5ff;
    }

    [data-testid="stFileUploader"] section {
        background: rgba(12, 22, 39, 0.72);
        border: 1px dashed rgba(106, 157, 248, 0.42);
        border-radius: 14px;
    }

    [data-testid="stFileUploader"] section:hover {
        border-color: #65a0ff;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid var(--line);
        border-radius: 12px;
        overflow: hidden;
    }

    hr {
        border-color: var(--line);
    }

    .sidebar-note {
        color: #8296b8;
        font-size: 0.78rem;
        line-height: 1.5;
    }

    #MainMenu, footer {
        visibility: hidden;
    }

    @media (max-width: 700px) {
        .hero-title { letter-spacing: -0.8px; }
        .hero-copy { font-size: 0.94rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_request(method, path, api_url, **kwargs):
    """Call the FastAPI backend and return decoded JSON or None."""
    try:
        response = requests.request(
            method,
            f"{api_url}{path}",
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
    except requests.RequestException as exc:
        st.error(
            "Unable to connect to the API. Make sure the FastAPI backend is running "
            "and the API URL is correct."
        )
        with st.expander("Connection details"):
            st.code(str(exc))
        return None

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        st.error(f"API error ({response.status_code}): {detail}")
        return None

    try:
        return response.json()
    except ValueError:
        st.error("The API returned an invalid JSON response.")
        return None


@st.cache_data(ttl=3, show_spinner=False)
def get_documents(api_base_url):
    try:
        response = requests.get(f"{api_base_url}/documents", timeout=15)
        response.raise_for_status()
        return response.json(), None
    except requests.RequestException as exc:
        return [], str(exc)


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown(
        """
        <div class="brand-lockup">
            <div class="brand-mark">◈</div>
            <div>
                <div class="brand-name">Document Insight</div>
                <div class="brand-subtitle">AI-powered document search</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("##### CONNECTION")
    api_url = st.text_input(
        "FastAPI URL",
        value=st.session_state.get("api_url", DEFAULT_API_URL),
        placeholder="http://127.0.0.1:8000",
        help="Enter the base URL of your FastAPI backend.",
    ).strip().rstrip("/")
    st.session_state["api_url"] = api_url

    if st.button("Check connection", use_container_width=True):
        st.session_state["check_api_now"] = True

    st.markdown("---")
    st.markdown("##### SESSION")
    sidebar_session = st.session_state.get("session_id")
    if sidebar_session:
        st.caption(f"Current session: `{sidebar_session[:8]}…`")
        if st.button("Delete session", use_container_width=True):
            deleted = api_request("DELETE", f"/sessions/{sidebar_session}", api_url)
            if deleted is not None:
                st.session_state.pop("session_id", None)
                st.session_state.pop("last_answer", None)
                st.session_state.pop("selected_document_id", None)
                get_documents.clear()
                st.rerun()
    else:
        st.caption("No active session. Uploading creates one.")
    if st.button("Start new session", use_container_width=True):
        st.session_state.pop("session_id", None)
        st.session_state.pop("last_answer", None)
        st.rerun()

    st.markdown("---")
    st.markdown(
        """
        <div class="sidebar-note">
            Your workspace for searching PDF documents and finding answers grounded
            in their content.
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------- Header ----------
header_left, header_right = st.columns([5, 1])
with header_left:
    st.markdown('<div class="eyebrow">DOCUMENT INTELLIGENCE WORKSPACE</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-title">Your documents.<br><span>Clear answers.</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero-copy">Upload a PDF, ask a question in natural language, '
        'and explore answers with their source context.</div>',
        unsafe_allow_html=True,
    )

with header_right:
    st.markdown("<div style='height: 1.4rem'></div>", unsafe_allow_html=True)
    if st.session_state.pop("check_api_now", False):
        connection = api_request("GET", "/", api_url)
        if connection:
            st.success("API connected")
    else:
        try:
            response = requests.get(f"{api_url}/", timeout=3)
            if response.ok:
                st.markdown(
                    '<div class="surface-card"><div class="metric-label">API STATUS</div>'
                    '<div style="color:#72e0b5;font-weight:700;"><span class="status-dot"></span>Online</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="surface-card"><div class="metric-label">API STATUS</div>'
                    '<div style="color:#ffb86b;font-weight:700;">Unavailable</div></div>',
                    unsafe_allow_html=True,
                )
        except requests.RequestException:
            st.markdown(
                '<div class="surface-card"><div class="metric-label">API STATUS</div>'
                '<div style="color:#ffb86b;font-weight:700;">Offline</div></div>',
                unsafe_allow_html=True,
            )

st.markdown("---")

# ---------- Workspace ----------
upload_tab, ask_tab, documents_tab = st.tabs(
    ["＋  Upload document", "✦  Ask a question", "▤  Document library"]
)

with upload_tab:
    st.markdown('<div class="section-heading">Add a new document</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">Upload a PDF to extract its content and make it searchable.</div>',
        unsafe_allow_html=True,
    )

    upload_col, tips_col = st.columns([1.7, 1], gap="large")
    with upload_col:
        uploaded_files = st.file_uploader(
            "Choose one or more PDF files",
            type=["pdf"],
            accept_multiple_files=True,
            help=f"PDF files only. Up to {MAX_FILES} files, maximum {MAX_FILE_MB} MB each.",
            key="pdf_upload",
        )
        too_big = [f.name for f in uploaded_files if f.size > MAX_FILE_MB * 1024 * 1024]
        if uploaded_files:
            total_mb = sum(f.size for f in uploaded_files) / (1024 * 1024)
            st.caption(f"Selected **{len(uploaded_files)}** file(s) · {total_mb:.2f} MB total")
        if too_big:
            st.warning(f"Over the {MAX_FILE_MB} MB limit: {', '.join(too_big)}")
        if len(uploaded_files) > MAX_FILES:
            st.warning(f"Select at most {MAX_FILES} files per upload.")

        current_session = st.session_state.get("session_id")
        if current_session:
            st.caption(f"Files will be added to the current session `{current_session[:8]}…`")
        else:
            st.caption("A new session will be created for this upload.")

        upload_clicked = st.button(
            "Upload and index PDFs",
            type="primary",
            disabled=not uploaded_files or bool(too_big) or len(uploaded_files) > MAX_FILES,
            use_container_width=True,
        )

        if upload_clicked and uploaded_files:
            with st.spinner("Extracting content and building the search index..."):
                result = api_request(
                    "POST",
                    "/upload",
                    api_url,
                    files=[
                        ("files", (f.name, f.getvalue(), "application/pdf"))
                        for f in uploaded_files
                    ],
                    data={"session_id": current_session} if current_session else None,
                )

            if result is None and current_session:
                st.caption(
                    "If the session no longer exists on the backend (e.g. it restarted), "
                    "use **Start new session** in the sidebar and upload again."
                )

            if result:
                get_documents.clear()
                st.session_state["session_id"] = result.get("session_id")
                st.session_state.pop("last_answer", None)
                uploaded_docs = result.get("documents", [])
                if uploaded_docs:
                    st.session_state["selected_document_id"] = uploaded_docs[0]["document_id"]
                st.success(f"{len(uploaded_docs)} document(s) uploaded and indexed.")
                for failed in result.get("errors", []):
                    st.warning(f"**{failed['filename']}** was skipped: {failed['detail']}")
                if uploaded_docs:
                    st.dataframe(
                        [
                            {
                                "Document": d["filename"],
                                "Pages": d["pages_processed"],
                                "Chunks": d["chunks_created"],
                            }
                            for d in uploaded_docs
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
                st.info("Your documents are ready. Open **Ask a question** to get started.")

    with tips_col:
        st.markdown(
            """
            <div class="surface-card">
                <div class="eyebrow">HOW IT WORKS</div>
                <div style="font-size:1.03rem;font-weight:700;margin-bottom:0.6rem;">From PDF to insight</div>
                <div style="color:#9aacc9;line-height:1.7;font-size:0.9rem;">
                    <b style="color:#eaf2ff;">01</b> &nbsp;Upload your PDF<br>
                    <b style="color:#eaf2ff;">02</b> &nbsp;Content is extracted and indexed<br>
                    <b style="color:#eaf2ff;">03</b> &nbsp;Ask questions and review sources
                </div>
            </div>
            <div class="surface-card">
                <div style="font-size:0.9rem;font-weight:700;margin-bottom:0.4rem;">Supported format</div>
                <div style="color:#9aacc9;font-size:0.86rem;">PDF · Up to 10 MB per file</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with ask_tab:
    st.markdown('<div class="section-heading">Ask your documents</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-copy">Choose a document and ask a specific question about its content.</div>',
        unsafe_allow_html=True,
    )

    documents, documents_error = get_documents(api_url)

    if documents_error:
        st.warning("Could not load the document library. Check that the API is running.")
    elif not documents:
        st.markdown(
            '<div class="surface-card"><div style="font-weight:700;margin-bottom:0.4rem;">Your workspace is empty</div>'
            '<div style="color:#9aacc9;">Upload a PDF first. Once it is indexed, you can ask questions here.</div></div>',
            unsafe_allow_html=True,
        )
    else:
        doc_options = {
            f'{doc.get("filename", "Untitled PDF")}  ·  {doc.get("pages", 0)} pages': doc["document_id"]
            for doc in documents
        }
        labels = list(doc_options.keys())
        saved_id = st.session_state.get("selected_document_id")
        default_index = next(
            (i for i, label in enumerate(labels) if doc_options[label] == saved_id),
            0,
        )

        session_id = st.session_state.get("session_id")
        session_docs = [d for d in documents if d.get("session_id") == session_id]

        question_col, prompt_col = st.columns([1.5, 1], gap="large")
        with question_col:
            ask_whole_session = False
            if session_docs:
                scope = st.radio(
                    "Search in",
                    [f"Whole session ({len(session_docs)} documents)", "Single document"],
                    horizontal=True,
                    key="ask_scope",
                )
                ask_whole_session = scope.startswith("Whole")

            selected_label = st.selectbox(
                "Document",
                labels,
                index=default_index,
                key="selected_document_label",
                disabled=ask_whole_session,
            )
            question = st.text_area(
                "Your question",
                placeholder="e.g. What is the annual learning budget for a full-time employee?",
                max_chars=1000,
                height=125,
                key="question_input",
            )
            ask_clicked = st.button(
                "Find answer  →",
                type="primary",
                disabled=not question.strip(),
                use_container_width=True,
            )

        with prompt_col:
            st.markdown(
                """
                <div class="surface-card">
                    <div class="eyebrow">GET BETTER RESULTS</div>
                    <div style="font-weight:700;margin-bottom:0.7rem;">Ask with context</div>
                    <div style="color:#9aacc9;font-size:0.9rem;line-height:1.75;">
                        • Ask one clear question at a time<br>
                        • Include a topic, date, or role when useful<br>
                        • Review the source text to verify the answer
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if ask_clicked:
            if ask_whole_session:
                scope_payload = {"session_id": session_id}
                scope_label = f"Whole session ({len(session_docs)} documents)"
            else:
                scope_payload = {"document_id": doc_options[selected_label]}
                scope_label = selected_label

            with st.spinner("Searching the documents and evaluating relevant passages..."):
                result = api_request(
                    "POST",
                    "/ask",
                    api_url,
                    json={**scope_payload, "question": question},
                )

            if result:
                st.session_state["last_answer"] = result
                st.session_state["last_question"] = question
                st.session_state["last_document_label"] = scope_label

        result = st.session_state.get("last_answer")
        if result:
            st.markdown("---")
            st.markdown('<div class="answer-label">ANSWER</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="surface-card"><div class="answer-text">{__import__("html").escape(str(result.get("answer", "No answer returned.")))}</div></div>',
                unsafe_allow_html=True,
            )

            st.caption(f"Searched in: {st.session_state.get('last_document_label', '—')}")

            source = result.get("source")
            if source:
                source_col, page_col = st.columns([4, 1])
                with source_col:
                    st.markdown("**Source context**")
                    st.markdown(
                        f'<div class="source-meta">{__import__("html").escape(str(source.get("filename", "Unknown document")))}</div>',
                        unsafe_allow_html=True,
                    )
                with page_col:
                    st.markdown("**Page**")
                    st.markdown(f"`{source.get('page', '—')}`")
                with st.expander("View retrieved source text", expanded=True):
                    st.write(source.get("text", ""))

            with st.expander("Retrieval details"):
                st.caption(f"Retrieved passages: {result.get('retrieved_chunks', 0)}")
                st.json(result.get("debug_candidates", []))

with documents_tab:
    top_col, refresh_col = st.columns([4, 1])
    with top_col:
        st.markdown('<div class="section-heading">Document library</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="section-copy">All PDFs currently loaded in this backend session.</div>',
            unsafe_allow_html=True,
        )
    with refresh_col:
        st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
        if st.button("Refresh ↻", use_container_width=True):
            get_documents.clear()

    documents, documents_error = get_documents(api_url)
    if documents_error:
        st.error("Unable to retrieve documents. Check the API connection.")
    elif not documents:
        st.info("No documents have been uploaded yet.")
    else:
        st.markdown(
            f'<div class="source-meta">{len(documents)} document(s) in your current session</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            [
                {
                    "Document": doc.get("filename", "Untitled PDF"),
                    "Session": (doc.get("session_id") or "—")[:8],
                    "Pages": doc.get("pages", 0),
                    "Chunks": doc.get("chunks", 0),
                    "Document ID": doc.get("document_id", "—"),
                }
                for doc in documents
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Documents are stored in backend memory for this version. "
            "They will be cleared when the backend process restarts."
        )
