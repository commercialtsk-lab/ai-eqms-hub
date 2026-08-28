from flask import Flask, send_file
import os
import qrcode
from io import BytesIO

app = Flask(__name__)

# ✅ Home Route
@app.route('/')
def home():
    return "WhatsApp Bot is Running!"

# ✅ QR Code Route
@app.route('/qr')
def generate_qr():
    # WhatsApp Web QR code generate karein
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data("https://web.whatsapp.com")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
