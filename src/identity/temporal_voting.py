"""
Temporal Voting and Promotion Engine
Aggregates multi-frame OCR readings for each vehicle identity using confidence-weighted voting.
Validates format against Indian plate standards and separates verified vehicles from "Needs Review".
Deduplicates verified results by normalized plate number.
"""
from typing import List, Dict, Tuple, Optional
import numpy as np
from config import TemporalVotingConfig
from src.identity.vehicle_identity import VehicleRecord, CandidateReading
from src.ocr.normalizer import IndianPlateNormalizer, ALPHA_TO_NUM, NUM_TO_ALPHA, STATE_CODE_CORRECTIONS
from src.ocr.enhancer import PlateEnhancer

class TemporalVotingEngine:
    def __init__(self, config: Optional[TemporalVotingConfig] = None):
        self.config = config or TemporalVotingConfig()
        self.normalizer = IndianPlateNormalizer()

    def vote_on_vehicle(self, vehicle: VehicleRecord, is_single_image: bool = False) -> VehicleRecord:
        """
        Processes all collected readings of a VehicleRecord, calculates consensus plate,
        determines confidence, and decides whether to promote to VERIFIED or route to NEEDS_REVIEW.
        """
        if not vehicle.readings:
            vehicle.status = "REJECTED"
            vehicle.review_reason = "No valid plate crops detected"
            vehicle.is_verified = False
            return vehicle

        # 1. Filter valid non-unreadable candidate readings
        valid_readings = [r for r in vehicle.readings if r.normalized_text and self.normalizer.config.min_length <= len(self.normalizer.clean_raw_text(r.normalized_text)) <= self.normalizer.config.max_length]

        if not valid_readings:
            vehicle.final_plate = "UNREADABLE"
            vehicle.display_plate = "UNREADABLE (INCOMPLETE OCR)"
            vehicle.final_confidence = 0.0
            persistent_readings = [r for r in vehicle.readings if r.detection_confidence >= 0.50]
            if len(persistent_readings) >= 5:
                vehicle.status = "UNREADABLE"
                vehicle.final_plate = "UNREADABLE"
                vehicle.display_plate = "UNREADABLE (LOW EVIDENCE)"
                vehicle.review_reason = f"Plate detected across {len(persistent_readings)} frames but text illegible (<20% OCR)"
                vehicle.is_verified = False
                return vehicle
            vehicle.status = "REJECTED"
            vehicle.review_reason = "Transient detection or no legible plate readings (<5 frames)"
            vehicle.is_verified = False
            return vehicle

        # 2. Determine canonical plate length weighted by confidence, format validity, and 10-char priority
        length_weight: Dict[int, float] = {}
        for r in valid_readings:
            norm = r.normalized_text
            is_valid_fmt, _, canonical = self.normalizer.validate(norm)
            fmt_mult = 2.0 if is_valid_fmt else 0.5
            char_bonus = 1.3 if len(canonical) == 10 else 1.0
            blur_mult = min(1.5, 1.0 + np.log1p(max(0.0, r.blur_score)) / 10.0)
            weight = (r.ocr_confidence ** 2) * fmt_mult * blur_mult * char_bonus
            l = len(canonical)
            length_weight[l] = length_weight.get(l, 0.0) + weight

        canonical_len = max(length_weight, key=lambda l: length_weight[l]) if length_weight else 10

        # Filter candidate readings matching canonical_len
        matching_candidates = [
            r for r in valid_readings
            if len(self.normalizer.validate(r.normalized_text)[2]) == canonical_len
        ]
        if not matching_candidates:
            matching_candidates = valid_readings

        # 3. Position-Aware Character-by-Character Voting with MoRTH / CMVR Positional Mapping
        chars: List[str] = []
        pos_confs: List[float] = []
        for i in range(canonical_len):
            tally: Dict[str, float] = {}
            conf_tally: Dict[str, float] = {}
            for r in matching_candidates:
                _, _, canon = self.normalizer.validate(r.normalized_text)
                if i < len(canon):
                    ch = canon[i]
                    # CMVR Single-Digit & Single-Letter Positional Normalization
                    if canonical_len == 10:
                        if i in (0, 1):
                            ch = NUM_TO_ALPHA.get(ch, ch)
                        elif i == 2:
                            ch = ALPHA_TO_NUM.get(ch, ch)
                        elif i == 3:
                            # 2-digit RTO (most common) or 1-digit RTO (Delhi/UT)
                            if ch in ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'O', 'I', 'Z'):
                                ch = ALPHA_TO_NUM.get(ch, ch)
                            else:
                                ch = NUM_TO_ALPHA.get(ch, ch)
                        elif i in (4, 5):
                            ch = NUM_TO_ALPHA.get(ch, ch)
                        elif i in (6, 7, 8, 9):
                            ch = ALPHA_TO_NUM.get(ch, ch)
                    elif canonical_len == 9:
                        if i in (0, 1):
                            ch = NUM_TO_ALPHA.get(ch, ch)
                        elif i == 2:
                            ch = ALPHA_TO_NUM.get(ch, ch)
                        elif i in (3, 4):
                            if ch.isdigit():
                                ch = ALPHA_TO_NUM.get(ch, ch)
                            else:
                                ch = NUM_TO_ALPHA.get(ch, ch)
                        elif i in (5, 6, 7, 8):
                            ch = ALPHA_TO_NUM.get(ch, ch)

                    blur_mult = min(1.5, 1.0 + np.log1p(max(0.0, r.blur_score)) / 10.0)
                    w = (r.ocr_confidence ** 2) * blur_mult
                    tally[ch] = tally.get(ch, 0.0) + w
                    conf_tally[ch] = max(conf_tally.get(ch, 0.0), r.ocr_confidence)
            if tally:
                best_ch = max(tally, key=lambda ch: tally[ch])
                chars.append(best_ch)
                pos_confs.append(conf_tally.get(best_ch, 0.5))
            else:
                chars.append("?")
                pos_confs.append(0.0)

        # CMVR State Code validation & correction for first 2 letters
        if len(chars) >= 2:
            st = "".join(chars[0:2])
            if st not in self.normalizer.state_codes and st in STATE_CODE_CORRECTIONS:
                corr_st = STATE_CODE_CORRECTIONS[st]
                chars[0], chars[1] = corr_st[0], corr_st[1]

        voted_plate = "".join(chars)

        # Also score candidate strings as fallback safety
        candidate_scores: Dict[str, float] = {}
        candidate_confs: Dict[str, List[float]] = {}
        for r in valid_readings:
            is_valid_fmt, _, canon = self.normalizer.validate(r.normalized_text)
            fmt_mult = 2.0 if is_valid_fmt else 0.5
            blur_mult = min(1.5, 1.0 + np.log1p(max(0.0, r.blur_score)) / 10.0)
            w = (r.ocr_confidence ** 2) * fmt_mult * blur_mult
            candidate_scores[canon] = candidate_scores.get(canon, 0.0) + w
            if canon not in candidate_confs:
                candidate_confs[canon] = []
            candidate_confs[canon].append(r.ocr_confidence)

        # 4. Validate synthesized plate or select best fallback candidate
        is_valid_voted, fmt_type_voted, norm_voted = self.normalizer.validate(voted_plate)
        if is_valid_voted:
            best_plate = norm_voted
            is_valid_plate = is_valid_voted
            fmt_type = fmt_type_voted
        else:
            sorted_str_candidates = sorted(
                candidate_scores.items(),
                key=lambda item: (
                    1 if self.normalizer.validate(item[0])[0] else 0,
                    max(candidate_confs.get(item[0], [0.0])),
                    item[1]
                ),
                reverse=True
            )
            raw_best = sorted_str_candidates[0][0] if sorted_str_candidates else voted_plate
            is_valid_plate, fmt_type, norm_plate = self.normalizer.validate(raw_best)
            best_plate = norm_plate

        # Readings supporting best_plate (Levenshtein similarity >= 0.80 or exact match)
        supporting_readings = [
            r for r in valid_readings
            if self.normalizer.calculate_levenshtein(self.normalizer.validate(r.normalized_text)[2], best_plate) >= 0.80
        ]
        supporting_count = max(1, len(supporting_readings))

        peak_ocr = max((r.ocr_confidence for r in supporting_readings), default=0.5)
        avg_pos_conf = float(np.mean(pos_confs)) if pos_confs else peak_ocr
        consensus_ratio = supporting_count / len(vehicle.readings)
        final_confidence = min(0.99, max(peak_ocr, float(avg_pos_conf * (0.85 + 0.15 * consensus_ratio))))

        display_plate = self.normalizer.format_display(best_plate)
        vehicle.final_plate = best_plate
        vehicle.display_plate = display_plate
        vehicle.final_confidence = final_confidence
        vehicle.format_type = fmt_type
        vehicle.is_valid_format = is_valid_plate

        # 5. Synchronize best visual evidence (crop, vehicle crop, annotated frame)
        # Select the reading closest to best_plate with highest OCR confidence and visual clarity
        def reading_evidence_score(r: CandidateReading):
            _, _, canon = self.normalizer.validate(r.normalized_text)
            sim = self.normalizer.calculate_levenshtein(canon, best_plate)
            return (sim >= 0.80, sim, r.ocr_confidence, (r.ocr_confidence ** 2) * np.log1p(max(1.0, r.blur_score)))

        best_win_reading = max(valid_readings, key=reading_evidence_score)
        if best_win_reading.crop_image is not None and best_win_reading.crop_image.size > 0:
            vehicle.best_crop = best_win_reading.crop_image.copy()
        if best_win_reading.vehicle_crop is not None and best_win_reading.vehicle_crop.size > 0:
            vehicle.best_vehicle_crop = best_win_reading.vehicle_crop.copy()
        if best_win_reading.annotated_frame is not None and best_win_reading.annotated_frame.size > 0:
            vehicle.best_annotated_frame = best_win_reading.annotated_frame.copy()
        vehicle.final_confidence = max(vehicle.final_confidence, float(best_win_reading.ocr_confidence))
        vehicle.best_reading = best_win_reading

        # Store enhanced crop & diagnostics for Before vs After forensic inspection
        if getattr(best_win_reading, "enhanced_crop", None) is not None and best_win_reading.enhanced_crop.size > 0:
            vehicle.best_enhanced_crop = best_win_reading.enhanced_crop.copy()
            vehicle.preprocessing_meta = getattr(best_win_reading, "preprocessing_meta", None)
        elif vehicle.best_crop is not None and vehicle.best_crop.size > 0:
            diag = PlateEnhancer.get_preprocessing_diagnostics(vehicle.best_crop)
            vehicle.best_enhanced_crop = diag.pop("enhanced_image", None)
            vehicle.preprocessing_meta = diag

        # Route to UNREADABLE or REJECTED if final confidence is < 20%
        if final_confidence < 0.20:
            persistent_readings = [r for r in vehicle.readings if r.detection_confidence >= 0.60]
            if persistent_readings:
                vehicle.status = "UNREADABLE"
                vehicle.final_plate = "UNREADABLE"
                vehicle.display_plate = "UNREADABLE (LOW EVIDENCE)"
                vehicle.review_reason = f"OCR confidence < 20% ({final_confidence:.1%})"
                vehicle.is_verified = False
                return vehicle
            else:
                vehicle.status = "REJECTED"
                vehicle.review_reason = f"Confidence < 20% noise ({final_confidence:.1%})"
                vehicle.is_verified = False
                return vehicle

        # 6. Check for severe conflicts:
        # Only flag has_severe_conflict if two completely distinct valid plates (differing significantly)
        # compete with substantial weight, rather than minor single-character optical noise
        has_severe_conflict = False
        competing_plates: Dict[str, float] = {}
        for r in valid_readings:
            is_v, _, canon = self.normalizer.validate(r.normalized_text)
            if is_v and canon != best_plate:
                sim = self.normalizer.calculate_levenshtein(canon, best_plate)
                if sim < 0.70:  # Distinct plates (3+ characters difference)
                    competing_plates[canon] = competing_plates.get(canon, 0.0) + (r.ocr_confidence ** 2)

        top_conflict_plate = ""
        if competing_plates:
            top_conflict_plate, conflict_weight = max(competing_plates.items(), key=lambda x: x[1])
            best_weight = sum((r.ocr_confidence ** 2) for r in supporting_readings)
            if conflict_weight >= 0.40 * best_weight:
                has_severe_conflict = True

        # 7. Evaluate Promotion Criteria
        reasons = []

        required_frames = 1 if is_single_image else self.config.min_supporting_frames
        if supporting_count < required_frames:
            reasons.append(f"Insufficient frames ({supporting_count} < {required_frames})")

        if final_confidence < self.config.min_promotion_confidence:
            reasons.append(f"Low confidence ({final_confidence:.1%})")

        if self.config.require_valid_plate_format and not is_valid_plate:
            reasons.append(f"Invalid plate format ({fmt_type})")

        if has_severe_conflict:
            reasons.append(f"Conflicting readings: '{best_plate}' vs '{top_conflict_plate}'")

        if not reasons:
            vehicle.status = "VERIFIED"
            vehicle.is_verified = True
            vehicle.review_reason = ""
        else:
            vehicle.status = "NEEDS_REVIEW"
            vehicle.is_verified = False
            vehicle.review_reason = "; ".join(reasons)

        return vehicle

    def deduplicate_verified_results(self, verified_vehicles: List[VehicleRecord]) -> List[VehicleRecord]:
        """
        Deduplicates verified vehicles by normalized final plate number.
        If multiple vehicle tracks correspond to the same license plate,
        merges them into one consolidated record preserving all linked track IDs,
        frame range, best crop, and evidence frames.
        """
        plate_map: Dict[str, VehicleRecord] = {}

        for v in verified_vehicles:
            plate = v.final_plate
            if not plate:
                continue

            matched_key = None
            if plate in plate_map:
                matched_key = plate
            else:
                for k in list(plate_map.keys()):
                    existing_v = plate_map[k]
                    time_diff = abs(v.first_timestamp - existing_v.first_timestamp)
                    sim = self.normalizer.calculate_levenshtein(k, plate)
                    # Match if prefix matches (e.g. HR06AM737 and HR06AM7371) or high fuzzy similarity within 3.5s
                    if (len(k) == 10 and len(plate) == 9 and k.startswith(plate)) or \
                       (len(plate) == 10 and len(k) == 9 and plate.startswith(k)) or \
                       (abs(len(k) - len(plate)) <= 1 and sim >= 0.88) or \
                       (sim >= 0.80 and time_diff <= 3.5):
                        matched_key = k
                        break

            if matched_key is None:
                plate_map[plate] = v
            else:
                existing = plate_map[matched_key]
                # If current candidate is 10 chars and existing was 9 chars, promote canonical key to 10 chars
                if len(plate) > len(existing.final_plate):
                    del plate_map[matched_key]
                    existing.final_plate = plate
                    existing.display_plate = self.normalizer.format_display(plate)
                    plate_map[plate] = existing

                # Merge linked track IDs
                existing.linked_track_ids.update(v.linked_track_ids)
                # Expand frame range
                existing.first_frame = min(existing.first_frame, v.first_frame)
                existing.last_frame = max(existing.last_frame, v.last_frame)
                existing.first_timestamp = min(existing.first_timestamp, v.first_timestamp)
                existing.last_timestamp = max(existing.last_timestamp, v.last_timestamp)
                
                # Keep highest confidence
                if v.final_confidence > existing.final_confidence:
                    existing.final_confidence = v.final_confidence
                    if v.best_crop is not None:
                        existing.best_crop = v.best_crop
                    if v.best_vehicle_crop is not None:
                        existing.best_vehicle_crop = v.best_vehicle_crop

                # Combine evidence frames up to max_evidence
                existing_frame_ids = {ef.frame_idx for ef in existing.evidence_frames}
                for ef in v.evidence_frames:
                    if ef.frame_idx not in existing_frame_ids and len(existing.evidence_frames) < self.config.max_evidence_frames:
                        existing.evidence_frames.append(ef)
                        existing_frame_ids.add(ef.frame_idx)

                # Combine readings
                existing.readings.extend(v.readings)

        return list(plate_map.values())
