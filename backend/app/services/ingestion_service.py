
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
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


BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "storage" / "uploads"

BATCH_SIZE = 1000


def make_unique_headers(values: list[Any]) -> list[str]:
    """Convert spreadsheet headings into unique column names."""

    headers = []
    used = set()

    for index, value in enumerate(values):
        if pd.isna(value) or not str(value).strip():
            base = f"unnamed_column_{index + 1}"
        else:
            base = str(value).strip()

        name = base
        suffix = 2

        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1

        used.add(name)
        headers.append(name)

    return headers


def to_json_value(value: Any) -> Any:
    """Convert pandas and NumPy values into JSON-compatible values."""

    if value is None or value is pd.NA or value is pd.NaT:
        return None

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()

    if isinstance(value, np.generic):
        value = value.item()

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None

    if pd.isna(value):
        return None

    return value


def infer_data_type(series: pd.Series) -> str:
    """Infer a basic database-independent column data type."""

    dtype = series.dtype

    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"

    if pd.api.types.is_integer_dtype(dtype):
        return "integer"

    if pd.api.types.is_float_dtype(dtype):
        return "float"

    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime"

    return "string"


def extract_sheet_data(
    raw_df: pd.DataFrame,
) -> tuple[list[str], pd.DataFrame, list[int]]:
    """
    Use the first non-empty row as the header.

    Returns:
        headers
        data rows
        original spreadsheet row numbers
    """

    if raw_df.empty:
        return [], pd.DataFrame(), []

    header_index = None

    for index, row in raw_df.iterrows():
        if not row.isna().all():
            header_index = index
            break

    if header_index is None:
        return [], pd.DataFrame(), []

    headers = make_unique_headers(
        raw_df.iloc[header_index].tolist()
    )

    data = raw_df.iloc[header_index + 1:].copy()
    data.columns = headers

    # Remove completely empty rows while preserving Excel row numbers.
    non_empty = ~data.isna().all(axis=1)

    original_row_numbers = [
        int(index) + 1
        for index in data.index[non_empty]
    ]

    data = data.loc[non_empty].reset_index(drop=True)

    return headers, data, original_row_numbers


def read_uploaded_file(
    file_path: Path,
    extension: str,
) -> dict[str, pd.DataFrame]:
    """Read an uploaded file and return its worksheets."""

    if extension == ".csv":
        try:
            df = pd.read_csv(
                file_path,
                header=None,
                dtype=object,
                encoding="utf-8-sig",
                sep=None,
                engine="python",
            )
        except UnicodeDecodeError:
            df = pd.read_csv(
                file_path,
                header=None,
                dtype=object,
                encoding="cp1252",
                sep=None,
                engine="python",
            )

        return {file_path.stem: df}

    if extension in {".xlsx", ".xlsm"}:
        excel_file = pd.ExcelFile(
            file_path,
            engine="openpyxl",
        )

    elif extension == ".xls":
        excel_file = pd.ExcelFile(
            file_path,
            engine="xlrd",
        )

    else:
        raise ValueError("Unsupported file format.")

    return {
        sheet_name: excel_file.parse(
            sheet_name=sheet_name,
            header=None,
            dtype=object,
        )
        for sheet_name in excel_file.sheet_names
    }


def save_uploaded_file(
    filename: str,
    file_bytes: bytes,
) -> tuple[Path, str]:
    """Save the original file using a generated unique filename."""

    extension = Path(filename).suffix.lower()

    allowed_extensions = {
        ".xlsx",
        ".xlsm",
        ".xls",
        ".csv",
    }

    if extension not in allowed_extensions:
        raise ValueError("Only XLSX, XLSM, XLS and CSV files are supported.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / stored_name

    file_path.write_bytes(file_bytes)

    return file_path, extension


def ingest_dataset(
    db: Session,
    filename: str,
    dataset_name: str,
    file_bytes: bytes,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Process a file and persist its contents in PostgreSQL."""

    file_path = None

    try:
        file_path, extension = save_uploaded_file(
            filename,
            file_bytes,
        )

        workbook = read_uploaded_file(
            file_path,
            extension,
        )

        dataset = Dataset(
            user_id=user_id,
            name=dataset_name,
            original_filename=Path(filename).name,
            file_type=extension.lstrip("."),
            storage_path=str(file_path.relative_to(BACKEND_DIR)),
            file_size=len(file_bytes),
            status="processing",
        )

        db.add(dataset)
        db.flush()

        total_rows = 0
        total_columns = 0
        sheet_results = []

        for sheet_index, (sheet_name, raw_df) in enumerate(
            workbook.items()
        ):
            headers, data, row_numbers = extract_sheet_data(raw_df)

            sheet = DatasetSheet(
                dataset_id=dataset.id,
                sheet_name=sheet_name,
                sheet_index=sheet_index,
                row_count=len(data),
                column_count=len(headers),
            )

            db.add(sheet)
            db.flush()

            columns = []

            for column_index, column_name in enumerate(headers):
                series = data[column_name]

                non_null_values = series.dropna()

                columns.append(
                    DatasetColumn(
                        sheet_id=sheet.id,
                        column_name=column_name,
                        column_index=column_index,
                        data_type=infer_data_type(series),
                        is_unique=(
                            non_null_values.nunique()
                            == len(non_null_values)
                        ),
                        null_count=int(series.isna().sum()),
                    )
                )

            db.add_all(columns)

            records = []

            for row_index, (_, row) in enumerate(
                data.iterrows()
            ):
                record_data = {
                    column: to_json_value(row[column])
                    for column in headers
                }

                records.append({
                    "sheet_id": sheet.id,
                    "row_index": row_numbers[row_index],
                    "data": record_data,
                })

                if len(records) >= BATCH_SIZE:
                    db.execute(
                        insert(DatasetRecord),
                        records,
                    )
                    records.clear()

            if records:
                db.execute(
                    insert(DatasetRecord),
                    records,
                )

            total_rows += len(data)
            total_columns += len(headers)

            sheet_results.append({
                "sheet_name": sheet_name,
                "rows": len(data),
                "columns": len(headers),
            })

        dataset.row_count = total_rows
        dataset.column_count = total_columns
        dataset.status = "completed"

        db.commit()

        return {
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "filename": filename,
            "total_rows": total_rows,
            "total_columns": total_columns,
            "total_sheets": len(sheet_results),
            "sheets": sheet_results,
            "status": dataset.status,
        }

    except Exception:
        db.rollback()

        if file_path and file_path.exists():
            file_path.unlink()

        raise
