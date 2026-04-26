from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from retrieval import retrieve_external_evidence
from schemas import ExternalEvidenceArtifact, ExternalEvidenceTask

load_dotenv()

app = FastAPI(title="Counterclaim External Evidence Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/run", response_model=ExternalEvidenceArtifact)
async def run(task: ExternalEvidenceTask):
    return retrieve_external_evidence(task)

@app.get("/health")
def health():
    return {"status": "ok"}
