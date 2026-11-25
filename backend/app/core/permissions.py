
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.dataset_sheet import DatasetSheet
from app.models.user import User


def get_accessible_dataset(
    db: Session,
    dataset_id: int,
    current_user: User,
) -> Dataset:
    dataset = db.get(Dataset, dataset_id)

    if dataset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    if current_user.role == "admin":
        return dataset

    if (
        current_user.department_id is None
        or dataset.department_id is None
        or dataset.department_id != current_user.department_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    return dataset


def get_accessible_sheet(
    db: Session,
    sheet_id: int,
    current_user: User,
) -> tuple[DatasetSheet, Dataset]:
    sheet = db.get(DatasetSheet, sheet_id)

    if sheet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Worksheet not found.",
        )

    dataset = get_accessible_dataset(
        db=db,
        dataset_id=sheet.dataset_id,
        current_user=current_user,
    )

    return sheet, dataset


def require_dataset_editor(
    dataset: Dataset,
    current_user: User,
) -> None:
    if current_user.role == "admin":
        return

    if dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the original uploader or an administrator can modify this dataset.",
        )
