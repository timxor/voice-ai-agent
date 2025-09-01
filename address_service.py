"""
Address validation service using Geoapify API.
"""
import httpx
from typing import Dict, Any
from config import GEOAPIFY_API_KEY


class AddressService:
    """Service for validating and normalizing addresses."""
    
    @staticmethod
    async def validate_address(address_text: str) -> Dict[str, Any]:
        """
        Validate and normalize a US mailing address string.
        Returns validation results including missing fields if any.
        """
        if not GEOAPIFY_API_KEY:
            return {"ok": False, "reason": "missing_geoapify_key"}

        url = "https://api.geoapify.com/v1/geocode/search"
        params = {"text": address_text, "apiKey": GEOAPIFY_API_KEY, "limit": 1}
        
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return {"ok": False, "reason": f"http_{r.status_code}"}
            
            data = r.json()
            features = data.get("features") or []
            if not features:
                return {"ok": False, "reason": "no_match"}
            
            props = features[0].get("properties", {})
            components = {
                "line1": props.get("address_line1"),
                "line2": props.get("address_line2"),
                "city": props.get("city"),
                "state": props.get("state_code") or props.get("state"),
                "postal_code": props.get("postcode"),
                "country": props.get("country_code"),
                "confidence": props.get("rank", {}).get("confidence") or props.get("confidence"),
            }
            missing = [k for k in ("line1", "city", "state", "postal_code") if not components.get(k)]
            
            return {
                "ok": True,
                "is_valid": len(missing) == 0,
                "missing": missing,
                "normalized": components,
                "raw": props,
            }