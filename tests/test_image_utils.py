import io
import unittest

from PIL import Image

from src.pipelines.image_utils import process_and_optimize_image, validate_image_file


class ImageUtilsTests(unittest.TestCase):
    def test_validate_and_process_mpo_image(self):
        first_frame = Image.new("RGB", (12, 8), "red")
        second_frame = Image.new("RGB", (12, 8), "blue")
        buffer = io.BytesIO()
        first_frame.save(buffer, format="MPO", save_all=True, append_images=[second_frame])
        image_data = buffer.getvalue()

        is_valid, error = validate_image_file(image_data, filename="sample.mpo")
        self.assertTrue(is_valid, error)

        processed_image, error = process_and_optimize_image(image_data)
        self.assertIsNone(error)
        self.assertIsNotNone(processed_image)
        self.assertEqual(processed_image.size, (12, 8))
        red, green, blue = processed_image.getpixel((0, 0))
        self.assertGreater(red, 240)
        self.assertLess(green, 10)
        self.assertLess(blue, 10)


if __name__ == "__main__":
    unittest.main()
