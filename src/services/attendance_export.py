from io import BytesIO

import pandas as pd


def attendance_workbook_bytes(attendance_df: pd.DataFrame) -> bytes:
    buffer = BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        attendance_df.to_excel(
            writer,
            index=False,
            sheet_name="Attendance"
        )
        worksheet = writer.sheets["Attendance"]

        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"

    return buffer.getvalue()
