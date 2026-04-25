"""
API Client with error handling and retry logic
"""
import requests
import time
from typing import Dict, Any, Optional
import streamlit as st
from config import REQUEST_TIMEOUT, MAX_RETRIES


class APIClient:
    """Generic API client with retry and error handling"""
    
    @staticmethod
    def make_request(
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        method: str = "GET",
        suppress_errors: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request with retry logic
        
        Args:
            url: API endpoint URL
            params: Query parameters
            headers: Request headers
            method: HTTP method (GET, POST)
            
        Returns:
            JSON response or None if failed
        """
        for attempt in range(MAX_RETRIES):
            try:
                if method == "GET":
                    response = requests.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=REQUEST_TIMEOUT
                    )
                else:
                    response = requests.post(
                        url,
                        json=params,
                        headers=headers,
                        timeout=REQUEST_TIMEOUT
                    )
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                if not suppress_errors:
                    st.error("⏱️ Request timed out. Please try again later.")
                return None
                
            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limit
                    if not suppress_errors:
                        st.warning("⚠️ Rate limit reached. Please wait a moment.")
                    time.sleep(5)
                    if attempt < MAX_RETRIES - 1:
                        continue
                elif response.status_code == 404:
                    if not suppress_errors:
                        st.error("❌ Resource not found.")
                else:
                    if not suppress_errors:
                        st.error(f"❌ HTTP Error: {e}")
                return None
                
            except requests.exceptions.ConnectionError:
                if not suppress_errors:
                    st.error("🌐 Connection error. Please check your internet connection.")
                return None
                
            except Exception as e:
                if not suppress_errors:
                    st.error(f"❌ Unexpected error: {str(e)}")
                return None
        
        return None
