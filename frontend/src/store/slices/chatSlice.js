import { createSlice } from '@reduxjs/toolkit'

const initialState = {
  sessionId: null,
  messages: [],
  context: {
    category: null,
    requirements: {},
    progress: 0,
  },
  isConnected: false,
  isTyping: false,
  partialBOM: null,
}

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    setSessionId: (state, action) => {
      state.sessionId = action.payload
    },
    addMessage: (state, action) => {
      state.messages.push(action.payload)
    },
    setMessages: (state, action) => {
      state.messages = action.payload
    },
    updateContext: (state, action) => {
      state.context = { ...state.context, ...action.payload }
    },
    setConnected: (state, action) => {
      state.isConnected = action.payload
    },
    setTyping: (state, action) => {
      state.isTyping = action.payload
    },
    setPartialBOM: (state, action) => {
      state.partialBOM = action.payload
    },
    resetChat: (state) => {
      return initialState
    },
  },
})

export const {
  setSessionId,
  addMessage,
  setMessages,
  updateContext,
  setConnected,
  setTyping,
  setPartialBOM,
  resetChat,
} = chatSlice.actions

export default chatSlice.reducer
