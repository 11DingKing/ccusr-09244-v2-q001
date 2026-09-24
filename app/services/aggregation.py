from typing import List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session

from app.models import OperationData, Annotation, Dataset
from app.schemas.dataset import DataGradeStats


@dataclass
class AnnotationSummary:
    annotated_count: int
    success_count: int
    failure_count: int


@dataclass
class DatasetSummary:
    dataset_count: int
    total_reuse_count: int
    reuse_rate: float


@dataclass
class OperationsGroupStats:
    total_data_count: int
    annotation: AnnotationSummary
    annotation_complete_rate: float
    datasets: DatasetSummary
    grade_distribution: List[DataGradeStats]


@dataclass
class DatasetQualityStats:
    success_count: int
    failure_count: int
    annotation_complete_rate: float
    average_quality_score: Optional[float]
    data_grade: Optional[str]


def compute_annotation_summary(
    db: Session,
    operation_ids: List[int]
) -> AnnotationSummary:
    if not operation_ids:
        return AnnotationSummary(
            annotated_count=0,
            success_count=0,
            failure_count=0
        )

    annotations = db.query(Annotation).filter(
        Annotation.operation_data_id.in_(operation_ids)
    ).all()

    annotated_count = len(annotations)
    success_count = sum(1 for a in annotations if a.is_success)
    failure_count = sum(1 for a in annotations if not a.is_success)

    return AnnotationSummary(
        annotated_count=annotated_count,
        success_count=success_count,
        failure_count=failure_count
    )


def compute_grade_distribution(
    operations: List[OperationData],
    total_data: int
) -> List[DataGradeStats]:
    if not operations:
        return []

    grade_counts = {}
    for op in operations:
        g = op.data_grade or "未分级"
        grade_counts[g] = grade_counts.get(g, 0) + 1

    distribution = []
    for grade, count in grade_counts.items():
        distribution.append(DataGradeStats(
            grade=grade,
            count=count,
            percentage=round(count / total_data, 4) if total_data > 0 else 0.0
        ))
    return distribution


def compute_dataset_summary(
    datasets: List[Dataset]
) -> DatasetSummary:
    dataset_count = len(datasets)
    total_reuse = sum(d.reuse_count or 0 for d in datasets)

    reuse_rate = 0.0
    if dataset_count > 0:
        reused_datasets = sum(1 for d in datasets if (d.reuse_count or 0) > 0)
        reuse_rate = round(reused_datasets / dataset_count, 4)

    return DatasetSummary(
        dataset_count=dataset_count,
        total_reuse_count=total_reuse,
        reuse_rate=reuse_rate
    )


def compute_group_stats(
    db: Session,
    operations: List[OperationData],
    datasets: List[Dataset],
    include_grade_distribution: bool = True
) -> OperationsGroupStats:
    total_data = len(operations)
    op_ids = [op.id for op in operations]

    annotation_summary = compute_annotation_summary(db, op_ids)
    annotation_complete_rate = (
        round(annotation_summary.annotated_count / total_data, 4)
        if total_data > 0 else 0.0
    )

    dataset_summary = compute_dataset_summary(datasets)

    grade_distribution = (
        compute_grade_distribution(operations, total_data)
        if include_grade_distribution else []
    )

    return OperationsGroupStats(
        total_data_count=total_data,
        annotation=annotation_summary,
        annotation_complete_rate=annotation_complete_rate,
        datasets=dataset_summary,
        grade_distribution=grade_distribution
    )


def compute_dataset_quality_stats(
    db: Session,
    operation_ids: List[int]
) -> DatasetQualityStats:
    if not operation_ids:
        return DatasetQualityStats(
            success_count=0,
            failure_count=0,
            annotation_complete_rate=0.0,
            average_quality_score=None,
            data_grade=None
        )

    annotations = db.query(Annotation).filter(
        Annotation.operation_data_id.in_(operation_ids)
    ).all()

    success_count = sum(1 for a in annotations if a.is_success)
    failure_count = sum(1 for a in annotations if not a.is_success)
    annotation_complete_rate = len(annotations) / len(operation_ids) if operation_ids else 0.0

    quality_scores = []
    ops = db.query(OperationData).filter(OperationData.id.in_(operation_ids)).all()
    for op in ops:
        if op.quality_score is not None:
            quality_scores.append(op.quality_score)
    average_quality_score = (
        sum(quality_scores) / len(quality_scores) if quality_scores else None
    )

    grade_counts = {}
    for op in ops:
        if op.data_grade:
            grade_counts[op.data_grade] = grade_counts.get(op.data_grade, 0) + 1
    data_grade = max(grade_counts, key=grade_counts.get) if grade_counts else None

    return DatasetQualityStats(
        success_count=success_count,
        failure_count=failure_count,
        annotation_complete_rate=annotation_complete_rate,
        average_quality_score=average_quality_score,
        data_grade=data_grade
    )
