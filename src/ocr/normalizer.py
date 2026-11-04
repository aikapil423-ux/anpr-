"""
Indian License Plate Normalizer and Validator Module
Handles cleaning, prefix stripping (e.g. HSRP 'IND'), character confusion repair,
Indian format regex validation (Standard & BH series), and similarity scoring.
"""
import re
from typing import Tuple, Optional
from config import NormalizerConfig

# Common optical character confusions
ALPHA_TO_NUM = {
    'O': '0', 'D': '0', 'Q': '0', 'U': '0',
    'I': '1', 'L': '1', 'l': '1', '|': '1', '/': '1', 'T': '1',
    'Z': '2',
    'E': '3',
    'A': '4',
    'S': '5',
    'G': '6', 'b': '6',
    'B': '8',
    'g': '9', 'q': '9'
}

NUM_TO_ALPHA = {
    '0': 'O',
    '1': 'I',
    '2': 'Z',
    '3': 'E',
    '4': 'A',
    '5': 'S',
    '6': 'G',
    '8': 'B'
}

# Deterministic optical state code corrections for 36 Indian states & UTs
STATE_CODE_CORRECTIONS = {
    'HB': 'HR', '4R': 'HR', '1R': 'HR', 'NR': 'HR', 'MR': 'HR',
    '0L': 'DL', 'OL': 'DL', 'D1': 'DL', 'DI': 'DL', '01': 'DL',
    'VP': 'UP', '0P': 'UP', 'OP': 'UP', '4P': 'UP',
    'P8': 'PB', 'PR': 'PB', 'FB': 'PB',
    'R1': 'RJ', 'RI': 'RJ', 'PJ': 'RJ',
    'K4': 'KA', 'KB': 'KA',
    'M0': 'MH', 'NH': 'MH',
    'G1': 'GJ', 'GI': 'GJ',
    'T5': 'TS', '7N': 'TN',
    'K1': 'KL', '8R': 'BR',
    'W8': 'WB', 'A5': 'AS',
    '0D': 'OD', 'C6': 'CG',
    'J1': 'JK', 'H1': 'HP',
    'U1': 'UK', 'UA': 'UK'
}

class IndianPlateNormalizer:
    def __init__(self, config: Optional[NormalizerConfig] = None):
        self.config = config or NormalizerConfig()
        self.state_codes = set(self.config.indian_state_codes)
        
        # Strict CMVR Indian Regex patterns
        # Strict CMVR Indian Regex patterns
        # Pattern 1 (2-digit RTO): 2 letters (State) + 2 digits (RTO) + 1-2 letters (Series) + 3-4 digits (e.g. HR26CL9999, HR06B8455, HR06AU992)
        # Pattern 2 (1-2 digit RTO - Delhi & UTs/Commercial): 2 letters (State) + 1-2 digit (RTO) + 2-3 letters (Series) + exactly 4 digits (e.g. DL3CCY7011, DL01ABC1234)
        self.standard_pattern = re.compile(
            r'^(?:[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{3,4}|[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4})$'
        )
        self.standard_pattern_2digit = re.compile(r'^[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}$')
        self.standard_pattern_1digit = re.compile(r'^[A-Z]{2}[0-9]{1}[A-Z]{2,3}[0-9]{4}$')
        # BH Series: 2 digits (Year) + "BH" + 4 digits + 1-2 letters
        self.bh_pattern = re.compile(r'^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$')
        # Legacy / Incomplete format: 1-3 digits ending (needs review)
        self.legacy_pattern = re.compile(r'^[A-Z]{2}[0-9]{1,2}[A-Z]{0,2}[0-9]{1,3}$')

    def clean_raw_text(self, text: str) -> str:
        """
        Strips whitespace, special characters, and common HSRP 'IND' watermark prefixes.
        """
        if not text:
            return ""
        # Remove non-alphanumeric
        cleaned = re.sub(r'[^A-Za-z0-9]', '', text).upper()
        
        # Strip leading 'IND' or '1ND' if present
        if (cleaned.startswith("IND") or cleaned.startswith("1ND")) and len(cleaned) >= 12:
            cleaned = cleaned[3:]

        # Strip trailing 'IND' or '1ND' if present (e.g. from HSRP badge read at end)
        if (cleaned.endswith("IND") or cleaned.endswith("1ND")) and len(cleaned) >= 12:
            cleaned = cleaned[:-3]
            
        return cleaned

    def repair_characters(self, text: str) -> str:
        """
        Position-based optical character confusion correction for Indian plates.
        Deterministic type assignment based on length (9, 10, 11) and national CMVR standards.
        """
        if len(text) < self.config.min_length or len(text) > self.config.max_length:
            return text

        chars = list(text)

        # 1. Check for BH series candidate: [0-9]{2}BH...
        if len(chars) in (9, 10) and (
            (chars[2] in ('B', '8') and chars[3] in ('H', '4')) or
            (chars[0].isdigit() and chars[1].isdigit() and chars[2] == 'B')
        ):
            # Pos 0, 1: Digits (Year)
            chars[0] = ALPHA_TO_NUM.get(chars[0], chars[0])
            chars[1] = ALPHA_TO_NUM.get(chars[1], chars[1])
            # Pos 2, 3: "BH"
            chars[2] = 'B'
            chars[3] = 'H'
            # Pos 4, 5, 6, 7: Digits (Unique)
            for i in range(4, 8):
                chars[i] = ALPHA_TO_NUM.get(chars[i], chars[i])
            # Pos 8..: Letters (Series)
            for i in range(8, len(chars)):
                chars[i] = NUM_TO_ALPHA.get(chars[i], chars[i])
            return "".join(chars)

        # 2. Standard 10-character plate:
        # Supports standard [L, L, D, D, L, L, D, D, D, D] (e.g. MH12DE1433)
        # and 1-digit RTO [L, L, D, L, L, L, D, D, D, D] (e.g. DL3CCY7011, DL4SAY1234)
        if len(chars) == 10:
            # 0, 1: State letters (strictly matched against 36 Indian states/UTs)
            chars[0] = NUM_TO_ALPHA.get(chars[0], chars[0])
            chars[1] = NUM_TO_ALPHA.get(chars[1], chars[1])
            st = "".join(chars[0:2])
            if st not in self.state_codes and st in STATE_CODE_CORRECTIONS:
                corr_st = STATE_CODE_CORRECTIONS[st]
                chars[0], chars[1] = corr_st[0], corr_st[1]

            # 2: RTO digit 1
            chars[2] = ALPHA_TO_NUM.get(chars[2], chars[2])
            # 6, 7, 8, 9: Unique number digits (strictly enforced numeric for last 4 characters)
            for i in range(6, 10):
                chars[i] = ALPHA_TO_NUM.get(chars[i], chars[i] if chars[i].isdigit() else '0')

            # Candidate A: 1-digit RTO + 3-letter category/series (e.g. DL3CCY7011)
            cand_3letter = list(chars)
            cand_3letter[3] = NUM_TO_ALPHA.get(chars[3], chars[3])
            cand_3letter[4] = NUM_TO_ALPHA.get(chars[4], chars[4])
            cand_3letter[5] = NUM_TO_ALPHA.get(chars[5], chars[5])
            s_3letter = "".join(cand_3letter)

            # Candidate B: 2-digit RTO + 2-letter series (e.g. MH12DE1433)
            cand_2digit = list(chars)
            cand_2digit[3] = ALPHA_TO_NUM.get(chars[3], chars[3])
            cand_2digit[4] = NUM_TO_ALPHA.get(chars[4], chars[4])
            cand_2digit[5] = NUM_TO_ALPHA.get(chars[5], chars[5])
            s_2digit = "".join(cand_2digit)

            # Prioritize 2-digit RTO (most common in India) if position 3 is digit-like
            if chars[3].isdigit() or chars[3] in ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'O', 'I', 'Z'):
                if self.standard_pattern.match(s_2digit) and s_2digit[:2] in self.state_codes:
                    return s_2digit

            if self.standard_pattern.match(s_3letter) and s_3letter[:2] in self.state_codes:
                return s_3letter

            if self.standard_pattern.match(s_2digit) and s_2digit[:2] in self.state_codes:
                return s_2digit

            return "".join(chars)

        # 3. Standard 9-character plate:
        # Pattern 9A: 2-digit RTO + 1-letter series + 4 digits (e.g. HR06B8455, KA05M9876)
        # Pattern 9B: 1-digit RTO + 2-letter series + 4 digits (e.g. DL1AA1234)
        # Pattern 9C: 2-digit RTO + 2-letter series + 3 digits (e.g. HR06AU992 - Motorcycle)
        if len(chars) == 9:
            # 0, 1: State letters (strictly matched against 36 Indian states/UTs)
            chars[0] = NUM_TO_ALPHA.get(chars[0], chars[0])
            chars[1] = NUM_TO_ALPHA.get(chars[1], chars[1])
            st = "".join(chars[0:2])
            if st not in self.state_codes and st in STATE_CODE_CORRECTIONS:
                corr_st = STATE_CODE_CORRECTIONS[st]
                chars[0], chars[1] = corr_st[0], corr_st[1]

            # Last 3 digits: 6, 7, 8 (always numeric)
            for i in range(6, 9):
                chars[i] = ALPHA_TO_NUM.get(chars[i], chars[i] if chars[i].isdigit() else '0')

            # Candidate 9C: 2-digit RTO + 2-letter series + 3 digits (e.g. HR06AU992)
            cand_9c = list(chars)
            cand_9c[2] = ALPHA_TO_NUM.get(chars[2], chars[2])
            cand_9c[3] = ALPHA_TO_NUM.get(chars[3], chars[3])
            cand_9c[4] = NUM_TO_ALPHA.get(chars[4], chars[4])
            cand_9c[5] = NUM_TO_ALPHA.get(chars[5], chars[5])
            s_9c = "".join(cand_9c)

            # Candidate 9A: 2-digit RTO + 1-letter series + 4 digits (e.g. HR06B8455)
            cand_9a = list(chars)
            cand_9a[2] = ALPHA_TO_NUM.get(chars[2], chars[2])
            cand_9a[3] = ALPHA_TO_NUM.get(chars[3], chars[3])
            cand_9a[4] = NUM_TO_ALPHA.get(chars[4], chars[4])
            cand_9a[5] = ALPHA_TO_NUM.get(chars[5], chars[5])
            s_9a = "".join(cand_9a)

            # Candidate 9B: 1-digit RTO + 2-letter series + 4 digits (e.g. DL1AA1234)
            cand_9b = list(chars)
            cand_9b[2] = ALPHA_TO_NUM.get(chars[2], chars[2])
            cand_9b[3] = NUM_TO_ALPHA.get(chars[3], chars[3])
            cand_9b[4] = NUM_TO_ALPHA.get(chars[4], chars[4])
            cand_9b[5] = ALPHA_TO_NUM.get(chars[5], chars[5])
            s_9b = "".join(cand_9b)

            if chars[5].isalpha() and chars[5] not in ('0', '1', 'O', 'I'):
                if self.standard_pattern.match(s_9c) and s_9c[:2] in self.state_codes:
                    return s_9c

            if self.standard_pattern.match(s_9a) and s_9a[:2] in self.state_codes:
                return s_9a
            if self.standard_pattern.match(s_9b) and s_9b[:2] in self.state_codes:
                return s_9b
            if self.standard_pattern.match(s_9c) and s_9c[:2] in self.state_codes:
                return s_9c

            return "".join(chars)

        # 4. 11-character candidate:
        # Under CMVR, a 2-digit RTO plate cannot have a 3-letter series.
        # When 11 characters are detected (e.g. HR06BMH0055), do NOT drop letters blindly into a fake plate.
        # Instead, preserve characters and flag as illegible / inconclusive for human review.
        if len(chars) == 11:
            chars[0] = NUM_TO_ALPHA.get(chars[0], chars[0])
            chars[1] = NUM_TO_ALPHA.get(chars[1], chars[1])
            chars[2] = ALPHA_TO_NUM.get(chars[2], chars[2])
            chars[3] = ALPHA_TO_NUM.get(chars[3], chars[3])
            chars[4] = NUM_TO_ALPHA.get(chars[4], chars[4])
            chars[5] = NUM_TO_ALPHA.get(chars[5], chars[5])
            chars[6] = NUM_TO_ALPHA.get(chars[6], chars[6])
            for i in range(7, 11):
                chars[i] = ALPHA_TO_NUM.get(chars[i], chars[i])
            return "".join(chars)

        return "".join(chars)

    def validate(self, plate: str) -> Tuple[bool, str, str]:
        """
        Validates if plate matches Indian CMVR standards.
        Returns:
            (is_valid: bool, format_type: str, normalized_plate: str)
        """
        cleaned = self.clean_raw_text(plate)
        if len(cleaned) < self.config.min_length or len(cleaned) > self.config.max_length:
            return False, "invalid_length", cleaned

        # Direct regex check
        if self.standard_pattern.match(cleaned):
            state = cleaned[:2]
            if state in self.state_codes:
                return True, "standard", cleaned
            elif state in STATE_CODE_CORRECTIONS:
                corr = STATE_CODE_CORRECTIONS[state] + cleaned[2:]
                return True, "standard", corr
            else:
                return False, f"unrecognized_state_{state}", cleaned

        if self.bh_pattern.match(cleaned):
            return True, "bh_series", cleaned

        # Attempt optical repair
        repaired = self.repair_characters(cleaned)

        if self.standard_pattern.match(repaired):
            state = repaired[:2]
            if state in self.state_codes:
                return True, "standard", repaired
            elif state in STATE_CODE_CORRECTIONS:
                corr = STATE_CODE_CORRECTIONS[state] + repaired[2:]
                return True, "standard", corr
            else:
                return False, f"unrecognized_state_{state}", repaired
        elif self.bh_pattern.match(repaired):
            return True, "bh_series", repaired

        # Edge noise artifact trimming for 11-character reads (e.g. RJ10AV7686J -> RJ10AV7686)
        # Often caused by plate frame borders, mounting screws, or rivets read as trailing/leading letters
        if len(cleaned) == 11:
            cand_trail = self.repair_characters(cleaned[:10])
            if self.standard_pattern.match(cand_trail) and cand_trail[:2] in self.state_codes:
                return True, "standard", cand_trail
            cand_lead = self.repair_characters(cleaned[1:])
            if self.standard_pattern.match(cand_lead) and cand_lead[:2] in self.state_codes:
                return True, "standard", cand_lead

        # Specific failure classification
        if self.legacy_pattern.match(repaired) or (len(repaired) in (9, 10) and not re.search(r'[0-9]{4}$', repaired)):
            return False, "incomplete_digits", repaired

        if len(repaired) == 11 and re.match(r'^[A-Z]{2}[0-9]{2}[A-Z]{3}[0-9]{4}$', repaired):
            return False, "illegible_numbers", repaired

        state = repaired[:2]
        if state not in self.state_codes and any(c.isalpha() for c in state):
            return False, f"unrecognized_state_{state}", repaired

        return False, "format_mismatch", repaired

    def format_display(self, plate: str) -> str:
        """
        Formats normalized plate with standard Indian spacing for clean UI readability.
        Example: MH12DE1433 -> MH 12 DE 1433, HR06B8455 -> HR 06 B 8455, DL3CCY7011 -> DL 3 CCY 7011
        """
        if not plate:
            return ""

        cleaned = self.clean_raw_text(plate)
        is_valid, fmt, norm = self.validate(cleaned)

        # 1. Standard 2-digit RTO: State (2), RTO (2), Series (1-2), Digits (4)
        m = re.match(r'^([A-Z]{2})([0-9]{2})([A-Z]{1,2})([0-9]{4})$', norm)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}"

        # 2. Standard 1-digit RTO: State (2), RTO (1), Series (2-3), Digits (4)
        m = re.match(r'^([A-Z]{2})([0-9]{1})([A-Z]{2,3})([0-9]{4})$', norm)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}"

        # 3. BH Series
        m = re.match(r'^([0-9]{2})(BH)([0-9]{4})([A-Z]{1,2})$', norm)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}"

        # 4. Fallback 11-char (e.g. invalid series length): State (2), RTO (2), Series (3), Digits (4)
        m = re.match(r'^([A-Z]{2})([0-9]{2})([A-Z]{3})([0-9]{4})$', norm)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)} {m.group(4)}"

        # 5. Fallback incomplete / legacy:
        m = re.match(r'^([A-Z]{2})([0-9]{1,2})([A-Z]{0,3})([0-9]{1,4})$', norm)
        if m:
            parts = [g for g in m.groups() if g]
            return " ".join(parts)

        return norm

    @staticmethod
    def calculate_levenshtein(s1: str, s2: str) -> float:
        """
        Computes normalized Levenshtein similarity [0.0, 1.0].
        """
        if s1 == s2:
            return 1.0
        if not s1 or not s2:
            return 0.0

        len1, len2 = len(s1), len(s2)
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i - 1] == s2[j - 1] else 1
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # deletion
                    dp[i][j - 1] + 1,      # insertion
                    dp[i - 1][j - 1] + cost # substitution
                )

        dist = dp[len1][len2]
        max_len = max(len1, len2)
        return 1.0 - (dist / max_len)
