// ═══════════════════════════════════════════════
// IT Contracting Dashboard — Backend API
// Proxies Groq (chat) + LlamaParse (extraction)
// Reads secrets from environment variables
// ═══════════════════════════════════════════════

const express = require('express');
const multer = require('multer');
const fetch = require('node-fetch');
const FormData = require('form-data');
const cors = require('cors');
require('dotenv').config();

const app = express();

// ─── MIDDLEWARE ───
app.use(cors({
  origin: '*',  // tighten this in production to your GitHub Pages URL
  methods: ['GET', 'POST'],
}));
app.use(express.json({ limit: '10mb' }));
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 20 * 1024 * 1024 } });

// ─── ROOT ───
app.get('/', (req, res) => {
  res.json({
    service: 'IT Contracting Dashboard API',
    status: 'running',
    endpoints: ['/api/health', '/api/llama-health', '/api/chat', '/api/extract'],
  });
});

// ─── HEALTH CHECKS ───
app.get('/api/health', (req, res) => {
  res.json({
    ok: true,
    grok_configured: !!process.env.GROQ_API_KEY,
    timestamp: new Date().toISOString(),
  });
});

app.get('/api/llama-health', (req, res) => {
  res.json({
    ok: true,
    llama_configured: !!process.env.LLAMA_API_KEY,
    timestamp: new Date().toISOString(),
  });
});

// ─── GROQ CHAT PROXY ───
app.post('/api/chat', async (req, res) => {
  if (!process.env.GROQ_API_KEY) {
    return res.status(500).json({ error: 'GROQ_API_KEY not configured on server' });
  }
  try {
    const { messages, max_tokens = 600, temperature = 0.3, model = 'llama-3.3-70b-versatile' } = req.body;
    if (!messages || !Array.isArray(messages)) {
      return res.status(400).json({ error: 'messages array required' });
    }

    const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.GROQ_API_KEY}`,
      },
      body: JSON.stringify({ model, messages, max_tokens, temperature }),
    });

    if (!r.ok) {
      const err = await r.text();
      console.error('Groq API error:', err);
      return res.status(r.status).json({ error: 'Groq API error', details: err.substring(0, 200) });
    }

    const d = await r.json();
    res.json({
      reply: d.choices?.[0]?.message?.content || 'No response',
      usage: d.usage,
    });
  } catch (e) {
    console.error('Chat endpoint error:', e.message);
    res.status(500).json({ error: e.message });
  }
});

// ─── LLAMA EXTRACT PROXY ───
app.post('/api/extract', upload.single('file'), async (req, res) => {
  if (!process.env.LLAMA_API_KEY) {
    return res.status(500).json({ error: 'LLAMA_API_KEY not configured' });
  }
  if (!req.file) {
    return res.status(400).json({ error: 'No file uploaded' });
  }

  try {
    // Step 1: Upload to LlamaParse
    const fd = new FormData();
    fd.append('file', req.file.buffer, { filename: req.file.originalname });

    const uploadRes = await fetch('https://api.cloud.llamaindex.ai/api/parsing/upload', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${process.env.LLAMA_API_KEY}` },
      body: fd,
    });

    if (!uploadRes.ok) {
      const err = await uploadRes.text();
      throw new Error('LlamaParse upload failed: ' + err.substring(0, 200));
    }

    const job = await uploadRes.json();
    console.log('LlamaParse job started:', job.id);

    // Step 2: Poll for markdown result (max 60 seconds)
    let parsed = null;
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 2000));
      const resultRes = await fetch(
        `https://api.cloud.llamaindex.ai/api/parsing/job/${job.id}/result/markdown`,
        { headers: { 'Authorization': `Bearer ${process.env.LLAMA_API_KEY}` } }
      );
      if (resultRes.ok) {
        parsed = await resultRes.json();
        break;
      }
    }

    if (!parsed || !parsed.markdown) {
      throw new Error('LlamaParse timed out or returned empty result');
    }

    // Step 3: Use Groq to extract structured data
    if (!process.env.GROQ_API_KEY) {
      return res.json({
        extracted: { raw: parsed.markdown.substring(0, 1000) },
        confidence: 'low',
        note: 'GROQ_API_KEY not set — returning raw markdown only',
      });
    }

    const extractPrompt = `You are a quote extraction assistant. Extract from this vendor quote:
- vendor: company name
- price: total price as NUMBER (no currency symbols)
- category: one of [Cybersecurity, Network & Telecom, Hosting, M365 & Power Platform, IdAM, Service Management (SNow)]
- services: array of service names/SKUs
- project: one of [Idemia, Tenneco, Panasonic] if mentioned, otherwise null

Return ONLY valid JSON with those exact keys. Quote text:

${parsed.markdown.substring(0, 6000)}`;

    const exRes = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.GROQ_API_KEY}`,
      },
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        messages: [
          { role: 'system', content: 'You are a JSON extraction assistant. Always return only valid JSON.' },
          { role: 'user', content: extractPrompt },
        ],
        response_format: { type: 'json_object' },
        temperature: 0.1,
      }),
    });

    if (!exRes.ok) {
      const err = await exRes.text();
      throw new Error('Groq extraction failed: ' + err.substring(0, 200));
    }

    const exData = await exRes.json();
    const extracted = JSON.parse(exData.choices[0].message.content);

    res.json({
      extracted,
      confidence: extracted.price && extracted.vendor && extracted.services?.length ? 'high' : 'med',
      job_id: job.id,
    });
  } catch (e) {
    console.error('Extract endpoint error:', e.message);
    res.status(500).json({ error: e.message });
  }
});

// ─── START SERVER ───
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`✅ Backend running on port ${PORT}`);
  console.log(`   GROQ_API_KEY: ${process.env.GROQ_API_KEY ? '✓ configured' : '✗ MISSING'}`);
  console.log(`   LLAMA_API_KEY: ${process.env.LLAMA_API_KEY ? '✓ configured' : '✗ MISSING'}`);
});
