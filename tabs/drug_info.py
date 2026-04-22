"""
Drug Information Page
"""
import streamlit as st
from utils.data_fetchers import fetch_drug_info
from utils.formatters import truncate_text


def show():
    st.markdown('<h2 class="gradient-header">💊 Drug Information</h2>', unsafe_allow_html=True)
    st.markdown("Search comprehensive drug information from FDA OpenFDA database")

    pending = st.session_state.pop("drug_pending_search", None)
    
    # Search interface
    drug_name = st.text_input(
        "Enter drug name (brand or generic)",
        value=pending or "",
        placeholder="e.g., Aspirin, Lipitor, Metformin...",
        label_visibility="visible",
        key="drug_name_input",
    )
    
    if drug_name:
        with st.spinner(f"🔍 Searching for {drug_name}..."):
            drugs = fetch_drug_info(drug_name)
        
        if not drugs:
            st.warning(f"⚠️ No information found for '{drug_name}'. Try a different name or spelling.")
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
                    st.markdown("#### Purpose")
                    purpose = truncate_text(drug.get('purpose', 'N/A'), 300)
                    st.markdown(purpose)
                
                st.markdown("#### Indications & Usage")
                indications = truncate_text(drug.get('indications', 'N/A'), 400)
                st.markdown(indications)
                
                st.markdown("#### ⚠️ Warnings")
                warnings = truncate_text(drug.get('warnings', 'N/A'), 400)
                st.markdown(f'<div style="background: rgba(239, 68, 68, 0.1); padding: 1rem; border-radius: 8px; border-left: 4px solid #EF4444;">{warnings}</div>', unsafe_allow_html=True)
                
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
