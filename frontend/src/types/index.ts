// Task status for tracking upload and processing progress
export interface Task {
  task_id: string
  filename: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  error_message?: string
  created_at?: string
  updated_at?: string
}

// Response from upload API
export interface UploadResponse {
  task_id: string
  filename: string
  status: string
  file_path: string
  message?: string
}

// API response wrapper
export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
}
