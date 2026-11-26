import unittest
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from src.services.attendance_export import attendance_workbook_bytes


class AttendanceExportTests(unittest.TestCase):
    def test_user_supplied_formula_text_is_saved_as_literal_text(self):
        formula_text = '=HYPERLINK("https://example.invalid","Open")'
        attendance = pd.DataFrame(
            [{
                "Date": "2026-11-26",
                "USN": "2BL24CI028",
                "Student Name": formula_text,
                "Attendance": "Present"
            }]
        )

        workbook_bytes = attendance_workbook_bytes(attendance)
        workbook = load_workbook(
            BytesIO(workbook_bytes),
            data_only=False
        )
        worksheet = workbook["Attendance"]
        name_cell = worksheet["C2"]

        self.assertEqual(name_cell.value, formula_text)
        self.assertEqual(name_cell.data_type, "s")
        self.assertEqual(worksheet["A1"].value, "Date")
        self.assertEqual(worksheet["B1"].value, "USN")
        self.assertEqual(worksheet["B2"].value, "2BL24CI028")


if __name__ == "__main__":
    unittest.main()
