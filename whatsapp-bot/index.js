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
console.log('✅ QR Code generated. Scan with WhatsApp.');
// Message receive karne ka listener
sock.ev.on('messages.upsert', async (m) => {
    const msg = m.messages[0];
    if (!msg.message) return;

    const sender = msg.key.remoteJid;
    const messageText = msg.message.conversation || msg.message.extendedTextMessage?.text;

    if (!messageText) return;

    console.log(`📩 New message from ${sender}: ${messageText}`);

    // Sirf "Sharique" ke messages filter karein
    if (sender.includes('Sharique') || sender.includes('@s.whatsapp.net')) {
        console.log('🤖 Processing with Gemini...');
        
        // Gemini se process karein
        const geminiResponse = await processWithGemini(messageText);
        console.log(`✅ Gemini Response: ${geminiResponse}`);

        // Excel mein update karein
        await updateExcel(geminiResponse);
        console.log('✅ Excel updated!');
    }
});
app.listen(PORT, () => {
    console.log(`✅ Server running on port ${PORT}`);
    startWhatsApp();
});
