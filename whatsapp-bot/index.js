const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const express = require('express');
const qrcode = require('qrcode');
const { GoogleGenerativeAI } = require("@google/generative-ai");
const XLSX = require('xlsx');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 10000;

let qrData = null;
let isConnected = false;
let sock = null;

// Gemini setup
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

// Excel file path (Render temporary storage)
const EXCEL_PATH = '/tmp/whatsapp_data.xlsx';

// ==============================================
// WHATSAPP BOT
// ==============================================

async function startBot() {
    const { state, saveCreds } = await useMultiFileAuthState('auth_info');
    
    sock = makeWASocket({
        printQRInTerminal: true,
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

    // 🔥 MESSAGE LISTENER - YEHI MISSING THA
    sock.ev.on('messages.upsert', async (m) => {
        const msg = m.messages[0];
        if (!msg.message) return;

        const sender = msg.key.remoteJid || 'unknown';
        const messageText = msg.message.conversation || msg.message.extendedTextMessage?.text;

        if (!messageText) return;

        console.log(`📩 New message from ${sender}: ${messageText}`);

        // Sirf "Sharique" ke messages filter karein
        if (sender.includes('Sharique') || sender.includes('@s.whatsapp.net')) {
            console.log('🤖 Processing with Gemini...');
            
            try {
                const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
                const prompt = `Extract railway revenue data from this message: ${messageText}`;
                const result = await model.generateContent(prompt);
                const geminiResponse = result.response.text();
                
                console.log(`✅ Gemini Response: ${geminiResponse}`);
                
                // Excel mein save karein
                await updateExcel(messageText, geminiResponse);
                console.log('✅ Excel updated!');
                
            } catch (error) {
                console.error('❌ Error:', error);
            }
        }
    });
}

// ==============================================
// EXCEL FUNCTION
// ==============================================

async function updateExcel(originalMessage, geminiData) {
    let workbook;
    
    if (fs.existsSync(EXCEL_PATH)) {
        workbook = XLSX.readFile(EXCEL_PATH);
    } else {
        workbook = XLSX.utils.book_new();
        const ws = XLSX.utils.aoa_to_sheet([
            ['Timestamp', 'Sender', 'Original Message', 'Gemini Response']
        ]);
        XLSX.utils.book_append_sheet(workbook, ws, 'Sheet1');
    }
    
    const ws = workbook.Sheets['Sheet1'];
    const newRow = [
        new Date().toISOString(),
        'Sharique',
        originalMessage,
        geminiData
    ];
    XLSX.utils.sheet_add_aoa(ws, [newRow], { origin: -1 });
    
    XLSX.writeFile(workbook, EXCEL_PATH);
    console.log('✅ Excel saved at:', EXCEL_PATH);
}

// ==============================================
// EXPRESS ROUTES
// ==============================================

app.get('/', (req, res) => {
    res.send(isConnected ? '✅ WhatsApp Bot Connected!' : '⏳ Waiting for QR...');
});

app.get('/qr', async (req, res) => {
    if (!qrData) {
        return res.send('⏳ QR Code not ready. Refresh in 5 seconds.');
    }
    const qrImage = await qrcode.toDataURL(qrData);
    res.send(`<h2>Scan QR with WhatsApp</h2><img src="${qrImage}" alt="QR Code"/>`);
});

app.get('/download-excel', (req, res) => {
    if (fs.existsSync(EXCEL_PATH)) {
        res.download(EXCEL_PATH);
    } else {
        res.send('❌ Excel file not found.');
    }
});

app.listen(PORT, () => {
    console.log(`✅ Server running on port ${PORT}`);
    startBot();
});
