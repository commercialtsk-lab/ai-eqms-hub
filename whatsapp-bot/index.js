const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 10000;

let qrData = null;
let isConnected = false;

// ============================================================
// 🔥 FORCE SESSION DELETE (Render Free Plan Fix)
// ============================================================

const SESSION_DIR = 'auth_info';

if (fs.existsSync(SESSION_DIR)) {
    console.log('🔄 Deleting old session...');
    fs.rmSync(SESSION_DIR, { recursive: true, force: true });
    console.log('✅ Session deleted!');
} else {
    console.log('ℹ️ No existing session found.');
}

// ============================================================
// ✅ WHATSAPP BOT START
// ============================================================

async function startBot() {
    try {
        console.log('🔄 Bot starting...');

        const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

        const sock = makeWASocket({
            auth: state,
            browser: ['Chrome', 'Windows', '10.0'],
            syncFullHistory: false,
            markOnlineOnConnect: false,
            connectTimeoutMs: 30000,
            keepAliveIntervalMs: 10000
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', (update) => {
            const { connection, qr, lastDisconnect } = update;

            if (qr) {
                qrData = qr;
                console.log('✅ QR Code generated');
            }

            if (connection === 'open') {
                isConnected = true;
                console.log('✅ WhatsApp Connected!');
            }

            if (connection === 'close') {
                const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
                isConnected = false;
                console.log('🔄 Connection closed, reconnecting:', shouldReconnect);
                if (shouldReconnect) {
                    setTimeout(startBot, 5000);
                }
            }
        });

        sock.ev.on('messages.upsert', async (m) => {
            try {
                const msg = m.messages[0];
                if (!msg || msg.key.fromMe) return;

                const sender = msg.key.remoteJid;
                let text = '';

                if (msg.message?.conversation) {
                    text = msg.message.conversation;
                } else if (msg.message?.extendedTextMessage) {
                    text = msg.message.extendedTextMessage.text;
                } else if (msg.message?.imageMessage) {
                    text = msg.message.imageMessage.caption || '[Image]';
                } else {
                    text = '[Media]';
                }

                console.log(`📩 [${sender}] ${text.substring(0, 80)}`);

                if (sender.toLowerCase().includes('sharique')) {
                    console.log('🎯 Sharique message detected!');
                }

            } catch (err) {
                console.log('⚠️ Message error:', err.message);
            }
        });

        sock.ev.on('error', (err) => {
            console.log('⚠️ Socket error:', err.message);
        });

    } catch (err) {
        console.log('❌ Bot error:', err.message);
        setTimeout(startBot, 10000);
    }
}

// ============================================================
// ✅ EXPRESS ROUTES
// ============================================================

app.get('/', (req, res) => {
    res.send(`
        <h2>🤖 WhatsApp Bot</h2>
        <p>Status: ${isConnected ? '✅ Connected' : '⏳ Connecting...'}</p>
        <p><a href="/qr">Scan QR</a> | <a href="/status">Status</a></p>
    `);
});

app.get('/qr', async (req, res) => {
    console.log('📱 QR page accessed');
    console.log('qrData:', qrData ? '✅ Available' : '❌ Not ready');

    if (!qrData) {
        return res.send(`
            <h2>⏳ QR Code Not Ready</h2>
            <p>Please wait 10 seconds and refresh.</p>
            <p><a href="/qr">Refresh</a></p>
            <p><a href="/status">Check Status</a></p>
        `);
    }

    try {
        const qrImage = await qrcode.toDataURL(qrData);
        res.send(`
            <h2>🔲 Scan QR with WhatsApp</h2>
            <p>Open WhatsApp → Linked Devices → Link a Device</p>
            <img src="${qrImage}" alt="QR Code" style="max-width:300px;"/>
            <br><br>
            <p><a href="/">Home</a> | <a href="/status">Status</a></p>
        `);
    } catch (err) {
        res.send('❌ Error generating QR: ' + err.message);
    }
});

app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        qr_ready: qrData !== null,
        timestamp: new Date().toISOString()
    });
});

// ============================================================
// ✅ SERVER START
// ============================================================

app.listen(PORT, () => {
    console.log(`✅ Server running on port ${PORT}`);
    console.log(`🌐 ${process.env.RENDER_EXTERNAL_URL || `http://localhost:${PORT}`}`);
    startBot();
});
