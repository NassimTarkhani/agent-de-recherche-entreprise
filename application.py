import asyncio
from fastapi.staticfiles import StaticFiles
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from backend.graph import Graph
from backend.services.mongodb import MongoDBService
from backend.services.pdf_service import PDFService
from backend.services.websocket_manager import WebSocketManager

# Load environment variables from .env file at startup
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
logger.addHandler(console_handler)

app = FastAPI(title="Tavily Company Research API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

manager = WebSocketManager()
pdf_service = PDFService({"pdf_output_dir": "pdfs"})

job_status = defaultdict(lambda: {
    "status": "pending",
    "result": None,
    "error": None,
    "debug_info": [],
    "company": None,
    "report": None,
    "last_update": datetime.now().isoformat()
})

mongodb = None
if mongo_uri := os.getenv("MONGODB_URI"):
    try:
        mongodb = MongoDBService(mongo_uri)
        logger.info("MongoDB integration enabled")
    except Exception as e:
        logger.warning(f"Échec de l'initialisation de MongoDB : {e}. Poursuite sans persistance.")

class ResearchRequest(BaseModel):
    company: str
    company_url: str | None = None
    industry: str | None = None
    hq_location: str | None = None

class PDFGenerationRequest(BaseModel):
    report_content: str
    company_name: str | None = None

@app.options("/research")
async def preflight():
    response = JSONResponse(content=None, status_code=200)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.post("/research")
async def research(data: ResearchRequest):
    try:
        logger.info(f"Received research request for {data.company}")
        job_id = str(uuid.uuid4())
        asyncio.create_task(process_research(job_id, data))

        response = JSONResponse(content={
            "status": "accepted",
            "job_id": job_id,
            "message": "Recherche démarrée. Connectez-vous au WebSocket pour suivre l'avancement.",
            "websocket_url": f"/research/ws/{job_id}"
        })
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    except Exception as e:
        logger.error(f"Error initiating research: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def process_research(job_id: str, data: ResearchRequest):
    try:
        if mongodb:
            mongodb.create_job(job_id, data.dict())
        await asyncio.sleep(1)  # Allow WebSocket connection

        await manager.send_status_update(job_id, status="processing", message="Starting research")

        graph = Graph(
            company=data.company,
            url=data.company_url,
            industry=data.industry,
            hq_location=data.hq_location,
            websocket_manager=manager,
            job_id=job_id
        )

        state = {}
        async for s in graph.run(thread={}):
            state.update(s)
        
        # Look for the compiled report in either location.
        report_content = state.get('report') or (state.get('editor') or {}).get('report')
        if report_content:
            logger.info(f"Found report in final state (length: {len(report_content)})")
            job_status[job_id].update({
                "status": "completed",
                "report": report_content,
                "company": data.company,
                "last_update": datetime.now().isoformat()
            })
            if mongodb:
                mongodb.update_job(job_id=job_id, status="completed")
                mongodb.store_report(job_id=job_id, report_data={"report": report_content})
            await manager.send_status_update(
                job_id=job_id,
                status="completed",
                message="Recherche terminée avec succès",
                result={
                    "report": report_content,
                    "company": data.company
                }
            )
        else:
            logger.error(f"Research completed without finding report. State keys: {list(state.keys())}")
            logger.error(f"Editor state: {state.get('editor', {})}")
            
            # Check if there was a specific error in the state
            error_message = "Aucun rapport trouvé"
            if error := state.get('error'):
                error_message = f"Erreur : {error}"
            
            await manager.send_status_update(
                job_id=job_id,
                status="failed",
                message="La recherche s'est terminée mais aucun rapport n'a été généré",
                error=error_message
            )

    except Exception as e:
        logger.error(f"La recherche a échoué : {str(e)}")
        await manager.send_status_update(
            job_id=job_id,
            status="failed",
            message=f"La recherche a échoué : {str(e)}",
            error=str(e)
        )
        if mongodb:
            mongodb.update_job(job_id=job_id, status="failed", error=str(e))
app.mount("/assets", StaticFiles(directory="ui/dist/assets"), name="assets")

@app.get("/{full_path:path}")
async def serve_static(full_path: str, request: Request):
    # Skip API routes
    if full_path.startswith("research/"):
        raise HTTPException(status_code=404)
        
    if full_path == "":
        # Serve index.html for root path
        return FileResponse("ui/dist/index.html")
    else:
        # For any other path, try to serve from the dist directory
        file_path = f"ui/dist/{full_path}"
        if os.path.exists(file_path):
            return FileResponse(file_path)
        # If file doesn't exist, return index.html for client-side routing
        return FileResponse("ui/dist/index.html")

@app.get("/research/pdf/{filename}")
async def get_pdf(filename: str):
    pdf_path = os.path.join("pdfs", filename)
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type='application/pdf', filename=filename)

@app.websocket("/research/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    try:
        await websocket.accept()
        await manager.connect(websocket, job_id)

        if job_id in job_status:
            status = job_status[job_id]
            await manager.send_status_update(
                job_id,
                status=status["status"],
                message="Connected to status stream",
                error=status["error"],
                result=status["result"]
            )

        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                manager.disconnect(websocket, job_id)
                break

    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {str(e)}", exc_info=True)
        manager.disconnect(websocket, job_id)

@app.get("/research/{job_id}")
async def get_research(job_id: str):
    if not mongodb:
        raise HTTPException(status_code=501, detail="Database persistence not configured")
    job = mongodb.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job

@app.get("/research/{job_id}/report")
async def get_research_report(job_id: str):
    if not mongodb:
        if job_id in job_status:
            result = job_status[job_id]
            if report := result.get("report"):
                return {"report": report}
        raise HTTPException(status_code=404, detail="Report not found")
    
    report = mongodb.get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Research report not found")
    return report

@app.post("/generate-pdf")
async def generate_pdf(data: PDFGenerationRequest):
    """Generate a PDF from markdown content and stream it to the client."""
    try:
        success, result = pdf_service.generate_pdf_stream(data.report_content, data.company_name)
        if success:
            pdf_buffer, filename = result
            return StreamingResponse(
                pdf_buffer,
                media_type='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}"'
                }
            )
        else:
            raise HTTPException(status_code=500, detail=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files from the UI build directory
app.mount("/assets", StaticFiles(directory="ui/dist/assets"), name="assets")

@app.get("/{full_path:path}")
async def serve_static(full_path: str, request: Request):
    if full_path == "":
        # Serve index.html for root path
        return FileResponse("ui/dist/index.html")
    else:
        # For any other path, try to serve from the dist directory
        file_path = f"ui/dist/{full_path}"
        if os.path.exists(file_path):
            return FileResponse(file_path)
        # If file doesn't exist, return index.html for client-side routing
        return FileResponse("ui/dist/index.html")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)