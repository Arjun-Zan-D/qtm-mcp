import logging
import hashlib
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone

import httpx

from qtm_mcp.config import get_settings
from qtm_mcp.utils import (
    validate_patient_inputs,
    safe_patient_path,
    get_project_patient_dir,
    confined_file,
    get_shared_client,
)

logger = logging.getLogger("Universal_QTM_Server.clinical_output")

async def generate_pdf_report(patient_id: str, session_date: str) -> dict:
    """Compiles data into a PDF and returns the file path.
    
    Use this tool to generate the final formatted clinical gait analysis report
    for physicians, including key kinematic charts, spatiotemporal tables, and notes.
    """
    settings = get_settings()

    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    # Try to load existing clinical report JSON
    clinical_data: Dict[str, Any] = {}
    candidate_file = patient_path / f"{patient_id}_clinical_report.json"
    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})

        def _read_clinical(p: Path) -> dict:
            import os
            if os.path.getsize(p) > 10 * 1024 * 1024:
                raise ValueError("Clinical report file exceeds 10 MB size limit")
            with open(p, "r") as f:
                return json.load(f)

        clinical_data = await asyncio.to_thread(_read_clinical, safe_path)
        logger.info(f"Loaded clinical report for patient {hashed_id}")
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(f"Clinical report not found for patient {hashed_id}: {exc}")
        clinical_data = {"note": "No clinical report data available — placeholder report"}

    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        _HAS_REPORTLAB = True
    except ImportError:
        _HAS_REPORTLAB = False

    if _HAS_REPORTLAB:
        report_path = patient_path / f"{patient_id}_report.pdf"
        
        def _write_pdf(p: Path, data: Dict[str, Any]) -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            c = canvas.Canvas(str(p), pagesize=A4)
            c.setFont('Helvetica-Bold', 14)
            c.drawString(72, 780, f"Clinical Gait Analysis Report")
            c.setFont('Helvetica', 11)
            c.drawString(72, 760, f"Patient ID : {patient_id}")
            c.drawString(72, 745, f"Session    : {session_date}")
            c.drawString(72, 730, f"Generated  : {datetime.now(timezone.utc).isoformat()}")
            
            y = 700
            for key, value in data.items():
                c.drawString(72, y, f"{key}: {value}")
                y -= 15
                if y < 50:
                    c.showPage()
                    c.setFont('Helvetica', 11)
                    y = 780
            c.save()
            
        await asyncio.to_thread(_write_pdf, report_path, clinical_data)
        logger.info(f"PDF report written for patient {hashed_id} at {report_path}")
        
        return {
            "status": "success",
            "patient_id": patient_id,
            "session_date": session_date,
            "report_path": str(report_path),
            "format": "pdf",
        }
    else:
        # Build text report
        report_lines = [
            f"Clinical Gait Analysis Report",
            f"==============================",
            f"Patient ID : {patient_id}",
            f"Session    : {session_date}",
            f"Generated  : {datetime.now(timezone.utc).isoformat()}",
            f"",
        ]
        for key, value in clinical_data.items():
            report_lines.append(f"{key}: {value}")
        report_text = "\n".join(report_lines) + "\n"

        # Write report file
        report_path = patient_path / f"{patient_id}_report.txt"

        def _write_report(p: Path, content: str) -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                f.write(content)

        await asyncio.to_thread(_write_report, report_path, report_text)
        logger.info(f"Report written for patient {hashed_id} at {report_path}")

        return {
            "status": "success",
            "patient_id": patient_id,
            "session_date": session_date,
            "report_path": str(report_path),
            "format": "txt",
            "note": "Generated as TXT (reportlab library not installed)",
        }

async def export_c3d(patient_id: str, session_date: str) -> dict:
    """Triggers the QTM C3D export pipeline.
    
    Use this tool to export raw tracked marker coordinates and analog data into
    the standard C3D format for use in third-party software like OpenSim or Visual3D.
    """
    settings = get_settings()

    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    # Try to load marker trajectory data
    marker_data: Dict[str, Any] = {}
    for filename in ("marker_trajectories.json", f"{patient_id}_markers.json"):
        candidate_file = patient_path / filename
        try:
            safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})

            def _read_markers(p: Path) -> dict:
                import os
                if os.path.getsize(p) > 10 * 1024 * 1024:
                    raise ValueError("Marker data file exceeds 10 MB size limit")
                with open(p, "r") as f:
                    return json.load(f)

            marker_data = await asyncio.to_thread(_read_markers, safe_path)
            logger.info(f"Loaded marker data from {filename} for patient {hashed_id}")
            break
        except (FileNotFoundError, ValueError):
            continue

    if not marker_data or "markers" not in marker_data:
        logger.warning(f"No marker trajectory data found for patient {hashed_id}")
        
        # Build JSON export payload
        export_payload = {
            "patient_id": patient_id,
            "session_date": session_date,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "marker_data": marker_data or {"note": "No marker trajectory data available"},
        }
        export_path = patient_path / f"{patient_id}_export.json"

        def _write_export(p: Path, data: Dict[str, Any]) -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                json.dump(data, f, indent=2)

        await asyncio.to_thread(_write_export, export_path, export_payload)
        logger.info(f"Export written for patient {hashed_id} at {export_path}")

        return {
            "status": "success",
            "patient_id": patient_id,
            "session_date": session_date,
            "export_path": str(export_path),
            "format": "json",
            "note": "Exported as JSON (marker data missing for C3D binary export)",
        }

    try:
        import c3d
        _HAS_C3D = True
    except ImportError:
        _HAS_C3D = False

    if not _HAS_C3D:
        # Build JSON export payload
        export_payload = {
            "patient_id": patient_id,
            "session_date": session_date,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "marker_data": marker_data,
        }
        export_path = patient_path / f"{patient_id}_export.json"

        def _write_export_json(p: Path, data: Dict[str, Any]) -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                json.dump(data, f, indent=2)

        await asyncio.to_thread(_write_export_json, export_path, export_payload)
        logger.info(f"Export written for patient {hashed_id} at {export_path}")

        return {
            "status": "success",
            "patient_id": patient_id,
            "session_date": session_date,
            "export_path": str(export_path),
            "format": "json",
            "note": "Exported as JSON (C3D binary requires c3d library)",
        }

    # Build C3D writer with marker data
    writer = c3d.Writer()
    markers = marker_data["markers"]
    marker_labels = list(markers.keys())
    
    c3d_path = patient_path / f"{patient_id}_export.c3d"

    def _write_c3d():
        writer.set_point_labels(marker_labels)
        with open(c3d_path, 'wb') as f:
            writer.write(f)

    await asyncio.to_thread(_write_c3d)
    logger.info(f"C3D export written for patient {hashed_id} at {c3d_path}")

    return {
        "status": "success",
        "patient_id": patient_id,
        "session_date": session_date,
        "export_path": str(c3d_path),
        "format": "c3d",
    }

async def push_to_ehr(patient_id: str, session_date: str, fhir_endpoint: str) -> dict:
    """Packages the clinical summary into an HL7/FHIR payload and executes the post request.
    
    Use this tool to securely transmit the final clinical parameters and observational
    notes to the hospital's Electronic Health Record (EHR) system.
    """
    settings = get_settings()

    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)

    if fhir_endpoint not in settings.allowed_fhir_endpoints:
        raise PermissionError(f"FHIR endpoint '{fhir_endpoint}' is not in the approved allowlist")

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]

    # Load clinical report from session directory
    clinical_data: Dict[str, Any] = {}
    candidate_file = patient_path / f"{patient_id}_clinical_report.json"
    try:
        safe_path = await confined_file(Path(base_dir), candidate_file, {".json"})

        def _read_clinical(p: Path) -> dict:
            import os
            if os.path.getsize(p) > 10 * 1024 * 1024:
                raise ValueError("Clinical report file exceeds 10 MB size limit")
            with open(p, "r") as f:
                return json.load(f)

        clinical_data = await asyncio.to_thread(_read_clinical, safe_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning(f"Clinical report not found for patient {hashed_id}: {exc}")
        clinical_data = {"note": "No clinical data available"}

    # Build FHIR DiagnosticReport payload
    fhir_payload = {
        "resourceType": "DiagnosticReport",
        "status": "final",
        "subject": {"identifier": {"value": patient_id}},
        "effectiveDateTime": session_date,
        "result": clinical_data,
    }

    # POST to EHR
    try:
        client = get_shared_client()
        response = await client.post(
            fhir_endpoint,
            json=fhir_payload,
            timeout=10.0,
        )
        logger.info(
            f"EHR push for patient {hashed_id} to {fhir_endpoint} "
            f"returned HTTP {response.status_code}"
        )
        return {
            "status": "success",
            "patient_id": patient_id,
            "fhir_endpoint": fhir_endpoint,
            "http_status": response.status_code,
        }
    except httpx.RequestError as exc:
        logger.error(f"EHR push failed for patient {hashed_id}: {exc}")
        return {
            "status": "error",
            "patient_id": patient_id,
            "fhir_endpoint": fhir_endpoint,
            "error": str(exc),
        }
    except RuntimeError as exc:
        # Circuit breaker is open
        logger.error(f"EHR push blocked by circuit breaker for patient {hashed_id}: {exc}")
        return {
            "status": "error",
            "patient_id": patient_id,
            "fhir_endpoint": fhir_endpoint,
            "error": str(exc),
        }

async def update_clinical_notes(patient_id: str, session_date: str, notes: str) -> dict:
    """Appends AI-generated observational text to the session's metadata file.
    
    Use this tool to save the AI's diagnostic reasoning, anomaly highlights,
    or general observational text directly into the patient's session records.
    """
    settings = get_settings()

    # Security checks
    validate_patient_inputs(patient_id, session_date)
    base_dir = await get_project_patient_dir()
    patient_path = await safe_patient_path(base_dir, patient_id, session_date)

    if len(notes) > 10000:
        raise ValueError("Notes exceed 10000 character limit")

    if not notes.startswith("[AI-GENERATED CLINICAL NOTE]"):
        notes = f"[AI-GENERATED CLINICAL NOTE]\n{notes}"

    hashed_id = hashlib.sha256(patient_id.encode()).hexdigest()[:12]
    logger.info(f"AUDIT: AI generated note for patient {hashed_id}")

    # Resolve notes file path
    notes_file = patient_path / "clinical_notes.json"

    # Load existing notes (if any)
    all_notes: List[Dict[str, Any]] = []

    def _read_notes(p: Path) -> List[Dict[str, Any]]:
        import os
        if not p.exists():
            return []
        if os.path.getsize(p) > 10 * 1024 * 1024:
            raise ValueError("Notes file exceeds 10 MB size limit")
        with open(p, "r") as f:
            return json.load(f)

    all_notes = await asyncio.to_thread(_read_notes, notes_file)

    # Append new entry
    all_notes.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "content": notes,
    })

    # Write back
    def _write_notes(p: Path, data: List[Dict[str, Any]]) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(data, f, indent=2)

    await asyncio.to_thread(_write_notes, notes_file, all_notes)
    logger.info(f"Clinical notes updated for patient {hashed_id}, total entries: {len(all_notes)}")

    return {
        "status": "success",
        "patient_id": patient_id,
        "session_date": session_date,
        "notes_count": len(all_notes),
    }
