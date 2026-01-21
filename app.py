import streamlit as st
from firebase import db
from datetime import datetime, timedelta
import time
import uuid

st.set_page_config(page_title="Project NN - Voting", layout="centered")

# Custom CSS for circular buttons
st.markdown("""
    <style>
    .button-container {
        display: flex;
        justify-content: center;
        gap: 50px;
        margin: 30px 0;
    }
    
    .circular-btn {
        width: 150px;
        height: 150px;
        border-radius: 50%;
        border: none;
        font-size: 20px;
        font-weight: bold;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
        color: white;
    }
    
    .circular-btn:hover {
        transform: scale(1.1);
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
    }
    
    .circular-btn:active {
        transform: scale(0.95);
    }
    
    .red-btn {
        background-color: #FF4444;
    }
    
    .green-btn {
        background-color: #44AA44;
    }
    
    .timer {
        text-align: center;
        font-size: 48px;
        font-weight: bold;
        margin: 20px 0;
        color: #2c3e50;
    }
    
    .result-box {
        text-align: center;
        padding: 20px;
        margin: 20px 0;
        border-radius: 10px;
        font-size: 18px;
    }
    
    .result-red {
        background-color: #FFE6E6;
        border: 2px solid #FF4444;
    }
    
    .result-green {
        background-color: #E6FFE6;
        border: 2px solid #44AA44;
    }
    
    .voted-message {
        text-align: center;
        padding: 15px;
        background-color: #FFF3CD;
        border: 2px solid #FFC107;
        border-radius: 10px;
        font-size: 18px;
        font-weight: bold;
        color: #856404;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎯 Project NN - Voting System")

# Initialize session state
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "current_round" not in st.session_state:
    st.session_state.current_round = 1
    st.session_state.round_start_time = datetime.now()
    st.session_state.has_voted_in_round = False
    st.session_state.user_vote = None

if "red_votes" not in st.session_state:
    st.session_state.red_votes = 0
    st.session_state.green_votes = 0

ROUND_DURATION = 60  # 1 minute
VOTING_CUTOFF = 5    # Stop voting 5 seconds before round ends

# Auto-refresh every second
placeholder = st.empty()
placeholder_timer = st.empty()
placeholder_buttons = st.empty()
placeholder_voting_status = st.empty()
placeholder_stats = st.empty()

def get_current_round_elapsed():
    """Calculate elapsed time in current round"""
    elapsed = (datetime.now() - st.session_state.round_start_time).total_seconds()
    return elapsed

def get_time_remaining():
    """Calculate remaining time in current round"""
    elapsed = get_current_round_elapsed()
    remaining = ROUND_DURATION - elapsed
    return max(0, remaining)

def check_and_advance_round():
    """Check if round should advance"""
    if get_time_remaining() <= 0:
        # Store round result
        db.collection("rounds").add({
            "round_number": st.session_state.current_round,
            "red_votes": st.session_state.red_votes,
            "green_votes": st.session_state.green_votes,
            "round_end_timestamp": datetime.now(),
            "winner": "RED" if st.session_state.red_votes > st.session_state.green_votes else 
                     "GREEN" if st.session_state.green_votes > st.session_state.red_votes else "TIE"
        })
        
        # Reset for new round
        st.session_state.current_round += 1
        st.session_state.round_start_time = datetime.now()
        st.session_state.has_voted_in_round = False
        st.session_state.user_vote = None
        st.session_state.red_votes = 0
        st.session_state.green_votes = 0

# Main loop
while True:
    check_and_advance_round()
    
    remaining = get_time_remaining()
    elapsed = get_current_round_elapsed()
    voting_open = remaining > VOTING_CUTOFF
    
    # Display round info
    with placeholder.container():
        st.markdown(f"<h3 style='text-align: center;'>Round #{st.session_state.current_round}</h3>", unsafe_allow_html=True)
    
    # Display timer
    with placeholder_timer.container():
        if remaining > 0:
            st.markdown(f"<div class='timer'>⏱ {int(remaining)}s</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='timer'>⏱ Round Ending...</div>", unsafe_allow_html=True)
    
    # Display voting status
    with placeholder_voting_status.container():
        if st.session_state.has_voted_in_round:
            st.markdown(f"""
                <div class='voted-message'>
                    ✅ You voted for {st.session_state.user_vote} in this round!
                </div>
            """, unsafe_allow_html=True)
        elif voting_open:
            st.info("🗳 Cast your vote! (Voting closes in 5 seconds)")
        else:
            st.warning("⛔ Voting Closed - New round starting soon...")
    
    # Display voting buttons
    with placeholder_buttons.container():
        if voting_open and not st.session_state.has_voted_in_round:
            col_red, col_spacer, col_green = st.columns([1, 0.5, 1])
            
            with col_red:
                if st.button("🔴 RED", key=f"red_{st.session_state.current_round}_{time.time()}", use_container_width=True):
                    st.session_state.red_votes += 1
                    st.session_state.has_voted_in_round = True
                    st.session_state.user_vote = "RED"
                    
                    # Store vote in database
                    db.collection("votes").add({
                        "round": st.session_state.current_round,
                        "color": "RED",
                        "user_id": st.session_state.user_id,
                        "timestamp": datetime.now(),
                        "round_elapsed_seconds": elapsed
                    })
                    st.rerun()
            
            with col_green:
                if st.button("🟢 GREEN", key=f"green_{st.session_state.current_round}_{time.time()}", use_container_width=True):
                    st.session_state.green_votes += 1
                    st.session_state.has_voted_in_round = True
                    st.session_state.user_vote = "GREEN"
                    
                    # Store vote in database
                    db.collection("votes").add({
                        "round": st.session_state.current_round,
                        "color": "GREEN",
                        "user_id": st.session_state.user_id,
                        "timestamp": datetime.now(),
                        "round_elapsed_seconds": elapsed
                    })
                    st.rerun()
    
    # Display statistics
    with placeholder_stats.container():
        st.divider()
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Current Round", st.session_state.current_round)
        
        with col2:
            st.metric("🔴 Red Votes", st.session_state.red_votes)
        
        with col3:
            st.metric("🟢 Green Votes", st.session_state.green_votes)
    
    # Refresh every 0.5 seconds
    time.sleep(0.5)
    st.rerun()