"""EDAPT v2 — Data Ingestion router"""

import io

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.routes.auth import get_current_user
from app.core.audit import append_event
from app.db.models import User

router = APIRouter()


@router.post("")
async def ingest_dataset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in {"csv", "xlsx", "json"}:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload .csv, .xlsx, or .json.",
        )

    content = await file.read()
    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(content))
        elif ext == "xlsx":
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_json(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {exc}")

    row_count = len(df)
    columns   = list(df.columns)
    preview   = df.head(10).fillna("").to_dict(orient="records")

    append_event(
        user_uid=current_user.email,
        role=current_user.role,
        action_type="Data Upload",
        status="Success",
        detail=f"Uploaded {file.filename} — {row_count:,} rows ingested",
    )

    return {"row_count": row_count, "columns": columns, "preview": preview}
