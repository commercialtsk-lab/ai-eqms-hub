const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 10000;

let qrData = null;
let isConnected = false;
let sock = null;

// ==============================================
// 📱 WHATSAPP BOT
// ==============================================

async function startWhatsApp() {
    try {
        const { state, saveCreds } = await useMultiFileAuthState('auth_info');
        
        sock = makeWASocket({
            printQRInTerminal: true,
            auth: state,
            browser: ['WhatsApp Bot', 'Chrome', '1.0.0']
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                qrData = qr;
                console.log('✅ QR Code generated');
                console.log('📱 Scan this QR with WhatsApp');
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
                console.log('📡 Monitoring messages...');
            }
        });

        // 📩 MESSAGE HANDLER
        sock.ev.on('messages.upsert', async (m) => {
            const msg = m.messages[0];
            if (!msg.message) return;
            
            const sender = msg.key.remoteJid;
            const messageText = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
            
            console.log(`📩 Message from: ${sender}`);
            console.log(`📝 Text: ${messageText}`);
            
            // 🔥 SIRF "Sharique" KE MESSAGES PROCESS KAREIN
            if (sender.includes('Sharique') || sender.includes('@s.whatsapp.net')) {
                console.log('🎯 Target message received!');
                // Gemini integration yahan add karein
            }
        });

    } catch (error) {
        console.error('❌ Error:', error);
        setTimeout(startWhatsApp, 5000);
    }
}

// ==============================================
// 🌐 EXPRESS SERVER
// ==============================================

app.get('/', (req, res) => {
    res.send(`
        <h2>🤖 WhatsApp Bot</h2>
        <p>Status: ${isConnected ? '✅ Connected' : '⏳ Connecting...'}</p>
        <a href="/qr">📱 Scan QR</a>
        <br><br>
        <a href="/status">📊 Status</a>
    `);
});

app.get('/qr', async (req, res) => {
    if (!qrData) {
        return res.send(`
            <h2>⏳ QR Code not ready</h2>
            <p>Refresh in 5 seconds...</p>
            <meta http-equiv="refresh" content="5">
        `);
    }
    
    try {
        const qrImage = await qrcode.toDataURL(qrData);
        res.send(`
            <h2>📱 Scan QR with WhatsApp</h2>
            <img src="${qrImage}" alt="QR Code" style="max-width:300px;"/>
            <br><br>
            <p>Status: ${isConnected ? '✅ Connected' : '⏳ Waiting...'}</p>
            <p>Open WhatsApp → Linked Devices → Link a Device</p>
            <br>
            <a href="/restart">🔄 Restart Session</a>
        `);
    } catch (error) {
        res.send('❌ Error generating QR: ' + error.message);
    }
});

app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        qr_ready: qrData !== null,
        timestamp: new Date().toISOString()
    });
});

app.get('/restart', async (req, res) => {
    try {
        // Session delete karein
        const authPath = path.join(__dirname, 'auth_info');
        if (fs.existsSync(authPath)) {
            fs.rmSync(authPath, { recursive: true, force: true });
        }
        qrData = null;
        isConnected = false;
        res.send('🔄 Restarting... Go to /qr in 10 seconds');
        setTimeout(() => {
            startWhatsApp();
        }, 3000);
    } catch (error) {
        res.send('❌ Error: ' + error.message);
    }
});

// ==============================================
// 🚀 START SERVER
// ==============================================

app.listen(PORT, '0.0.0.0', () => {
    console.log(`✅ Server running on port ${PORT}`);
    console.log(`📱 QR URL: https://ai-eqms-hub-5.onrender.com/qr`);
    startWhatsApp();
});

// Handle shutdown
process.on('SIGINT', () => {
    console.log('🛑 Shutting down...');
    process.exit(0);
});
