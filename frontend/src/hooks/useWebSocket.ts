import { useEffect, useState, useCallback, useRef } from 'react'

interface ProgressMessage {
  type: 'progress' | 'complete' | 'error'
  progress: number
  message: string
  result?: any
  error?: string
}

interface UseWebSocketReturn {
  progress: number
  message: string
  result: any
  error: string | null
  isConnected: boolean
  sendMessage: (message: string) => void
  reconnect: () => void
}

export function useWebSocket(taskId: string | null): UseWebSocketReturn {
  const [progress, setProgress] = useState(0)
  const [message, setMessage] = useState('')
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttempts = useRef(0)
  const MAX_RECONNECT_ATTEMPTS = 5

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
  }, [])

  const connect = useCallback(() => {
    if (!taskId || reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
      return
    }

    try {
      const ws = new WebSocket(`ws://localhost:8000/ws/${taskId}`)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('WebSocket connected')
        setIsConnected(true)
        reconnectAttempts.current = 0
        setError(null)
      }

      ws.onmessage = (event) => {
        try {
          const data: ProgressMessage = JSON.parse(event.data)

          if (data.type === 'progress') {
            setProgress(data.progress * 100)
            setMessage(data.message)
          } else if (data.type === 'complete') {
            setProgress(100)
            setMessage('Processing complete')
            setResult(data.result)
            setIsConnected(false)
          } else if (data.type === 'error') {
            setError(data.error || 'An error occurred')
            setMessage('Error')
            setIsConnected(false)
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err)
        }
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        setIsConnected(false)

        // Attempt to reconnect if not completed
        if (progress < 100 && reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current++
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, 3000 * reconnectAttempts.current) // Exponential backoff
        }
      }

      ws.onerror = (err) => {
        console.error('WebSocket error:', err)
        setError('Connection error')
      }
    } catch (err) {
      console.error('Failed to create WebSocket:', err)
      setError('Failed to connect')
    }
  }, [taskId, progress])

  useEffect(() => {
    if (taskId) {
      connect()
    }

    return () => {
      cleanup()
    }
  }, [taskId, connect, cleanup])

  const sendMessage = useCallback((msg: string) => {
    if (wsRef.current && isConnected) {
      wsRef.current.send(msg)
    }
  }, [isConnected])

  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0
    cleanup()
    connect()
  }, [cleanup, connect])

  return {
    progress,
    message,
    result,
    error,
    isConnected,
    sendMessage,
    reconnect
  }
}
