"""
Drug Information Page
"""
import hashlib
import re
import streamlit as st
import config
from utils.data_fetchers import fetch_drug_info, fetch_drug_info_relaxed
from utils.spellcheck_util import normalize_query_text, suggest_for_text, candidates_for_tokens
from difflib import SequenceMatcher


def _has_content(value: str) -> bool:
    v = str(value or "").strip()
    if not v:
        return False
    return v.upper() not in {"N/A", "NONE", "NULL", "NOT AVAILABLE"}


def _normalize_section_text(text: str, section_key: str = "") -> str:
    """Clean noisy FDA label formatting for easier reading."""
    t = str(text or "").strip()
    # Remove citation-like markers: ( 1 ), [see ...], etc.
    t = re.sub(r"\(\s*\d+(\.\d+)?\s*\)", "", t)
    t = re.sub(r"\[\s*see[^\]]*\]", "", t, flags=re.IGNORECASE)
    # Strip common section headers in a safe, section-specific way (avoid clipping first letter).
    header_patterns = {
        "indications": r"^\s*\d+(\.\d+)?\s+INDICATIONS AND USAGE\s*",
        "dosage": r"^\s*\d+(\.\d+)?\s+DOSAGE AND ADMINISTRATION\s*",
        "side_effects": r"^\s*\d+(\.\d+)?\s+ADVERSE REACTIONS\s*",
        "interactions": r"^\s*\d+(\.\d+)?\s+DRUG INTERACTIONS\s*",
        "contraindications": r"^\s*\d+(\.\d+)?\s+CONTRAINDICATIONS\s*",
        "pregnancy_warning": r"^\s*8(\.\d+)?\s+PREGNANCY(\s+RISK SUMMARY)?\s*",
        "alternatives": r"^\s*\d+(\.\d+)?\s+MECHANISM OF ACTION\s*",
        "warnings": r"^\s*\d+(\.\d+)?\s+WARNINGS( AND PRECAUTIONS)?\s*",
    }
    pat = header_patterns.get(section_key)
    if pat:
        t = re.sub(pat, "", t, flags=re.IGNORECASE)

    t = re.sub(r"\s+", " ", t).strip()
    return t


def _concise_summary(
    text: str, max_sentences: int = 1, max_chars: int = 220, section_key: str = ""
) -> str:
    cleaned = _normalize_section_text(text, section_key=section_key)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = " ".join([p for p in parts if p][:max_sentences]).strip()
    if not summary:
        summary = cleaned
    if len(summary) > max_chars:
        clipped = summary[:max_chars].rstrip()
        # Keep sentence-like ending; avoid cutting in the middle of a word.
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        summary = clipped.rstrip(" ,;:-")
        if not summary.endswith((".", "!", "?")):
            summary += "."
    return summary


def _safe_correction(raw: str, candidate: str) -> bool:
    r = (raw or "").strip().lower()
    c = (candidate or "").strip().lower()
    if not r or not c or r == c:
        return False
    if r[0] != c[0]:
        return False
    if abs(len(r) - len(c)) > 2:
        return False
    common_prefix = 0
    for a, b in zip(r, c):
        if a != b:
            break
        common_prefix += 1
    return common_prefix >= 2


def _best_name_match(raw: str, drugs: list[dict]) -> str:
    aliases = _intent_alias_strings(raw or "")
    names = []
    for d in drugs or []:
        b = str(d.get("brand_name", "")).strip()
        g = str(d.get("generic_name", "")).strip()
        if b and b != "N/A":
            names.append(b)
        if g and g != "N/A":
            names.append(g)
    best = ""
    best_score = 0.0
    for n in names:
        nl = n.lower()
        score = max(SequenceMatcher(None, a, nl).ratio() for a in aliases)
        if score > best_score:
            best_score = score
            best = n
    return best if best_score >= 0.58 else ""


def _name_similarity(raw: str, name: str) -> float:
    return SequenceMatcher(None, (raw or "").strip().lower(), (name or "").strip().lower()).ratio()


def _intent_alias_strings(raw: str) -> set[str]:
    """
    When user input is close to any name in a synonym group, treat all names in that group
    as intent aliases (e.g. paracetamol <-> acetaminophen for US FDA labels).
    """
    r = (raw or "").strip().lower()
    if not r:
        return set()
    out = {r}
    for group in getattr(config, "DRUG_NAME_SYNONYM_GROUPS", []) or []:
        gl = [str(x).strip().lower() for x in group if x and str(x).strip()]
        if not gl:
            continue
        best = max(SequenceMatcher(None, r, g).ratio() for g in gl)
        if best >= 0.45:
            out.update(gl)
    return out


def _best_similarity_for_drug(raw: str, drug: dict) -> float:
    aliases = _intent_alias_strings(raw)
    b = str(drug.get("brand_name", "")).strip()
    g = str(drug.get("generic_name", "")).strip()
    scores = []

    def add_text(t: str) -> None:
        tl = t.lower()
        for a in aliases:
            scores.append(SequenceMatcher(None, a, tl).ratio())

    if b and b != "N/A":
        add_text(b)
        for tok in b.split():
            if len(tok) >= 3:
                add_text(tok)
    if g and g != "N/A":
        add_text(g)
        for part in re.split(r"[,/+]| AND | and ", g):
            tok = part.strip()
            if len(tok) >= 3:
                add_text(tok)
    return max(scores) if scores else 0.0


def _filter_relaxed_matches(raw: str, drugs: list[dict]) -> list[dict]:
    if not drugs:
        return []
    ranked = [(d, _best_similarity_for_drug(raw, d)) for d in drugs]
    ranked.sort(key=lambda x: x[1], reverse=True)
    best = ranked[0][1]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    # Require a strong best hit; prefer clear winner over noisy prefix matches (e.g. Parasol vs acetaminophen).
    if best < 0.58:
        return []
    if len(ranked) > 1 and (best - second) < 0.02 and best < 0.72:
        return []
    cutoff = max(0.52, best - 0.14)
    return [d for d, s in ranked if s >= cutoff][:5]


def _labels_from_relaxed_pool(raw: str, drugs: list[dict]) -> list[str]:
    """Build ranked clickable drug-name suggestions from a broad OpenFDA pool."""
    if not drugs or not raw.strip():
        return []
    aliases = _intent_alias_strings(raw)
    raw_l = raw.strip().lower()
    labels: list[tuple[str, float]] = []

    def sim_aliases(text: str) -> float:
        tl = text.strip().lower()
        return max(SequenceMatcher(None, a, tl).ratio() for a in aliases)

    for d in drugs:
        b = str(d.get("brand_name", "")).strip()
        if b and b != "N/A":
            labels.append((b, sim_aliases(b)))
        g = str(d.get("generic_name", "")).strip()
        if g and g != "N/A":
            for part in re.split(r"[,/+]| AND | and ", g):
                t = part.strip()
                if len(t) >= 4 and not t.isdigit():
                    labels.append((t, sim_aliases(t)))

    labels.sort(key=lambda x: x[1], reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for lab, score in labels:
        key = lab.lower()
        if key in seen or key == raw_l:
            continue
        if score < 0.38:
            continue
        seen.add(key)
        out.append(lab)
        if len(out) >= 8:
            break
    if not out and labels:
        for lab, _ in labels[:6]:
            key = lab.lower()
            if key not in seen and key != raw_l:
                seen.add(key)
                out.append(lab)
    return out


def _synonym_search_terms(raw: str) -> list[str]:
    """Extra OpenFDA query strings when input matches a synonym group (e.g. paracetamol → acetaminophen)."""
    r = (raw or "").strip().lower()
    if not r:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for group in getattr(config, "DRUG_NAME_SYNONYM_GROUPS", []) or []:
        gl = [str(x).strip() for x in group if x and str(x).strip()]
        if not gl:
            continue
        gll = [g.lower() for g in gl]
        if max(SequenceMatcher(None, r, g).ratio() for g in gll) < 0.45:
            continue
        gl_sorted = sorted(gl, key=lambda x: (0 if x.lower() == "acetaminophen" else 1, x.lower()))
        for g in gl_sorted:
            k = g.lower()
            if k == r or k in seen:
                continue
            seen.add(k)
            out.append(g)
    return out


def _merge_suggestions(raw: str, spell_cands: list[str], api_labels: list[str]) -> list[str]:
    raw_l = raw.strip().lower()
    merged: list[str] = []
    seen: set[str] = set()
    for lab in spell_cands + api_labels:
        if not lab or len(lab.strip()) < 3:
            continue
        k = lab.strip().lower()
        if k == raw_l or k in seen:
            continue
        seen.add(k)
        merged.append(lab.strip())
        if len(merged) >= 10:
            break
    return merged


def show():
    st.markdown('<h2 class="gradient-header">💊 Drug Information</h2>', unsafe_allow_html=True)
    st.markdown("Search comprehensive drug information from FDA OpenFDA database")

    pending = st.session_state.pop("drug_pending_search", None)
    if pending:
        # text_input with a fixed key keeps prior widget state unless we set it explicitly
        st.session_state["drug_name_input"] = pending
    
    # Search interface
    drug_name = st.text_input(
        "Enter drug name (brand or generic)",
        value=pending or "",
        placeholder="e.g., Aspirin, Lipitor, Metformin...",
        label_visibility="visible",
        key="drug_name_input",
    )

    raw_input = (drug_name or "").strip()
    normalized_name, auto_corrections = normalize_query_text(raw_input) if raw_input else ("", [])
    safe_normalized = normalized_name if _safe_correction(raw_input, normalized_name) else raw_input
    
    if drug_name:
        hint_candidates = suggest_for_text(raw_input) if raw_input else []
        candidates = []
        if raw_input:
            candidates.append(raw_input)
        for syn in _synonym_search_terms(raw_input):
            if syn.lower() not in {c.lower() for c in candidates}:
                candidates.append(syn)
        if safe_normalized and safe_normalized.lower() != raw_input.lower():
            candidates.append(safe_normalized)

        for _orig, sug in hint_candidates[:4]:
            if _safe_correction(raw_input, sug) and sug.lower() not in [x.lower() for x in candidates]:
                candidates.append(sug)

        if not candidates:
            candidates = [raw_input]

        query_to_use = candidates[0]
        corrected_query_used = ""
        corrected_hint = ""
        drugs = []
        with st.spinner(f"🔍 Searching for {query_to_use}..."):
            for cand in candidates:
                query_to_use = cand
                drugs = fetch_drug_info(cand, suppress_errors=True)
                if drugs:
                    if cand.lower() != raw_input.lower():
                        corrected_query_used = cand
                    break
            if not drugs and raw_input:
                relaxed = fetch_drug_info_relaxed(
                    raw_input, suppress_errors=True, per_query_limit=25, max_total=45
                )
                drugs = _filter_relaxed_matches(raw_input, relaxed)
                if drugs:
                    corrected_hint = _best_name_match(raw_input, drugs)
                    st.caption("Used relaxed typo-tolerant match.")
        if corrected_query_used:
            st.info(f"Spell check applied: `{raw_input}` -> `{corrected_query_used}`")
            st.caption(f"Retrieved results using corrected query: `{corrected_query_used}`")
        elif corrected_hint and corrected_hint.lower() != raw_input.lower():
            st.info(f"Did you mean `{corrected_hint}`? Retrieved closest matching results.")
        
        if not drugs:
            safe_hints = [(a, b) for a, b in hint_candidates if _safe_correction(raw_input, b)]
            if safe_hints:
                hint_str = ", ".join([f"`{a}` -> `{b}`" for a, b in safe_hints[:6]])
                st.caption(f"Spell hints: {hint_str}")
            if auto_corrections and safe_normalized.lower() != raw_input.lower():
                st.caption(f"Tried safe normalized query: `{safe_normalized}`")

            spell_cands = candidates_for_tokens(raw_input, max_per_token=15)
            relaxed_pool = fetch_drug_info_relaxed(
                raw_input, suppress_errors=True, per_query_limit=25, max_total=45
            )
            api_labels = _labels_from_relaxed_pool(raw_input, relaxed_pool)
            suggestions = _merge_suggestions(raw_input, spell_cands, api_labels)

            if suggestions:
                st.markdown("**Similar names — click one to search:**")
                cols = st.columns(4)
                for i, label in enumerate(suggestions):
                    with cols[i % 4]:
                        key = f"drug_sug_{i}_{hashlib.md5(label.encode('utf-8')).hexdigest()[:10]}"
                        if st.button(label, key=key, use_container_width=True):
                            st.session_state.drug_pending_search = label
                            st.rerun()

            st.warning(f"⚠️ No exact match for '{raw_input}'. Use a suggestion above or refine spelling.")
            st.info("""
            **Search Tips:**
            - Try both brand and generic names
            - Check spelling
            - Use common names (e.g., 'Aspirin' instead of 'Acetylsalicylic acid')
            """)
            return
        
        st.success(f"✅ Found {len(drugs)} result(s)")
        
        # Display drug information
        for idx, drug in enumerate(drugs):
            with st.expander(f"📋 {drug.get('brand_name', 'N/A')} ({drug.get('generic_name', 'N/A')})", expanded=(idx == 0)):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("#### General Information")
                    st.markdown(f"**Brand Name:** {drug.get('brand_name', 'N/A')}")
                    st.markdown(f"**Generic Name:** {drug.get('generic_name', 'N/A')}")
                    st.markdown(f"**Manufacturer:** {drug.get('manufacturer', 'N/A')}")
                    st.markdown(f"**Route:** {drug.get('route', 'N/A')}")
                
                with col2:
                    purpose = drug.get("purpose", "")
                    if _has_content(purpose):
                        st.markdown("#### Purpose")
                        st.markdown(
                            _concise_summary(
                                purpose,
                                max_sentences=1,
                                max_chars=220,
                                section_key="purpose",
                            )
                        )

                indications = drug.get("indications", "")
                if _has_content(indications):
                    st.markdown("#### Indications & Usage")
                    st.markdown(
                        _concise_summary(
                            indications,
                            max_sentences=1,
                            max_chars=220,
                            section_key="indications",
                        )
                    )

                warnings = drug.get("warnings", "")
                if _has_content(warnings):
                    st.markdown("#### ⚠️ Warnings")
                    warn_text = _concise_summary(
                        warnings,
                        max_sentences=1,
                        max_chars=220,
                        section_key="warnings",
                    )
                    st.markdown(warn_text)

                sections = [
                    ("#### Dosage", "dosage", 220),
                    ("#### Side Effects", "side_effects", 220),
                    ("#### Alternatives", "alternatives", 220),
                ]
                for heading, key, max_len in sections:
                    value = drug.get(key, "N/A")
                    if _has_content(value):
                        st.markdown(heading)
                        section_text = _concise_summary(
                            value,
                            max_sentences=1,
                            max_chars=min(max_len, 220),
                            section_key=key,
                        )
                        st.markdown(section_text)
                
                st.markdown("---")
                st.markdown("*This information is from FDA OpenFDA. Always consult a healthcare professional.*")
    
    else:
        # Show placeholder
        st.info("👆 Enter a drug name to search")
        
        st.markdown("### 🔍 Popular Searches")
        
        popular_drugs = [
            "Aspirin", "Lipitor", "Metformin", "Lisinopril",
            "Amoxicillin", "Levothyroxine", "Atorvastatin", "Omeprazole"
        ]
        
        cols = st.columns(4)
        for idx, drug in enumerate(popular_drugs):
            with cols[idx % 4]:
                if st.button(drug, use_container_width=True):
                    st.session_state.drug_pending_search = drug
                    st.rerun()
