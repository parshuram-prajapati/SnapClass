import streamlit as st



def style_background_home():

    st.markdown("""
        <style>

                .stApp {
                    background: #5865F2 !important;
                }

                .stApp div[data-testid="stColumn"]{
                    background-color:#E0E3FF !important;
                    padding:2.5rem !important;
                    border-radius: 5rem !important;
                    }

                @media (max-width: 640px) {
                    .stApp {
                        overflow-x: clip;
                    }

                    .stApp .block-container {
                        box-sizing: border-box;
                        max-width: 100% !important;
                        padding-left: 1rem !important;
                        padding-right: 1rem !important;
                    }

                    .stApp div[data-testid="stHorizontalBlock"] {
                        flex-direction: column !important;
                        gap: 1rem !important;
                    }

                    .stApp div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                        box-sizing: border-box;
                        flex: 1 1 100% !important;
                        width: 100% !important;
                        min-width: 0 !important;
                        max-width: 100% !important;
                        padding: 1.25rem !important;
                        border-radius: 1.75rem !important;
                    }

                    .stApp div[data-testid="stImage"] img {
                        max-width: 100%;
                        height: auto;
                        object-fit: contain;
                    }
                }
        </style>  

                """
            ,unsafe_allow_html=True)
    

def style_background_dashboard():

    st.markdown("""
        <style>

                .stApp {
                    background: #E0E3FF !important;
                }

        </style>  

                """
            ,unsafe_allow_html=True)
    

    

def style_base_layout():
# asdasd
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Climate+Crisis:YEAR@1979&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap');

                
         /* Hide Top Bar of streamlit */
                
            #MainMenu, footer, header {
                visibility: hidden;
            }
                
            .block-container {
                padding-top:1.5rem !important;    
            }

            h1 {
                font-family: 'Climate Crisis', sans-serif !important;
                font-size: 3.5rem !important;
                line-height:1.1 1important;
                margin-bottom:0rem !important;
            }

            .home-brand {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                max-width: 100%;
                margin: 1.875rem 0;
                text-align: center;
            }

            .home-brand-logo {
                display: block;
                width: 100px;
                height: auto;
                max-width: 100%;
            }

            .home-brand-heading {
                width: max-content;
                max-width: 100%;
                margin: 0 !important;
                color: #E0E3FF !important;
                font-family: 'Climate Crisis', sans-serif !important;
                font-size: clamp(2rem, 5vw, 3.5rem) !important;
                font-weight: 400;
                letter-spacing: -0.035em;
                line-height: 0.96 !important;
                text-align: center;
                word-break: normal;
                overflow-wrap: normal;
                hyphens: none;
            }

            .home-brand-heading span {
                display: block;
                white-space: nowrap;
            }

            h2 {
                font-family: 'Climate Crisis', sans-serif !important;
                font-size: 2rem !important;
                line-height:0.9 !important;
                margin-bottom:0rem !important;
            }
                
            h3, h4, p {
                font-family: 'Outfit', sans-serif;    
            }
                

            button{
                border-radius: 1.5rem !important;
                background-color: #5865F2 !important;
                color: white !important;
                padding: 10px 20px !important;
                border: none !important;
                transition: transform 0.25s ease-in-out !important;
                }

            button[kind="secondary"]{
                border-radius: 1.5rem !important;
                background-color: #EB459E !important;
                color: white !important;
                padding: 10px 20px !important;
                border: none !important;
                transition: transform 0.25s ease-in-out !important;
                }

            button[kind="tertiary"]{
                border-radius: 1.5rem !important;
                background-color: black !important;
                color: white !important;
                padding: 10px 20px !important;
                border: none !important;
                transition: transform 0.25s ease-in-out !important;
                }

            button:hover{
                transform :scale(1.05)}

            @media (max-width: 640px) {
                .home-brand {
                    margin: 1.25rem 0 1.5rem;
                    padding-inline: 0.5rem;
                }

                .home-brand-logo {
                    width: clamp(4.25rem, 15vw, 5rem);
                }

                .home-brand-heading {
                    letter-spacing: -0.04em;
                    line-height: 0.98 !important;
                }
            }
        </style>  

                """
            ,unsafe_allow_html=True)