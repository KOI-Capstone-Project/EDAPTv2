"""EDAPT v2 — Predictions router (Mode 2: ML Pass/Fail predictions)"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("/")
async def list_predictions(
    trimester_id: int | None = Query(None, description="Filter by trimester"),
    model_version: str | None = Query(None, description="Filter by model version"),
    db: AsyncSession = Depends(get_db),
):
    """Return stored ML predictions for a given trimester + model version."""
    return {"message": "predictions endpoint — coming soon"}


@router.post("/run")
async def run_predictions(
    trimester_id: int = Query(..., description="Target trimester ID (T3 2025)"),
    model_version: str = Query("rf_v1", description="Model version tag"),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger ML inference for the target trimester.
    Loads the trained model from disk, runs predict_proba on enrolled
    students, persists results to the Prediction table, and returns a summary.
    """
    # TODO: load model via app.ml.predictor and write to DB
    return {
        "message": "ML inference triggered — coming soon",
        "trimester_id": trimester_id,
        "model_version": model_version,
    }


@router.get("/{student_masked_id}")
async def get_student_prediction(
    student_masked_id: int,
    trimester_id: int = Query(...),
    model_version: str = Query("rf_v1"),
    db: AsyncSession = Depends(get_db),
):
    """Return the prediction + Gemini insight for a single student."""
    return {
        "student_masked_id": student_masked_id,
        "message": "student prediction — coming soon",
    }
