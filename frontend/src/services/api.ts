import axios, { AxiosInstance } from 'axios'
import { UploadResponse, Task } from '../types'

// Create axios instance with base configuration
const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token if needed
api.interceptors.request.use(
  (config) => {
    // Add auth token if available
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized access
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * Upload an image file to the server
 * @param file - File object to upload
 * @returns Promise with upload response containing task_id and file info
 */
export const uploadImage = async (file: File): Promise<UploadResponse> => {
  const formData = new FormData()
  formData.append('file', file)

  const response = await api.post<UploadResponse>('/api/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })

  return response.data
}

/**
 * Get the status of a processing task
 * @param taskId - The task ID to check
 * @returns Promise with task status information
 */
export const getTaskStatus = async (taskId: string): Promise<Task> => {
  const response = await api.get<Task>(`/api/tasks/${taskId}`)
  return response.data
}

/**
 * Cancel a running task
 * @param taskId - The task ID to cancel
 * @returns Promise with cancellation confirmation
 */
export const cancelTask = async (taskId: string): Promise<{ message: string }> => {
  const response = await api.post<{ message: string }>(`/api/tasks/${taskId}/cancel`)
  return response.data
}

/**
 * Get task results when processing is complete
 * @param taskId - The task ID to get results for
 * @returns Promise with task results
 */
export const getTaskResults = async (taskId: string): Promise<any> => {
  const response = await api.get(`/api/tasks/${taskId}/results`)
  return response.data
}

export default api
