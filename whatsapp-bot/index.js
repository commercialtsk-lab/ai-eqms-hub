const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode');

const app = express();
const PORT = process.env.PORT || 10000;

let qrData = null;
let isConnected = false;

// ==============================================
// 🔥 WHATSAPP BOT START
// ==============================================

async function startBot() {
    try {
        console.log('🔄 Starting WhatsApp Bot...');
        
        const { state, saveCreds } = await useMultiFileAuthState('auth_info');
        
        const sock = makeWASocket({
            auth: state,
            browser: ['Chrome', 'Windows', '10.0'],
            syncFullHistory: false,
            markOnlineOnConnect: false,
            connectTimeoutMs: 30000,
            // 🔥 Keep connection alive
            keepAliveIntervalMs: 10000,
            patchMessageBeforeSending: (msg) => msg
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', async (update) => {
            const { connection, qr, lastDisconnect } = update;
            
            if (qr) {
                qrData = qr;
                console.log('✅ QR Code generated. Scan with WhatsApp.');
            }

            if (connection === 'open') {
                isConnected = true;
                console.log('✅ WhatsApp Connected!');
            }

            if (connection === 'close') {
                const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
                console.log('🔄 Connection closed, reconnecting:', shouldReconnect);
                isConnected = false;
                
                if (shouldReconnect) {
                    // 🔥 Exponential backoff
                    const delay = Math.min(5000 * Math.pow(1.5, Math.floor(Math.random() * 3)), 30000);
                    console.log(`⏳ Reconnecting in ${delay/1000}s...`);
                    setTimeout(startBot, delay);
                } else {
                    console.log('❌ Logged out. Please scan QR again.');
                }
            }
        });

        // 🔥 Message Handler
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
                
                // 🔥 Sirf "Sharique" ke messages
                if (sender.toLowerCase().includes('sharique') || 
                    sender.includes('91XXXXXXXXXX')) {
                    console.log('🎯 Sharique message detected!');
                }
                
            } catch (err) {
                console.log('⚠️ Message error:', err.message);
            }
        });

        // 🔥 Error Handler
        sock.ev.on('error', (err) => {
            console.log('⚠️ Socket error:', err.message);
        });

    } catch (err) {
        console.log('❌ Bot error:', err.message);
        setTimeout(startBot, 10000);
    }
}

// ==============================================
// 🔥 EXPRESS SERVER
// ==============================================

app.get('/', (req, res) => {
    res.send(`
        <h2>🤖 WhatsApp Bot</h2>
        <p>Status: ${isConnected ? '✅ Connected' : '⏳ Connecting...'}</p>
        <p><a href="/qr">Scan QR</a> | <a href="/status">Status</a></p>
    `);
});

app.get('/qr', async (req, res) => {
    if (!qrData) {
        return res.send(`
            <h2>⏳ QR Code Not Ready</h2>
            <p>Please wait 5 seconds and refresh.</p>
            <a href="/qr">Refresh</a>
        `);
    }
    try {
        const qrImage = await qrcode.toDataURL(qrData);
        res.send(`
            <h2>🔲 Scan QR with WhatsApp</h2>
            <p>Open WhatsApp → Linked Devices → Link a Device</p>
            <img src="${qrImage}" alt="QR" style="max-width:300px;"/>
            <br><br>
            <a href="/">Home</a> | <a href="/status">Status</a>
        `);
    } catch (err) {
        res.send('❌ Error: ' + err.message);
    }
});

app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        qr_ready: qrData !== null,
        timestamp: new Date().toISOString()
    });
});

// ==============================================
// 🔥 SERVER START
// ==============================================

app.listen(PORT, () => {
    console.log(`✅ Server running on port ${PORT}`);
    console.log(`🌐 ${process.env.RENDER_EXTERNAL_URL || `http://localhost:${PORT}`}`);
    startBot();
});
