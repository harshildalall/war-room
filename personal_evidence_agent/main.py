from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class RunRequest(BaseModel):
    case_id: str

@app.post("/run")
async def run(req: RunRequest):
    return {"case_id": req.case_id, "status": "not implemented"}

@app.get("/health")
def health():
    return {"status": "ok"}
