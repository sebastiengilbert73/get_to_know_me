import streamlit as st
import json
import os
from assistant import Assistant, get_available_models
from profile_manager import ProfileManager
from web_search import WebSearcher
import time

st.set_page_config(page_title="get_to_know_me", page_icon="🤖", layout="wide")

# Initialize web searcher
if "web_searcher" not in st.session_state:
    st.session_state.web_searcher = WebSearcher()
if "available_models" not in st.session_state:
    st.session_state.available_models = get_available_models()
if not st.session_state.available_models:
    st.session_state.available_models = ["llama3.2"]  # fallback
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ---- User Selection (top of sidebar) ----
st.sidebar.title("👤 User Selection")

NEW_USER_LABEL = "➕ New user"
existing_users = ProfileManager.list_users()
user_options = existing_users + [NEW_USER_LABEL]

# Determine default index
if "current_user" not in st.session_state:
    st.session_state.current_user = existing_users[0] if existing_users else None

default_index = 0
if st.session_state.current_user and st.session_state.current_user in user_options:
    default_index = user_options.index(st.session_state.current_user)

selected_user = st.sidebar.selectbox("Select User", user_options, index=default_index)

# Handle "New user" selection
if selected_user == NEW_USER_LABEL:
    new_username = st.sidebar.text_input("Enter new username:")
    if st.sidebar.button("Create User"):
        if new_username.strip():
            clean_name = new_username.strip()
            if clean_name in existing_users:
                st.sidebar.error(f"User '{clean_name}' already exists!")
            else:
                st.session_state.current_user = clean_name
                st.session_state.profile_manager = ProfileManager(username=clean_name)
                st.session_state.chat_history = []
                st.rerun()
        else:
            st.sidebar.error("Please enter a valid username.")
    # Don't continue rendering the rest of the app until user is created
    if not st.session_state.current_user:
        st.stop()
else:
    # Switch user if changed
    if st.session_state.current_user != selected_user:
        st.session_state.current_user = selected_user
        st.session_state.profile_manager = ProfileManager(username=selected_user)
        st.session_state.chat_history = []  # Reset chat on user switch
        st.rerun()

# Ensure profile_manager exists for current user
if "profile_manager" not in st.session_state:
    if st.session_state.current_user:
        st.session_state.profile_manager = ProfileManager(username=st.session_state.current_user)
    else:
        st.stop()

# ---- Profile Section ----
st.sidebar.markdown("---")
st.sidebar.title("Your Profile")
st.sidebar.write("This profile is automatically updated by the assistant based on your conversations, but you can also edit it manually.")

# Profile editor
current_profile_dict = st.session_state.profile_manager.read_profile()
current_profile_str = json.dumps(current_profile_dict, indent=4, ensure_ascii=False)

edited_profile = st.sidebar.text_area("Edit Profile", value=current_profile_str, height=400)
if st.sidebar.button("Save Profile Manually"):
    try:
        parsed_json = json.loads(edited_profile)
        st.session_state.profile_manager.update_profile(parsed_json)
        st.sidebar.success("Profile saved!")
        current_profile_str = edited_profile
    except json.JSONDecodeError:
        st.sidebar.error("Invalid JSON format. Please check your syntax before saving.")

# ---- Model Selection ----
MODEL_FILE = "last_model.txt"

default_model_index = 0
if os.path.exists(MODEL_FILE):
    with open(MODEL_FILE, "r") as f:
        last_model = f.read().strip()
    if last_model in st.session_state.available_models:
        default_model_index = st.session_state.available_models.index(last_model)

selected_model = st.sidebar.selectbox(
    "Ollama Model",
    st.session_state.available_models,
    index=default_model_index
)

with open(MODEL_FILE, "w") as f:
    f.write(selected_model)

st.session_state.assistant = Assistant(model_name=selected_model)

# ---- Main Chat UI ----
st.title(f"get_to_know_me Chat — {st.session_state.current_user}")
st.write("An assistant that learns about you, proposes discussion topics, and finds interesting articles.")

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if not st.session_state.chat_history:
    with st.spinner("Initializing..."):
        initial_greeting = st.session_state.assistant.generate_initial_greeting(current_profile_dict)
        st.session_state.chat_history.append({"role": "assistant", "content": initial_greeting})
    st.rerun()

if prompt := st.chat_input("Say something..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking...")

        raw_history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history[:-1]]

        with st.spinner("Processing..."):
            result = st.session_state.assistant.process_message(
                user_message=prompt,
                chat_history=raw_history,
                current_profile=st.session_state.profile_manager.read_profile(),
                web_searcher=st.session_state.web_searcher
            )

        response_text = result["response"]
        message_placeholder.markdown(response_text)
        st.session_state.chat_history.append({"role": "assistant", "content": response_text})

        # Check if profile was updated
        if result["new_profile"] != st.session_state.profile_manager.read_profile():
            st.session_state.profile_manager.update_profile(result["new_profile"])
            st.sidebar.info("Profile was updated by the assistant!")
            time.sleep(1)
            st.rerun()
