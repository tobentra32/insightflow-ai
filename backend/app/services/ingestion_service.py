
import math
import numbers
import os
import time

from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

import numpy as np
import pandas as pd

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import (
    Dataset,
    DatasetSheet,
    DatasetColumn,
    DatasetRecord,
)
from app.services.audit import record_audit_changes


BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "storage" / "uploads"

BATCH_SIZE = int(os.getenv("INGESTION_BATCH_SIZE", "1000"))

if BATCH_SIZE < 1:
    raise ValueError("INGESTION_BATCH_SIZE must be greater than zero.")


def make_unique_headers(headers: list[Any]) -> list[str]:
    cleaned_headers = []
    seen = {}

    for index, header in enumerate(headers):
        if pd.isna(header) or str(header).strip() == "":
            name = f"column_{index + 1}"
        else:
            name = str(header).strip()

        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1

        cleaned_headers.append(name)

    return cleaned_headers


def to_json_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()

    if isinstance(value, np.generic):
        value = value.item()

    if pd.isna(value):
        return None

    if isinstance(value, float) and not math.isfinite(value):
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def infer_data_type(series: pd.Series) -> str:
    values = series.dropna()

    if values.empty:
        return "empty"

    if pd.api.types.is_bool_dtype(values):
        return "boolean"

    if pd.api.types.is_integer_dtype(values):
        return "integer"

    if pd.api.types.is_float_dtype(values):
        return "float"

    if pd.api.types.is_datetime64_any_dtype(values):
        return "datetime"

    sample = values.head(100)

    if all(isinstance(value, bool) for value in sample):
        return "boolean"

    if all(
        isinstance(value, numbers.Integral)
        and not isinstance(value, bool)
        for value in sample
    ):
        return "integer"

    if all(
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        for value in sample
    ):
        return "float"

    if all(
        isinstance(value, (datetime, date, pd.Timestamp))
        for value in sample
    ):
        return "datetime"

    return "string"


def extract_sheet_data(
    raw_df: pd.DataFrame,
) -> tuple[list[str], pd.DataFrame, list[int]]:
    extraction_start = time.perf_counter()

    original_shape = raw_df.shape
    original_memory = raw_df.memory_usage(deep=True).sum()

    print(
        f"\nOriginal worksheet dimensions: "
        f"{original_shape[0]} rows x {original_shape[1]} columns"
    )
    print(
        f"Original DataFrame memory: "
        f"{original_memory / (1024 * 1024):.2f} MB"
    )

    step_start = time.perf_counter()
    raw_df = raw_df.dropna(axis=1, how="all")
    empty_column_removal = time.perf_counter() - step_start

    print(
        f"After removing empty columns: "
        f"{raw_df.shape[0]} rows x {raw_df.shape[1]} columns"
    )
    print(
        f"Initial empty-column removal: "
        f"{empty_column_removal:.4f}s"
    )

    step_start = time.perf_counter()
    raw_df = raw_df.replace(r"^\s*$", np.nan, regex=True)
    whitespace_cleaning = time.perf_counter() - step_start

    step_start = time.perf_counter()
    raw_df = raw_df.dropna(axis=1, how="all")
    final_column_removal = time.perf_counter() - step_start

    step_start = time.perf_counter()
    header_index = None

    for index, row in raw_df.iterrows():
        if row.notna().sum() >= 2:
            header_index = index
            break

    header_detection = time.perf_counter() - step_start

    if header_index is None:
        raise ValueError(
            "Could not identify a valid header row in this worksheet."
        )

    step_start = time.perf_counter()

    headers = make_unique_headers(
        raw_df.loc[header_index].tolist()
    )

    data = raw_df.loc[header_index + 1:].copy()
    data.columns = headers

    row_numbers = [
        int(index) + 1
        for index in data.index
    ]

    data_extraction = time.perf_counter() - step_start

    step_start = time.perf_counter()

    non_empty_mask = data.notna().any(axis=1)
    data = data.loc[non_empty_mask].copy()

    row_numbers = [
        row_number
        for row_number, keep in zip(
            row_numbers,
            non_empty_mask.tolist(),
        )
        if keep
    ]

    empty_record_removal = time.perf_counter() - step_start

    total_duration = time.perf_counter() - extraction_start

    print("\n---------- EXTRACTION PERFORMANCE ----------")
    print(f"Initial empty-column removal: {empty_column_removal:.4f}s")
    print(f"Whitespace cleaning: {whitespace_cleaning:.4f}s")
    print(f"Final empty-column removal: {final_column_removal:.4f}s")
    print(f"Header detection: {header_detection:.4f}s")
    print(f"Data extraction: {data_extraction:.4f}s")
    print(f"Empty record removal: {empty_record_removal:.4f}s")
    print(f"Total extraction: {total_duration:.4f}s")
    print("---------------------------------------------\n")

    return headers, data, row_numbers


def iter_uploaded_sheets(
    file_path: Path,
) -> Iterator[tuple[str, pd.DataFrame]]:
    extension = file_path.suffix.lower()

    if extension == ".csv":
        try:
            df = pd.read_csv(
                file_path,
                dtype=object,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
                header=None,
            )
        except UnicodeDecodeError:
            df = pd.read_csv(
                file_path,
                dtype=object,
                sep=None,
                engine="python",
                encoding="cp1252",
                header=None,
            )

        yield file_path.stem, df
        return

    engine = "xlrd" if extension == ".xls" else "openpyxl"

    with pd.ExcelFile(file_path, engine=engine) as excel_file:
        for sheet_name in excel_file.sheet_names:
            read_start = time.perf_counter()

            df = excel_file.parse(
                sheet_name=sheet_name,
                header=None,
                dtype=object,
            )

            read_duration = time.perf_counter() - read_start

            print(
                f"Worksheet '{sheet_name}' read in "
                f"{read_duration:.4f}s"
            )

            yield sheet_name, df
            del df


def save_uploaded_file(uploaded_file) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    extension = Path(uploaded_file.filename).suffix.lower()
    file_path = UPLOAD_DIR / f"{uuid4()}{extension}"

    with file_path.open("wb") as destination:
        while chunk := uploaded_file.file.read(1024 * 1024):
            destination.write(chunk)

    uploaded_file.file.seek(0)

    return file_path


def ingest_dataset(
    db: Session,
    uploaded_file,
    dataset_name: str | None = None,
    user_id: int | None = None,
    department_id: int | None = None,
) -> dict:
    ingestion_start = time.perf_counter()
    uploaded_path = None

    total_rows = 0
    total_columns = 0
    total_sheets = 0

    total_extraction_duration = 0.0
    total_insert_duration = 0.0

    try:
        uploaded_path = save_uploaded_file(uploaded_file)
        file_size = uploaded_path.stat().st_size

        dataset = Dataset(
            user_id=user_id,
            department_id=department_id,
            name=dataset_name or uploaded_file.filename,
            original_filename=uploaded_file.filename,
            file_type=uploaded_path.suffix.lower().replace(".", ""),
            storage_path=str(uploaded_path),
            file_size=file_size,
            status="processing",
        )

        db.add(dataset)
        db.flush()

        for sheet_index, (sheet_name, raw_df) in enumerate(
            iter_uploaded_sheets(uploaded_path)
        ):
            sheet_start = time.perf_counter()

            print(f"\nProcessing worksheet: {sheet_name}")
            total_sheets += 1

            extraction_start = time.perf_counter()

            headers, data, row_numbers = extract_sheet_data(raw_df)

            extraction_duration = (
                time.perf_counter() - extraction_start
            )
            total_extraction_duration += extraction_duration

            del raw_df

            sheet = DatasetSheet(
                dataset_id=dataset.id,
                sheet_name=sheet_name,
                sheet_index=sheet_index,
                row_count=len(data),
                column_count=len(headers),
            )

            db.add(sheet)
            db.flush()

            column_objects = []

            for column_index, column_name in enumerate(headers):
                series = data[column_name]
                non_null_values = series.dropna()

                column_objects.append(
                    DatasetColumn(
                        sheet_id=sheet.id,
                        column_name=column_name,
                        column_index=column_index,
                        data_type=infer_data_type(series),
                        null_count=int(series.isna().sum()),
                        is_unique=(
                            len(non_null_values) > 0
                            and non_null_values.is_unique
                        ),
                    )
                )

            db.add_all(column_objects)

            insert_start = time.perf_counter()
            batch_records = []

            for row_index, values in zip(
                row_numbers,
                data.itertuples(index=False, name=None),
            ):
                record_data = {
                    column: to_json_value(value)
                    for column, value in zip(headers, values)
                }

                batch_records.append(
                    {
                        "sheet_id": sheet.id,
                        "row_index": row_index,
                        "data": record_data,
                    }
                )

                if len(batch_records) >= BATCH_SIZE:
                    db.execute(
                        insert(DatasetRecord),
                        batch_records,
                    )
                    batch_records.clear()

            if batch_records:
                db.execute(
                    insert(DatasetRecord),
                    batch_records,
                )

            insert_duration = time.perf_counter() - insert_start
            total_insert_duration += insert_duration

            sheet_rows = len(data)
            sheet_columns = len(headers)

            total_rows += sheet_rows
            total_columns += sheet_columns

            sheet_duration = time.perf_counter() - sheet_start

            print(f"Worksheet completed: {sheet_name}")
            print(f"Rows: {sheet_rows} | Columns: {sheet_columns}")
            print(
                f"Extraction: {extraction_duration:.4f}s | "
                f"Insertion: {insert_duration:.4f}s"
            )
            print(f"Worksheet total: {sheet_duration:.4f}s")

            del data
            del row_numbers
            del headers
            del column_objects

        dataset.row_count = total_rows
        dataset.column_count = total_columns
        dataset.status = "completed"

        if user_id is not None:
            record_audit_changes(
                db,
                user_id=user_id,
                entity_type="dataset",
                entity_id=dataset.id,
                action="created",
                changes={
                    "name": (None, dataset.name),
                    "owner_user_id": (None, dataset.user_id),
                    "department_id": (None, dataset.department_id),
                    "original_filename": (
                        None,
                        dataset.original_filename,
                    ),
                    "file_type": (None, dataset.file_type),
                    "file_size": (None, dataset.file_size),
                    "row_count": (None, dataset.row_count),
                    "column_count": (None, dataset.column_count),
                    "status": (None, dataset.status),
                },
            )

        db.commit()
        db.refresh(dataset)

        total_duration = time.perf_counter() - ingestion_start

        print("\n========== INGESTION SUMMARY ==========")
        print(f"Worksheets: {total_sheets}")
        print(f"Total rows: {total_rows}")
        print(f"Total columns: {total_columns}")
        print(f"Total extraction: {total_extraction_duration:.4f}s")
        print(f"Total insertion: {total_insert_duration:.4f}s")
        print(f"Total ingestion: {total_duration:.4f}s")
        print("=======================================\n")

        return {
            "dataset_id": dataset.id,
            "name": dataset.name,
            "filename": dataset.original_filename,
            "status": dataset.status,
            "department_id": dataset.department_id,
            "user_id": dataset.user_id,
            "sheet_count": total_sheets,
            "row_count": total_rows,
            "column_count": total_columns,
        }

    except Exception:
        db.rollback()

        if uploaded_path and uploaded_path.exists():
            uploaded_path.unlink()

        raise
