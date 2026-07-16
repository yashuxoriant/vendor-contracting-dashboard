# IT BOM Creation System - Quick Start Guide

## 🚀 Single Command Start

Run both backend and frontend servers with one command:

```bash
start-all.bat
```

This will open two terminal windows:
- **Backend Server** → http://localhost:8000
- **Frontend Server** → http://localhost:5173

## 📋 What You Need to Provide

Since you have **Azure OpenAI** credentials (not Anthropic Claude), update `backend/.env`:

```env
# Set this to True to use Azure OpenAI instead of Anthropic
USE_AZURE_OPENAI=True

# Your Azure OpenAI credentials
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-actual-api-key-here
AZURE_OPENAI_CHAT_DEPLOYMENT=claude-opus-4-6
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Set this to False since we're using Azure OpenAI
USE_DUMMY_CLAUDE=False
```

Replace:
- `https://your-resource.openai.azure.com/` with your actual Azure OpenAI endpoint
- `your-actual-api-key-here` with your actual API key

## ✅ Current Setup

- **Mock Cosmos DB** ✓ (in-memory, no Azure needed)
- **Mock ADLS** ✓ (local filesystem, no Azure needed)
- **Azure OpenAI** → Ready to configure with your credentials

## 🧪 Testing the App

1. **Run:** `start-all.bat`
2. **Open:** http://localhost:5173
3. **Select a category:** Data Center, SD-WAN, etc.
4. **Chat with AI:** Answer 5 questions
5. **Watch BOM build:** Real-time preview on the right
6. **View dashboard:** Analytics and charts

## 📝 Alternative: Manual Start

If you prefer to run servers manually:

```bash
# Terminal 1 - Backend
cd backend
python -m uvicorn main:app --reload --port 8000

# Terminal 2 - Frontend
cd frontend
npm run dev
```

## 🔑 API Documentation

Once running, visit:
- **API Docs:** http://localhost:8000/api/docs
- **Health Check:** http://localhost:8000/health
