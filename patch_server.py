import re

with open('c:/Users/Administrator/Desktop/html_test/WebChat2Local/server/server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the dashboard endpoint with our new endpoints
dashboard_pattern = re.compile(r'@app\.get\("/", response_class=HTMLResponse\)\nasync def dashboard\(\):\n(?:.|\n)*?    """', re.MULTILINE)

new_endpoints = """
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import os
from server.tools.edit_engine import list_directory, read_file
from fastapi.responses import FileResponse

# We will serve static files from server/static
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class SessionCreate(BaseModel):
    mode: str = "ASK"

class EditProposalRequest(BaseModel):
    path: str
    content: str
    
# Store sessions and proposals simply in memory
SESSIONS = {}
PROPOSALS = {}

@app.get("/api/providers")
async def get_providers():
    return {"providers": [{"name": "mock", "active": True}]}

@app.get("/api/providers/{provider_name}/health")
async def get_provider_health(provider_name: str):
    return {"status": "ok"}

@app.post("/api/sessions")
async def create_session(session: SessionCreate):
    import uuid
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {"mode": session.mode}
    return {"session_id": session_id, "mode": session.mode}

@app.post("/api/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    if session_id in SESSIONS:
        del SESSIONS[session_id]
        return {"status": "cancelled"}
    raise HTTPException(status_code=404, detail="Session not found")

@app.post("/api/proposals/{proposal_id}/accept")
async def accept_proposal(proposal_id: str):
    if proposal_id in PROPOSALS:
        PROPOSALS[proposal_id]["status"] = "accepted"
        return {"status": "accepted"}
    raise HTTPException(status_code=404, detail="Proposal not found")

@app.post("/api/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str):
    if proposal_id in PROPOSALS:
        PROPOSALS[proposal_id]["status"] = "rejected"
        return {"status": "rejected"}
    raise HTTPException(status_code=404, detail="Proposal not found")

@app.get("/api/workspace/tree")
async def get_workspace_tree():
    workspace = os.path.dirname(os.path.dirname(__file__))
    return list_directory(workspace, ".")

@app.get("/api/workspace/file")
async def get_workspace_file(path: str):
    workspace = os.path.dirname(os.path.dirname(__file__))
    return read_file(workspace, path)

@app.post("/api/workspace/edit")
async def edit_workspace_file(req: EditProposalRequest):
    import uuid
    proposal_id = str(uuid.uuid4())
    PROPOSALS[proposal_id] = {"path": req.path, "content": req.content, "status": "pending"}
    return {"proposal_id": proposal_id}

@app.get("/studio")
async def serve_studio():
    # Return Web Studio IDE Shell HTML interface
    static_dir = os.path.join(os.path.dirname(__file__), "static", "studio")
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    # Return Dashboard
    return "<h1>Studio Dashboard</h1><a href='/studio'>Open Studio</a>"
"""

if "@app.get(\"/api/providers\")" not in content:
    content = dashboard_pattern.sub(new_endpoints, content)
    with open('c:/Users/Administrator/Desktop/html_test/WebChat2Local/server/server.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Already patched")
