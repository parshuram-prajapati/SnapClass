import streamlit as st


def header_home():

    logo_url = "https://i.ibb.co/YTYGn5qV/logo.png"
    
    st.markdown(f"""
        <div class="home-brand" id="home-brand">
            <img class="home-brand-logo" src="{logo_url}" alt="SnapClass logo" />
            <div class="home-brand-heading" role="heading" aria-level="1">
                <span>FACE</span>
                <span>PRESENCE</span>
            </div>
        </div>   
                
                """, unsafe_allow_html=True)


def header_dashboard():

    logo_url = "https://i.ibb.co/YTYGn5qV/logo.png"
    
    st.markdown(f"""
        <div style="display:flex; align-items:center; justify-content:center; gap:10px">
            <img src='{logo_url}' style='height:85px;' />
            <h2 style='text-align:left; color:#5865F2; font-size:1.5rem !important; white-space:nowrap'>FACE<br/>PRESENCE</h2>
        </div>   
                
                """, unsafe_allow_html=True)
