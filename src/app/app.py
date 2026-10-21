"""Olist DSS Streamlit entry point."""

import streamlit as st


st.set_page_config(page_title="Olist DSS", layout="wide")
st.markdown(
    """
    <style>
        [data-testid="stAppViewContainer"] { background: #f8fafc; }
        [data-testid="stSidebar"] { background: #eef2ff; }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 12px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

pages = [
    st.Page("pages/1_Overview.py", title="Overview", default=True),
    st.Page("pages/2_Sales_analysis.py", title="Sales analysis"),
    st.Page("pages/3_Late_delivery_DSS.py", title="Late-delivery DSS"),
]
st.navigation(pages).run()
