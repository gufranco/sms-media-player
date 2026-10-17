from smsggmedia import smscolor


class TestConstants:
    def test_cram_holds_two_palettes_of_sixteen(self):
        # Arrange
        expected = (16, 2, 32)

        # Act
        result = (smscolor.PALETTE_ENTRIES, smscolor.PALETTE_COUNT, smscolor.CRAM_BYTES)

        # Assert
        assert result == expected
