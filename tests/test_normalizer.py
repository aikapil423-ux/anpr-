"""
Unit tests for Indian License Plate Normalizer and Validator
"""
from src.ocr.normalizer import IndianPlateNormalizer

def test_standard_valid_plates():
    normalizer = IndianPlateNormalizer()
    
    valid_samples = [
        ("MH12DE1433", "MH12DE1433"),
        ("DL01AB1234", "DL01AB1234"),
        ("KA05M9876", "KA05M9876"),
        ("HR26DQ5555", "HR26DQ5555"),
        ("TN09BK2020", "TN09BK2020")
    ]
    for raw, expected in valid_samples:
        is_valid, fmt, norm = normalizer.validate(raw)
        assert is_valid, f"Expected {raw} to be valid"
        assert norm == expected
        assert fmt == "standard"

def test_bh_series_plates():
    normalizer = IndianPlateNormalizer()
    
    bh_samples = [
        ("22BH1234AA", "22BH1234AA"),
        ("23BH5678B", "23BH5678B")
    ]
    for raw, expected in bh_samples:
        is_valid, fmt, norm = normalizer.validate(raw)
        assert is_valid
        assert norm == expected
        assert fmt == "bh_series"

def test_hsrp_ind_strip():
    normalizer = IndianPlateNormalizer()
    # Test prefix IND
    is_valid, fmt, norm = normalizer.validate("INDMH12DE1433")
    assert is_valid
    assert norm == "MH12DE1433"

    # Test suffix IND (the exact issue reported by user)
    is_valid, fmt, norm = normalizer.validate("MH12DE1433IND")
    assert is_valid
    assert norm == "MH12DE1433"
    assert normalizer.format_display("MH12DE1433IND") == "MH 12 DE 1433"

def test_optical_character_repair():
    normalizer = IndianPlateNormalizer()
    
    # 'I' in number position -> '1'
    is_valid, fmt, norm = normalizer.validate("MHI2DEI433")
    assert is_valid
    assert norm == "MH12DE1433"

    # 'O' in number position -> '0'
    is_valid, fmt, norm = normalizer.validate("DL01AB1234")
    assert is_valid
    assert norm == "DL01AB1234"

    # '8' in 'BH' position -> 'B'
    is_valid, fmt, norm = normalizer.validate("228H1234AA")
    assert is_valid
    assert norm == "22BH1234AA"

def test_invalid_plates():
    normalizer = IndianPlateNormalizer()
    
    invalid_samples = [
        "HELLO",              # Too short, no numbers (len 5)
        "HR26A1",             # Too short (len 6 < 9)
        "XYZ9999",            # Too short (len 7 < 9)
        "DL4S123",            # Too short (len 7 < 9)
        "HR06BG66",           # Too short (len 8 < 9)
        "1234567890",         # All numbers
        "ABCDEFGHIJ",         # All letters
        "DL01ABCDE1234",     # Too long (len 13 > 11)
        "MH12DE1433999"       # Too long (len 13 > 11)
    ]
    for sample in invalid_samples:
        is_valid, fmt, norm = normalizer.validate(sample)
        assert not is_valid, f"Expected {sample} to be invalid"

def test_display_formatting():
    normalizer = IndianPlateNormalizer()
    assert normalizer.format_display("MH12DE1433") == "MH 12 DE 1433"
    assert normalizer.format_display("22BH1234AA") == "22 BH 1234 AA"

def test_levenshtein_similarity():
    normalizer = IndianPlateNormalizer()
    sim_exact = normalizer.calculate_levenshtein("MH12DE1433", "MH12DE1433")
    assert sim_exact == 1.0

    sim_close = normalizer.calculate_levenshtein("MH12DE1433", "MH12DE1438")
    assert sim_close >= 0.90

    sim_diff = normalizer.calculate_levenshtein("MH12DE1433", "DL01AB9999")
    assert sim_diff < 0.40

def test_motorcycle_variable_digit_plates():
    normalizer = IndianPlateNormalizer()
    # Plates within the strict 9 to 11 length range
    samples = [
        ("HR06AU992", "HR06AU992", "HR 06 AU 992"),       # 9 chars
        ("DL01ABC1234", "DL01ABC1234", "DL 01 ABC 1234"), # 11 chars
        ("HRO6AU992", "HR06AU992", "HR 06 AU 992"),       # 9 chars (with optical repair of 'O' in RTO)
        ("DL3CCY7011", "DL3CCY7011", "DL 3 CCY 7011"),    # 10 chars (Delhi 1-digit RTO + 3 letters)
        ("DL3CCY7O11", "DL3CCY7011", "DL 3 CCY 7011"),    # 10 chars (with optical repair of 'O' in number)
        ("DL4SAY1234", "DL4SAY1234", "DL 4 SAY 1234"),    # 10 chars (Delhi 1-digit RTO + Scooter category)
    ]
    for raw, expected_norm, expected_display in samples:
        is_valid, fmt, norm = normalizer.validate(raw)
        assert is_valid, f"Expected {raw} to be valid"
        assert norm == expected_norm, f"Expected {expected_norm}, got {norm}"
        assert fmt == "standard"
        assert normalizer.format_display(raw) == expected_display
