const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 10000;

let qrData = null;
let isConnected = false;
let sock = null;

async function startBot() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info');
    
    sock = makeWASocket({
        auth: state,
        browser: ['WhatsApp Bot', 'Chrome', '1.0.0']
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, qr } = update;
        if (qr) {
            qrData = qr;
            console.log('✅ QR Code generated');
        }
        if (connection === 'open') {
            isConnected = true;
            console.log('✅ WhatsApp Connected!');
        }
    });

    // 🔥 Message Handler - Ye Add Karein
    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.key.fromMe && msg.message) {
            const sender = msg.key.remoteJid;
            const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
            
            console.log(`📩 New message from ${sender}: ${text}`);
            
            // Sirf "Sharique" ke messages filter karein
            if (sender.includes('sharique') || sender.includes('91XXXXXXXXXX')) { // Apna number daalein
                console.log('🎯 Message from Sharique detected!');
                // Yahan Gemini + Excel code add karein
            }
        }
    });
}

app.get('/qr', async (req, res) => {
    if (!qrData) return res.send('⏳ QR Code not ready. Refresh in 5 seconds.');
    const qrImage = await qrcode.toDataURL(qrData);
    res.send(`<img src="${qrImage}" alt="QR Code"/>`);
});

app.get('/', (req, res) => {
    res.send(isConnected ? '✅ Bot Connected' : '⏳ Waiting for QR...');
});

app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
    startBot();
});
