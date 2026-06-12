import streamlit as st

st.title("World Cup Draft Test")
st.success("Streamlit is working.")

try:
    token = st.secrets["FOOTBALL_DATA_TOKEN"]
    st.write("API key found.")
except Exception:
    st.warning("API key not found.")
