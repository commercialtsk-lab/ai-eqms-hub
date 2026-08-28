const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 10000;

let sock = null;
let isConnected = false;
let qrCodeData = null;

async function startWhatsApp() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info');
    
    sock = makeWASocket({
        printQRInTerminal: false,
        auth: state,
        browser: ['WhatsApp Bot', 'Chrome', '1.0.0']
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            qrCodeData = qr;
            qrcode.generate(qr, { small: true });
            console.log('✅ QR Code generated');
        }

        if (connection === 'close') {
            const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
            if (shouldReconnect) {
                console.log('🔄 Reconnecting...');
                startWhatsApp();
            } else {
                console.log('❌ Logged out');
                isConnected = false;
            }
        } else if (connection === 'open') {
            console.log('✅ WhatsApp Connected!');
            isConnected = true;
        }
    });
}

// Express routes
app.get('/', (req, res) => {
    res.send(isConnected ? '✅ WhatsApp Bot Connected!' : '⏳ Connecting...');
});

app.get('/qr', (req, res) => {
    if (!qrCodeData) {
        return res.send('⏳ QR Code not ready. Refresh in 5 seconds.');
    }
    res.send(`<img src="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(qrCodeData)}" alt="QR Code"/>`);
});

app.get('/status', (req, res) => {
    res.json({ connected: isConnected });
});

app.listen(PORT, () => {
    console.log(`✅ Server running on port ${PORT}`);
    startWhatsApp();
});
