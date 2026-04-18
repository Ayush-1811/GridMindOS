import urllib.request
import ssl
import re

def test_fetch_iex():
    print("Fetching real-time price from IEX...")
    try:
        # Ignore SSL certificate errors
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        # We must send a User-Agent, otherwise the server blocks the request
        req = urllib.request.Request('https://iexrtmprice.com/', headers={'User-Agent': 'Mozilla/5.0'})
        
        # Download the HTML
        html = urllib.request.urlopen(req, context=ctx, timeout=10).read().decode('utf-8')
        
        # Use Regex to extract the price inside <span id="lastPrice">2.7</span>
        match = re.search(r'id=[\"\']lastPrice[\"\'][^>]*>([\d\.]+)<\/span>', html)
        
        if match:
            price = float(match.group(1))
            print(f"Success! Extracted price: Rs. {price}/kWh")
        else:
            print("Error: Could not find the price in the HTML using regex.")
            
    except Exception as e:
        print(f"Error fetching data: {e}")

if __name__ == "__main__":
    test_fetch_iex()
