const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode');

const app = express();
const PORT = process.env.PORT || 10000;

let qrData = null;
let isConnected = false;
let sock = null;

// ==============================================
// 🔥 WHATSAPP BOT START
// ==============================================

async function startBot() {
    try {
        console.log('🔄 Starting WhatsApp Bot...');
        
        const { state, saveCreds } = await useMultiFileAuthState('auth_info');
        
        sock = makeWASocket({
            auth: state,
            browser: ['Chrome', 'Windows', '10.0'],
            syncFullHistory: false,
            markOnlineOnConnect: false,
            connectTimeoutMs: 30000
        });

        // Save credentials
        sock.ev.on('creds.update', saveCreds);

        // Connection events
        sock.ev.on('connection.update', (update) => {
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
                    setTimeout(startBot, 5000);
                }
            }
        });

        // ==============================================
        // 🔥 MESSAGE HANDLER
        // ==============================================

        sock.ev.on('messages.upsert', async (m) => {
            try {
                const msg = m.messages[0];
                if (!msg || msg.key.fromMe) return;
                
                const sender = msg.key.remoteJid;
                const message = msg.message;
                
                // Text message extract
                let text = '';
                if (message.conversation) {
                    text = message.conversation;
                } else if (message.extendedTextMessage) {
                    text = message.extendedTextMessage.text;
                } else if (message.imageMessage) {
                    text = message.imageMessage.caption || '[Image]';
                } else if (message.documentMessage) {
                    text = '[Document]';
                } else {
                    text = '[Other Media]';
                }
                
                console.log(`📩 [${sender}] ${text.substring(0, 100)}`);
                
                // 🔥 Sirf "Sharique" ke messages filter karein
                if (sender.toLowerCase().includes('sharique') || 
                    sender.includes('91XXXXXXXXXX')) { // 🔥 Apna number daalein
                    console.log('🎯 Sharique message detected!');
                    
                    // Yahan Gemini + Excel logic add karein
                    // await processMessage(sender, text);
                }
                
            } catch (err) {
                console.log('⚠️ Message handler error:', err.message);
            }
        });

        // ==============================================
        // 🔥 PRESENCE UPDATE (Optional)
        // ==============================================

        sock.ev.on('presence.update', (update) => {
            // console.log('👤 Presence update:', update);
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
        <p>QR: <a href="/qr">Click here to scan</a></p>
    `);
});

app.get('/qr', async (req, res) => {
    if (!qrData) {
        return res.send(`
            <h2>⏳ QR Code Not Ready</h2>
            <p>Please wait 5 seconds and refresh.</p>
            <p><a href="/qr">Refresh</a></p>
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

// ==============================================
// 🔥 SERVER START
// ==============================================

app.listen(PORT, () => {
    console.log(`✅ Server running on port ${PORT}`);
    console.log(`🌐 URL: https://ai-eqms-hub-5.onrender.com`);
    startBot();
});
