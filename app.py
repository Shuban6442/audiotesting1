# server.py
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret!"
# Use eventlet or gevent in production; if installed, Flask-SocketIO will use it automatically.
socketio = SocketIO(app, cors_allowed_origins="*")

# Basic in-memory session store: session_id -> { sid -> name }
sessions = {}

@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("create_session")
def on_create_session():
    session_id = str(uuid.uuid4())[:6]
    sessions[session_id] = {}
    emit("session_created", {"session_id": session_id})


@socketio.on("join")
def on_join(data):
    """
    data: { session: <session_id>, name: <display_name> }
    """
    session = data.get("session")
    name = data.get("name", "Anonymous")
    sid = request.sid

    if not session:
        emit("error", {"msg": "No session specified"})
        return

    if session not in sessions:
        sessions[session] = {}

    # Add participant
    sessions[session][sid] = name
    join_room(session)

    # Tell the joining client who is already present
    other_peers = [s for s in sessions[session].keys() if s != sid]
    emit("existing_peers", {"peers": other_peers})

    # Notify others that a new peer joined
    emit("peer_joined", {"sid": sid, "name": name}, room=session, include_self=False)


@socketio.on("offer")
def on_offer(data):
    """Forward offer from caller -> target"""
    target = data.get("target")
    sdp = data.get("sdp")
    if target:
        emit("offer", {"from": request.sid, "sdp": sdp}, to=target)


@socketio.on("answer")
def on_answer(data):
    """Forward answer from callee -> caller"""
    target = data.get("target")
    sdp = data.get("sdp")
    if target:
        emit("answer", {"from": request.sid, "sdp": sdp}, to=target)


@socketio.on("ice-candidate")
def on_ice_candidate(data):
    """Forward ICE candidate to target peer"""
    target = data.get("target")
    candidate = data.get("candidate")
    if target:
        emit("ice-candidate", {"from": request.sid, "candidate": candidate}, to=target)


@socketio.on("leave")
def on_leave(data):
    """Peer voluntarily leaving a session"""
    session = data.get("session")
    sid = request.sid
    if session and session in sessions and sid in sessions[session]:
        leave_room(session)
        sessions[session].pop(sid, None)
        emit("peer_left", {"sid": sid}, room=session)


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    # remove from any session and notify
    for session, participants in list(sessions.items()):
        if sid in participants:
            participants.pop(sid, None)
            emit("peer_left", {"sid": sid}, room=session)
            # if empty session, optionally delete it
            if not participants:
                sessions.pop(session, None)
            break


if __name__ == "__main__":
    # Install eventlet: `pip install eventlet` to get best performance.
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
