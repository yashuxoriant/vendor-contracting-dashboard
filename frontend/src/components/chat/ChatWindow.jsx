import { useState, useRef, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import {
  Box,
  TextField,
  IconButton,
  Paper,
  Typography,
  Chip,
  CircularProgress,
} from '@mui/material'
import { Send as SendIcon } from '@mui/icons-material'
import { addMessage, setTyping, setPartialBOM } from '../../store/slices/chatSlice'

export default function ChatWindow({ category }) {
  const dispatch = useDispatch()
  const messages = useSelector((state) => state.chat.messages)
  const isTyping = useSelector((state) => state.chat.isTyping)
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    // Send initial message when category selected
    if (messages.length === 0) {
      const welcomeMessage = {
        role: 'assistant',
        content: `Great! Let's create a ${category.name} BOM. I'll ask you 5 questions to generate a complete Bill of Materials. Ready to start?`,
        timestamp: new Date().toISOString(),
      }
      dispatch(addMessage(welcomeMessage))
      
      // Simulate first question
      setTimeout(() => {
        const firstQuestion = {
          role: 'assistant',
          content: 'Question 1/5: How many units do you need? (e.g., servers, sites, users)',
          timestamp: new Date().toISOString(),
        }
        dispatch(addMessage(firstQuestion))
      }, 1000)
    }
  }, [])

  const handleSend = () => {
    if (!input.trim()) return

    // Add user message
    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    }
    dispatch(addMessage(userMessage))
    setInput('')

    // Simulate AI response
    dispatch(setTyping(true))
    setTimeout(() => {
      const responses = [
        "Perfect! That helps me understand the scale. Question 2/5: Do you need high availability (HA pair)?",
        "Great! Question 3/5: What's your storage capacity requirement? (in TB)",
        "Excellent. Question 4/5: Do you need backup/disaster recovery?",
        "Almost done! Question 5/5: What's your preferred vendor? (CDW, Entity, or Direct)",
        "Perfect! I have all the information I need. Generating your BOM now...",
      ]
      
      const currentQuestion = messages.filter(m => m.role === 'assistant' && m.content.includes('Question')).length
      const response = responses[currentQuestion] || responses[responses.length - 1]
      
      const aiMessage = {
        role: 'assistant',
        content: response,
        timestamp: new Date().toISOString(),
      }
      dispatch(addMessage(aiMessage))
      dispatch(setTyping(false))

      // If last question, generate dummy BOM
      if (currentQuestion >= 4) {
        setTimeout(() => {
          const dummyBOM = {
            line_items: [
              { line_number: 1, description: 'Dell PowerEdge R750 Server', qty: 10, unit_price: 18500, extended_price: 185000 },
              { line_number: 2, description: 'VMware vSphere Enterprise Plus', qty: 20, unit_price: 4995, extended_price: 99900 },
              { line_number: 3, description: 'Dell ProSupport 5Y 24x7', qty: 10, unit_price: 3200, extended_price: 32000 },
            ],
            totals: {
              hardware: 185000,
              software: 99900,
              services: 32000,
              total_otc: 316900,
            },
          }
          dispatch(setPartialBOM(dummyBOM))
          
          const completeMessage = {
            role: 'assistant',
            content: '✅ BOM generated successfully! You can review it in the preview panel on the right. Would you like to export it or make any adjustments?',
            timestamp: new Date().toISOString(),
          }
          dispatch(addMessage(completeMessage))
        }, 2000)
      }
    }, 1500)
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Messages */}
      <Box
        sx={{
          flexGrow: 1,
          overflow: 'auto',
          p: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        {messages.map((message, index) => (
          <Box
            key={index}
            sx={{
              display: 'flex',
              justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            <Paper
              sx={{
                p: 2,
                maxWidth: '70%',
                bgcolor: message.role === 'user' ? 'primary.main' : 'grey.100',
                color: message.role === 'user' ? 'white' : 'text.primary',
              }}
            >
              <Typography variant="body1">{message.content}</Typography>
              <Typography variant="caption" sx={{ opacity: 0.7, mt: 0.5, display: 'block' }}>
                {new Date(message.timestamp).toLocaleTimeString()}
              </Typography>
            </Paper>
          </Box>
        ))}
        
        {isTyping && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <CircularProgress size={16} />
            <Typography variant="caption" color="text.secondary">
              AI is thinking...
            </Typography>
          </Box>
        )}
        
        <div ref={messagesEndRef} />
      </Box>

      {/* Input */}
      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <TextField
            fullWidth
            placeholder="Type your answer..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            multiline
            maxRows={3}
          />
          <IconButton color="primary" onClick={handleSend} disabled={!input.trim()}>
            <SendIcon />
          </IconButton>
        </Box>
      </Box>
    </Box>
  )
}
