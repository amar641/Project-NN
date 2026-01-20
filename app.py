import streamlit as st
from firebase import db
from datetime import datetime

st.title("Firebase Connection Test")

if st.button("Test Write"):
    db.collection("test").add({
        "timestamp": datetime.utcnow()
    })
    st.success("Firebase connected successfully!")
