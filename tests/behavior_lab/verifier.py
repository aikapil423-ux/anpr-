"""
Behavior Intelligence Lab - Stage 2 Cloud AI Forensic Verifier
Receives 4 chronological keyframes extracted by Stage 1 trigger.
Uses Google Gemini Flash API with Structured JSON Schema.
Acts as the final 'Judge' to eliminate false alarms.
"""
import os
import cv2
import json
import time
from typing import List, Dict, Any, Optional
import numpy as np

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

class CloudBehaviorVerifier:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.client = None
        self.model_name = "gemini-3.5-flash"
        self.fallback_model = "gemini-3.1-flash-lite"

        if self.api_key and HAS_GENAI:
            try:
                self.client = genai.Client(api_key=self.api_key)
                print(f"[Stage 2 Verifier] Successfully connected to Google GenAI ({self.model_name})")
            except Exception as e:
                print(f"[Stage 2 Verifier Warning] Could not initialize Gemini Client: {e}")
        else:
            print("[Stage 2 Verifier] Running in MOCK / LOCAL-EMULATION mode (No active API key set).")

    def verify_candidate(
        self,
        event_type: str,
        keyframes: List[np.ndarray],
        stage1_meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Sends 4 chronological keyframes to Gemini Flash for forensic verification.
        """
        t0 = time.time()

        # If no client or API key, run realistic forensic heuristic mock for dry-run
        if self.client is None:
            return self._mock_verification(event_type, stage1_meta, elapsed=time.time() - t0)

        # 1. Prepare images as lightweight JPEG byte payloads
        parts = []
        for idx, img in enumerate(keyframes):
            # Downscale slightly for speed (640x480 max dimension)
            h, w = img.shape[:2]
            scale = min(640 / max(w, 1), 480 / max(h, 1), 1.0)
            if scale < 1.0:
                img_resized = cv2.resize(img, (int(w * scale), int(h * scale)))
            else:
                img_resized = img

            success, buf = cv2.imencode(".jpg", img_resized, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if success:
                parts.append(
                    types.Part.from_bytes(data=buf.tobytes(), mime_type="image/jpeg")
                )

        # 2. Targeted Prompt with Strict Police Forensic Guidelines
        prompt = f"""
You are a senior law enforcement forensic video analyst for State Police HQ.
Review these 4 sequential CCTV frames representing an anomalous event detected over a 2-second span.

Triggered Suspected Behavior: {event_type}
Stage 1 Automated Telemetry: {json.dumps(stage1_meta or {})}

YOUR TASK:
Determine whether this is a GENUINE violation or a FALSE ALARM.

Evaluation Rules:
1. For 'PHYSICAL_FIGHT':
   - Distinguish genuine violent assault/brawls (punching, kicking, choking, striking, weapon usage) from friendly hugs, wrestling sport, horseplay, dance, or greeting.
   - Look at facial/body tension, guarding posture, impact reactions, and aggression.
2. For 'PUBLIC_DRINKING / NUISANCE':
   - Confirm presence of alcohol bottles, cans, glasses, open intoxication vs water bottles, tea/coffee, snacks, or soft drinks.
3. For 'UNLAWFUL_MARCH / PROTEST':
   - Confirm protest banners, coordinated slogans, road obstruction vs standard commuters crossing street.

OUTPUT STRICT JSON ONLY with the following schema:
{{
  "is_violation": true or false,
  "confidence": float between 0.0 and 1.0,
  "violation_type": "{event_type}",
  "reason": "1-sentence concise factual explanation of what occurred across the 4 frames",
  "threat_level": "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "action_recommended": "1-sentence instruction for patrolling officer / police dispatch"
}}
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[*parts, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            elapsed = time.time() - t0
            result = json.loads(response.text)
            result["latency_seconds"] = round(elapsed, 2)
            result["provider"] = f"Google {self.model_name}"
            return result
        except Exception as e:
            try:
                # Fallback model attempt
                response = self.client.models.generate_content(
                    model=self.fallback_model,
                    contents=[*parts, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                elapsed = time.time() - t0
                result = json.loads(response.text)
                result["latency_seconds"] = round(elapsed, 2)
                result["provider"] = f"Google {self.fallback_model} (Fallback)"
                return result
            except Exception as e2:
                elapsed = time.time() - t0
                print(f"[Stage 2 Verifier Error]: {e} | Fallback Error: {e2}")
                return {
                    "is_violation": False,
                    "confidence": 0.0,
                    "error": str(e2),
                    "latency_seconds": round(elapsed, 2),
                    "provider": "Fallback Error"
                }

    def _mock_verification(self, event_type: str, meta: Optional[Dict[str, Any]], elapsed: float) -> Dict[str, Any]:
        """Provides realistic structured response when testing offline without an API key"""
        score = meta.get("kinetic_score", 50.0) if meta else 50.0
        is_viol = score > 65.0
        return {
            "is_violation": is_viol,
            "confidence": round(min(0.96, score / 100.0 + 0.15), 2),
            "violation_type": event_type,
            "reason": (
                f"[Simulated Verification]: High kinetic wrist velocity ({meta.get('wrist_velocity_px_s', 0)} px/s) "
                f"and close body overlap ({meta.get('overlap_iou', 0)}) observed between person #{meta.get('person_A_id')} and #{meta.get('person_B_id')}."
                if is_viol else
                f"[Simulated Non-Violation]: Movement consistent with proximity pass-by or non-aggressive interaction."
            ),
            "threat_level": "HIGH" if is_viol else "NONE",
            "action_recommended": "Dispatch nearest PCR van for physical verification." if is_viol else "No action required.",
            "latency_seconds": round(elapsed + 0.05, 2),
            "provider": "Local Dry-Run Mock (Provide GEMINI_API_KEY to invoke live Gemini 2.5 Flash)"
        }
