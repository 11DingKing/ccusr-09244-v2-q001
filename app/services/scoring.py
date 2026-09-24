from typing import Optional, Dict
from dataclasses import dataclass

from app.models import OperationData, Annotation


@dataclass
class QualityScores:
    completeness_score: float
    annotation_quality_score: float
    quality_score: float
    data_grade: str


def calculate_completeness_score(operation: OperationData) -> float:
    total_fields = 6
    score = 0.0

    if operation.motion_trajectory:
        traj = operation.motion_trajectory
        if isinstance(traj, dict):
            if traj.get("waypoints") and len(traj["waypoints"]) > 0:
                score += 0.5
            if traj.get("joint_angles"):
                score += 0.5
        else:
            score += 1.0

    if operation.perception_records:
        percep = operation.perception_records
        if isinstance(percep, dict):
            keys_count = len(percep.keys())
            score += min(1.0, keys_count / 5)
        else:
            score += 1.0

    if operation.grasp_result:
        score += 1.0
    if operation.environment_conditions:
        score += 1.0
    if operation.hardware_status:
        score += 1.0
    if operation.duration_ms:
        score += 1.0

    return round(score / total_fields, 4)


def calculate_annotation_quality_score(annotation: Optional[Annotation]) -> float:
    if not annotation:
        return 0.0

    base = 0.6
    if annotation.review_status == "approved":
        base += 0.2
    if annotation.annotation_quality_score is not None:
        base = annotation.annotation_quality_score
    elif annotation.failure_category and annotation.failure_description:
        base += 0.2
    return min(1.0, base)


def determine_grade(quality_score: float, thresholds: Dict[str, float]) -> str:
    if quality_score >= thresholds.get("grade_a", 0.9):
        return "A"
    elif quality_score >= thresholds.get("grade_b", 0.7):
        return "B"
    elif quality_score >= thresholds.get("grade_c", 0.5):
        return "C"
    else:
        return "D"


def compute_operation_quality(
    operation: OperationData,
    annotation: Optional[Annotation],
    completeness_weight: float,
    annotation_weight: float,
    thresholds: Dict[str, float]
) -> QualityScores:
    completeness = calculate_completeness_score(operation)
    annotation_quality = calculate_annotation_quality_score(annotation)

    quality_score = (completeness * completeness_weight +
                     annotation_quality * annotation_weight)
    quality_score = round(quality_score, 4)
    grade = determine_grade(quality_score, thresholds)

    return QualityScores(
        completeness_score=round(completeness, 4),
        annotation_quality_score=round(annotation_quality, 4),
        quality_score=quality_score,
        data_grade=grade
    )
