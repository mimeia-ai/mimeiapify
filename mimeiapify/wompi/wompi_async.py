import hashlib
import urllib.parse
import aiohttp
import uuid
from typing import Dict, Optional, List, Any

class WompiAsync:
    """
    Asynchronous client for the Wompi payment platform.
    
    This class provides methods to generate payment links and interact with Wompi's API.
    """
    
    def __init__(self, public_key: str, integrity_key: str, environment: str = "production", session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize the Wompi client.
        
        Args:
            public_key (str): The public key of the merchant.
            integrity_key (str): The integrity secret key for signature generation.
            environment (str, optional): Either "production" or "sandbox". Defaults to "production".
            session (aiohttp.ClientSession, optional): An existing aiohttp session to use. If None, a new session will be created when needed.
        """
        self.public_key = public_key
        self.integrity_key = integrity_key
        self.environment = environment
        self.base_url = "https://checkout.wompi.co/p/"
        env_subdomain = "sandbox" if environment == "sandbox" else "production"
        self.api_url = f"https://{env_subdomain}.wompi.co/v1"
        self._session = session
        self._own_session = False
    
    async def __aenter__(self):
        """Support for async context manager."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources when exiting the context manager."""
        await self.close()
    
    async def close(self):
        """Close the session if we created it."""
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None
            self._own_session = False
    
    async def _get_session(self):
        """Get or create an aiohttp session."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session
    
    def _generate_integrity_signature(self, reference: str, amount_in_cents: int, currency: str, expiration_time: Optional[str] = None) -> str:
        """
        Generate the integrity signature for the transaction.
        
        Args:
            reference (str): Unique payment reference.
            amount_in_cents (int): The amount to charge in cents.
            currency (str): The currency to charge in.
            expiration_time (str, optional): ISO8601 formatted expiration time.
            
        Returns:
            str: The integrity signature as a hex string.
        """
        # Concatenate the values in the required order
        if expiration_time:
            message = f"{reference}{amount_in_cents}{currency}{expiration_time}{self.integrity_key}"
        else:
            message = f"{reference}{amount_in_cents}{currency}{self.integrity_key}"
        
        # Calculate the SHA-256 hash
        hash_obj = hashlib.sha256(message.encode())
        return hash_obj.hexdigest()
    
    def generate_reference(self) -> str:
        """
        Generate a unique payment reference.
        
        Returns:
            str: A unique reference string.
        """
        return str(uuid.uuid4()).replace("-", "")
    
    async def generate_checkout_url(self, 
                               amount_in_cents: int, 
                               reference: Optional[str] = None, 
                               currency: str = "COP", 
                               redirect_url: Optional[str] = None, 
                               expiration_time: Optional[str] = None, 
                               tax_vat_in_cents: Optional[int] = None, 
                               tax_consumption_in_cents: Optional[int] = None,
                               customer_data: Optional[Dict[str, str]] = None, 
                               shipping_address: Optional[Dict[str, str]] = None, 
                               collect_shipping: bool = False,
                               collect_customer_legal_id: bool = False) -> Dict[str, str]:
        """
        Generate a URL for the Wompi Web Checkout.
        
        Args:
            amount_in_cents (int): The amount to charge in cents.
            reference (str, optional): Unique payment reference. If None, a random reference will be generated.
            currency (str, optional): The currency to charge in. Defaults to "COP".
            redirect_url (str, optional): URL to redirect after payment. Defaults to None.
            expiration_time (str, optional): ISO8601 formatted expiration time. Defaults to None.
            tax_vat_in_cents (int, optional): VAT tax amount in cents. Defaults to None.
            tax_consumption_in_cents (int, optional): Consumption tax amount in cents. Defaults to None.
            customer_data (dict, optional): Customer data for prefilling. Defaults to None.
                Expected keys: email, full-name, phone-number, phone-number-prefix, legal-id, legal-id-type
            shipping_address (dict, optional): Shipping address data. Defaults to None.
                Expected keys: address-line-1, address-line-2, country, city, phone-number, region, name, postal-code
            collect_shipping (bool, optional): Whether to collect shipping information. Defaults to False.
            collect_customer_legal_id (bool, optional): Whether to collect customer legal ID information. Defaults to False.
            
        Returns:
            dict: A dictionary containing the checkout URL and the reference used.
        """
        # Generate a reference if not provided
        if reference is None:
            reference = self.generate_reference()
        
        # Generate the integrity signature
        signature = self._generate_integrity_signature(reference, amount_in_cents, currency, expiration_time)
        
        # Build the URL parameters
        params = {
            "public-key": self.public_key,
            "currency": currency,
            "amount-in-cents": str(amount_in_cents),
            "reference": reference,
            "signature:integrity": signature
        }
        
        if redirect_url:
            params["redirect-url"] = redirect_url
        
        if expiration_time:
            params["expiration-time"] = expiration_time
            
        # Add tax parameters if provided
        if tax_vat_in_cents:
            params["tax-in-cents:vat"] = str(tax_vat_in_cents)
        
        if tax_consumption_in_cents:
            params["tax-in-cents:consumption"] = str(tax_consumption_in_cents)
        
        # Add customer data if provided
        if customer_data:
            for key, value in customer_data.items():
                params[f"customer-data:{key}"] = value
        
        # Add shipping address if provided
        if shipping_address:
            for key, value in shipping_address.items():
                params[f"shipping-address:{key}"] = value
        
        if collect_shipping:
            params["collect-shipping"] = "true"
            
        if collect_customer_legal_id:
            params["collect-customer-legal-id"] = "true"
        
        # Build the URL
        query_string = "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])
        checkout_url = f"{self.base_url}?{query_string}"
        
        return {
            "checkout_url": checkout_url,
            "reference": reference
        }
    
    async def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """
        Get a transaction by its ID.
        
        Args:
            transaction_id (str): The ID of the transaction.
            
        Returns:
            dict: The transaction data.
        """
        url = f"{self.api_url}/transactions/{transaction_id}"
        
        session = await self._get_session()
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            else:
                response_text = await response.text()
                raise Exception(f"Failed to get transaction: {response.status} - {response_text}")
    
    async def get_transaction_by_reference(self, reference: str) -> List[Dict[str, Any]]:
        """
        Get a transaction by its reference.
        
        Args:
            reference (str): The reference of the transaction.
            
        Returns:
            list: A list of transaction data matching the reference.
        """
        url = f"{self.api_url}/transactions?reference={reference}"
        
        session = await self._get_session()
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("data", [])
            else:
                response_text = await response.text()
                raise Exception(f"Failed to get transaction by reference: {response.status} - {response_text}")

    @staticmethod
    def verify_webhook_event(event_data: dict, events_secret: str) -> bool:
        """
        Verify the authenticity of a Wompi webhook event.
        
        This is a static method as it doesn't require an instance of WompiAsync.
        
        Args:
            event_data (dict): The full event data received from Wompi webhook
            events_secret (str): The Events Secret key from Wompi dashboard
            
        Returns:
            bool: True if the event is authentic, False otherwise
        """
        try:
            # Extract required components for verification
            signature = event_data.get("signature", {})
            properties = signature.get("properties", [])
            received_checksum = signature.get("checksum", "")
            timestamp = event_data.get("timestamp")
            
            if not properties or not received_checksum or timestamp is None:
                return False
            
            # Extract and concatenate property values
            data = event_data.get("data", {})
            concatenated_values = ""
            
            for prop_path in properties:
                # Handle nested properties like "transaction.id"
                parts = prop_path.split(".")
                current_data = data
                
                for part in parts:
                    if isinstance(current_data, dict) and part in current_data:
                        current_data = current_data[part]
                    else:
                        # Property path doesn't exist
                        return False
                
                # Ensure we have a primitive value, not a complex object
                if isinstance(current_data, (dict, list)) or current_data is None:
                    return False
                    
                concatenated_values += str(current_data)
            
            # Create the string to hash: values + timestamp + secret
            concat_string = concatenated_values + str(timestamp) + events_secret
            
            # Calculate SHA-256 hash
            calculated_checksum = hashlib.sha256(concat_string.encode()).hexdigest().upper()
            
            # Compare the calculated checksum with the received one (case-insensitive)
            return calculated_checksum == received_checksum.upper()
            
        except Exception:
            # Any unexpected error means verification failed
            return False
