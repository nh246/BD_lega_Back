"""
SSLCommerz Payment Gateway Integration Service.
Handles sandbox session initialization, transaction validation, and IPN verification.
"""

from typing import Any, Dict, Optional
import requests
from fastapi import HTTPException, status

from app.core.config import (
    BACKEND_URL,
    FRONTEND_URL,
    SSLCZ_SANDBOX,
    SSLCZ_STORE_ID,
    SSLCZ_STORE_PASSWD,
)

# Gateway endpoints
SANDBOX_GW_URL = "https://sandbox.sslcommerz.com/gwprocess/v4/api.php"
LIVE_GW_URL = "https://securepay.sslcommerz.com/gwprocess/v4/api.php"

SANDBOX_VALIDATOR_URL = "https://sandbox.sslcommerz.com/validator/api/validationserverAPI.php"
LIVE_VALIDATOR_URL = "https://securepay.sslcommerz.com/validator/api/validationserverAPI.php"


def get_gw_url() -> str:
    return SANDBOX_GW_URL if SSLCZ_SANDBOX else LIVE_GW_URL


def get_validator_url() -> str:
    return SANDBOX_VALIDATOR_URL if SSLCZ_SANDBOX else LIVE_VALIDATOR_URL


def init_sslcommerz_session(
    payment_id: str,
    amount: float,
    user_name: Optional[str] = None,
    user_email: Optional[str] = None,
    user_phone: Optional[str] = None,
    product_name: Optional[str] = "BD Legal AI Subscription",
) -> Dict[str, Any]:
    """
    Initializes an SSLCommerz hosted payment session.
    POSTs to the gateway endpoint and returns the GatewayPageURL redirect URL.
    """
    store_id = (SSLCZ_STORE_ID or "").strip()
    store_passwd = (SSLCZ_STORE_PASSWD or "").strip()

    if not store_id or not store_passwd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSLCommerz Store ID or Password is not configured in backend/.env. Please configure SSLCZ_STORE_ID and SSLCZ_STORE_PASSWD.",
        )

    backend = BACKEND_URL.rstrip("/")
    success_url = f"{backend}/api/payments/sslcommerz/success"
    fail_url = f"{backend}/api/payments/sslcommerz/fail"
    cancel_url = f"{backend}/api/payments/sslcommerz/cancel"
    ipn_url = f"{backend}/api/payments/sslcommerz/ipn"

    payload = {
        "store_id": store_id,
        "store_passwd": store_passwd,
        "total_amount": f"{amount:.2f}",
        "currency": "BDT",
        "tran_id": str(payment_id),
        "success_url": success_url,
        "fail_url": fail_url,
        "cancel_url": cancel_url,
        "ipn_url": ipn_url,
        "cus_name": (user_name or "Valued Client").strip() or "Valued Client",
        "cus_email": (user_email or "client@bdlegal.ai").strip() or "client@bdlegal.ai",
        "cus_add1": "Dhaka, Bangladesh",
        "cus_city": "Dhaka",
        "cus_country": "Bangladesh",
        "cus_phone": (user_phone or "01700000000").strip() or "01700000000",
        "shipping_method": "NO",
        "product_name": product_name or "BD Legal Services",
        "product_category": "Legal Services",
        "product_profile": "general",
    }

    try:
        response = requests.post(get_gw_url(), data=payload, timeout=30)
        data = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SSLCommerz gateway session initiation failed: {str(exc)}",
        )

    status_val = data.get("status")
    gateway_url = data.get("GatewayPageURL")

    if status_val == "SUCCESS" and gateway_url:
        return {
            "redirect_url": gateway_url,
            "sessionkey": data.get("sessionkey"),
            "status": "initiated",
        }

    # Handle gateway error response
    failed_reason = data.get("failedreason") or data.get("error") or "Unknown gateway rejection"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"SSLCommerz initialization failed: {failed_reason}",
    )


def validate_sslcommerz_transaction(val_id: str) -> Dict[str, Any]:
    """
    Validates a transaction using the SSLCommerz Validation API.
    Calls the validator endpoint with val_id, store_id, and store_passwd.
    """
    store_id = (SSLCZ_STORE_ID or "").strip()
    store_passwd = (SSLCZ_STORE_PASSWD or "").strip()

    if not store_id or not store_passwd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSLCommerz Store ID or Password is not configured in backend/.env.",
        )

    params = {
        "val_id": val_id,
        "store_id": store_id,
        "store_passwd": store_passwd,
        "format": "json",
    }

    try:
        response = requests.get(get_validator_url(), params=params, timeout=30)
        data = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SSLCommerz transaction validation failed: {str(exc)}",
        )

    return data
