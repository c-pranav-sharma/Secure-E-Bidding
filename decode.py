import base64

# This is the receipt you got from the Contractor Dashboard
receipt_code = "QzFfMWEyMWFmNGRiMTVhNDJhY2FhZDFlNzQ2MWQyOTA0ZTYyY2MzYmE5MjJhZWZiMGNjMjJmNmNkMTMwNTIzZTM2Zl8yMDI2LTAxLTI5IDE5OjU5OjE0LjkzNzEzOQ=="

try:
    # Decode the Base64 string
    decoded_bytes = base64.b64decode(receipt_code)
    decoded_text = decoded_bytes.decode('utf-8')

    # Split the parts to make it readable
    parts = decoded_text.split('_')
    
    print("\n✅ DECODED RECEIPT:")
    print("-" * 50)
    print(f"👤 Who (Contractor): {parts[0]}")
    print(f"🔑 What (File Hash): {parts[1]}")
    print(f"⏰ When (Timestamp): {parts[2]}")
    print("-" * 50)

except Exception as e:
    print(f"Error: {e}")